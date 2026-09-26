import json
import os
import shutil
import uuid
from typing import List

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Invoice, InvoiceStatus, LedgerRecord
from app import extraction
from app.connectors import get_connector
from app.rate_limit import enforce_upload_rate_limit

Base.metadata.create_all(bind=engine)

BASE_DIR = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(os.path.dirname(BASE_DIR), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Invoice → Accounting Sync Agent")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ---------------------------------------------------------------- helpers --

def invoice_to_dict(inv: Invoice) -> dict:
    return {
        "id": inv.id,
        "file_name": inv.file_name,
        "vendor_name": inv.vendor_name,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "currency": inv.currency,
        "subtotal": inv.subtotal,
        "tax_amount": inv.tax_amount,
        "total_amount": inv.total_amount,
        "line_items": json.loads(inv.line_items_json or "[]"),
        "confidence": json.loads(inv.confidence_json or "{}"),
        "status": inv.status.value if hasattr(inv.status, "value") else inv.status,
        "is_low_confidence": inv.is_low_confidence,
        "connector_used": inv.connector_used,
        "sync_error": inv.sync_error,
    }


# ------------------------------------------------------------------ pages --

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"
    ledger = []
    if demo_mode:
        rows = db.query(LedgerRecord).order_by(LedgerRecord.synced_at.desc()).limit(50).all()
        ledger = [
            {
                "vendor_name": r.vendor_name,
                "invoice_number": r.invoice_number,
                "invoice_date": r.invoice_date,
                "currency": r.currency,
                "total_amount": r.total_amount,
                "synced_at": r.synced_at.strftime("%Y-%m-%d %H:%M"),
            }
            for r in rows
        ]
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "invoices": [invoice_to_dict(i) for i in invoices],
            "active_connector": "demo (public showcase)" if demo_mode else os.getenv("ACTIVE_CONNECTOR", "sheets"),
            "demo_mode": demo_mode,
            "ledger": ledger,
            "demo_upload_limit": os.getenv("DEMO_MAX_UPLOADS_PER_HOUR", "8"),
        },
    )


# -------------------------------------------------------------- upload API --

@app.post("/api/upload")
async def upload_invoices(
    request: Request, files: List[UploadFile] = File(...), db: Session = Depends(get_db)
):
    enforce_upload_rate_limit(request)
    results = []
    for f in files:
        ext = os.path.splitext(f.filename)[1]
        saved_name = f"{uuid.uuid4().hex}{ext}"
        saved_path = os.path.join(UPLOAD_DIR, saved_name)
        with open(saved_path, "wb") as out:
            shutil.copyfileobj(f.file, out)

        try:
            extracted = extraction.process_file(saved_path)
        except Exception as exc:  # noqa: BLE001
            results.append({"file_name": f.filename, "error": str(exc)})
            continue

        inv = Invoice(
            file_name=f.filename,
            vendor_name=extracted.get("vendor_name"),
            invoice_number=extracted.get("invoice_number"),
            invoice_date=extracted.get("invoice_date"),
            due_date=extracted.get("due_date"),
            currency=extracted.get("currency"),
            subtotal=extracted.get("subtotal"),
            tax_amount=extracted.get("tax_amount"),
            total_amount=extracted.get("total_amount"),
            line_items_json=json.dumps(extracted.get("line_items", [])),
            raw_extracted_json=json.dumps(extracted),
            confidence_json=json.dumps(extracted.get("confidence", {})),
            status=InvoiceStatus.EXTRACTED,
            is_low_confidence=extracted.get("_low_confidence", True),
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)
        results.append(invoice_to_dict(inv))

    return {"results": results}


# ------------------------------------------------------------- review API --

@app.post("/api/invoices/{invoice_id}/update")
async def update_invoice(invoice_id: int, payload: dict, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Invoice not found")

    editable_fields = [
        "vendor_name", "invoice_number", "invoice_date", "due_date",
        "currency", "subtotal", "tax_amount", "total_amount",
    ]
    for field in editable_fields:
        if field in payload:
            setattr(inv, field, payload[field])

    db.commit()
    db.refresh(inv)
    return invoice_to_dict(inv)


@app.post("/api/invoices/{invoice_id}/approve")
async def approve_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Invoice not found")
    inv.status = InvoiceStatus.APPROVED
    db.commit()
    return {"status": "approved"}


@app.post("/api/invoices/{invoice_id}/reject")
async def reject_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Invoice not found")
    inv.status = InvoiceStatus.REJECTED
    db.commit()
    return {"status": "rejected"}


# --------------------------------------------------------------- sync API --

@app.post("/api/invoices/{invoice_id}/sync")
async def sync_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if inv.status != InvoiceStatus.APPROVED:
        raise HTTPException(400, "Invoice must be approved before syncing")

    connector = get_connector()

    if connector.check_duplicate(inv.invoice_number or "", inv.vendor_name or ""):
        inv.status = InvoiceStatus.DUPLICATE
        db.commit()
        return {"status": "duplicate", "message": "Already exists in target system"}

    result = connector.push_invoice(invoice_to_dict(inv))
    inv.connector_used = connector.name
    if result.success:
        inv.status = InvoiceStatus.SYNCED
        inv.sync_error = None
    else:
        inv.status = InvoiceStatus.FAILED
        inv.sync_error = result.message
    db.commit()

    return {"status": inv.status.value, "message": result.message, "external_id": result.external_id}


@app.post("/api/sync-all-approved")
async def sync_all_approved(db: Session = Depends(get_db)):
    approved = db.query(Invoice).filter(Invoice.status == InvoiceStatus.APPROVED).all()
    connector = get_connector()
    synced, failed, duplicates = 0, 0, 0

    for inv in approved:
        if connector.check_duplicate(inv.invoice_number or "", inv.vendor_name or ""):
            inv.status = InvoiceStatus.DUPLICATE
            duplicates += 1
            continue
        result = connector.push_invoice(invoice_to_dict(inv))
        inv.connector_used = connector.name
        if result.success:
            inv.status = InvoiceStatus.SYNCED
            synced += 1
        else:
            inv.status = InvoiceStatus.FAILED
            inv.sync_error = result.message
            failed += 1

    db.commit()
    return {"synced": synced, "failed": failed, "duplicates": duplicates}


@app.get("/api/invoices")
async def list_invoices(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
    return [invoice_to_dict(i) for i in invoices]
