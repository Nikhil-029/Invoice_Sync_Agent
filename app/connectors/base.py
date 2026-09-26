"""
Every accounting target (Google Sheets, QuickBooks, Tally, ...) implements
this same interface. The rest of the app only ever talks to `AccountingConnector`,
never to a specific vendor SDK — that's what makes the sync target pluggable.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class SyncResult:
    success: bool
    external_id: Optional[str] = None   # ID of the record in the target system
    message: str = ""


class AccountingConnector(ABC):
    name: str = "base"

    @abstractmethod
    def push_invoice(self, invoice: dict) -> SyncResult:
        """Push one invoice's normalized fields to the accounting target.

        `invoice` is a plain dict with the same shape as the Invoice model's
        core fields (vendor_name, invoice_number, invoice_date, currency,
        subtotal, tax_amount, total_amount, line_items).
        """
        raise NotImplementedError

    @abstractmethod
    def check_duplicate(self, invoice_number: str, vendor_name: str) -> bool:
        """Return True if this invoice already exists in the target system."""
        raise NotImplementedError

    def test_connection(self) -> bool:
        """Optional: connectors can override to verify credentials/reachability."""
        return True
