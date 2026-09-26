import enum
from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum, Boolean
from sqlalchemy.orm import relationship

from app.database import Base


class InvoiceStatus(str, enum.Enum):
    EXTRACTED = "extracted"       # raw extraction done, awaiting review
    APPROVED = "approved"         # human approved, ready to sync
    SYNCED = "synced"             # pushed to accounting target
    DUPLICATE = "duplicate"       # detected as already synced
    FAILED = "failed"             # sync attempt failed
    REJECTED = "rejected"         # human rejected


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String, nullable=False)

    vendor_name = Column(String, nullable=True)
    invoice_number = Column(String, nullable=True, index=True)
    invoice_date = Column(String, nullable=True)
    due_date = Column(String, nullable=True)
    currency = Column(String, nullable=True)
    subtotal = Column(Float, nullable=True)
    tax_amount = Column(Float, nullable=True)
    total_amount = Column(Float, nullable=True)

    line_items_json = Column(Text, nullable=True)  # JSON string of line items
    raw_extracted_json = Column(Text, nullable=True)  # full raw LLM output
    confidence_json = Column(Text, nullable=True)  # per-field confidence scores

    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.EXTRACTED)
    is_low_confidence = Column(Boolean, default=False)

    connector_used = Column(String, nullable=True)
    sync_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LedgerRecord(Base):
    """
    Stand-in 'destination accounting system' used by DemoConnector so a
    public demo never needs real Sheets/QuickBooks/Tally credentials.
    Visually represents the row that would have been written to a real
    ledger — shown in its own table in the UI.
    """
    __tablename__ = "ledger_records"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, nullable=False)
    vendor_name = Column(String, nullable=True)
    invoice_number = Column(String, nullable=True, index=True)
    invoice_date = Column(String, nullable=True)
    currency = Column(String, nullable=True)
    total_amount = Column(Float, nullable=True)
    synced_at = Column(DateTime, default=datetime.utcnow)
