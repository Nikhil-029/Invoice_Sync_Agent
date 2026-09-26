"""
DemoConnector — the connector used on the public portfolio deployment.

It implements the exact same AccountingConnector interface as the real
Sheets/QuickBooks/Tally connectors, but "syncs" by writing to a local
LedgerRecord table instead of an external system. This means the live
public demo needs zero real credentials and can't touch anyone's actual
accounting data — while still proving the full pipeline end to end,
including duplicate detection.
"""
from app.connectors.base import AccountingConnector, SyncResult
from app.database import SessionLocal
from app.models import LedgerRecord


class DemoConnector(AccountingConnector):
    name = "demo"

    def check_duplicate(self, invoice_number: str, vendor_name: str) -> bool:
        if not invoice_number:
            return False
        db = SessionLocal()
        try:
            existing = (
                db.query(LedgerRecord)
                .filter(
                    LedgerRecord.invoice_number == invoice_number,
                    LedgerRecord.vendor_name == vendor_name,
                )
                .first()
            )
            return existing is not None
        finally:
            db.close()

    def push_invoice(self, invoice: dict) -> SyncResult:
        db = SessionLocal()
        try:
            record = LedgerRecord(
                invoice_id=invoice.get("id"),
                vendor_name=invoice.get("vendor_name"),
                invoice_number=invoice.get("invoice_number"),
                invoice_date=invoice.get("invoice_date"),
                currency=invoice.get("currency"),
                total_amount=invoice.get("total_amount"),
            )
            db.add(record)
            db.commit()
            return SyncResult(
                success=True,
                external_id=str(record.id),
                message="Synced to demo ledger (no external system touched)",
            )
        except Exception as exc:  # noqa: BLE001
            return SyncResult(success=False, message=str(exc))
        finally:
            db.close()
