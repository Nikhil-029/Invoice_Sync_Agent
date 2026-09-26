import os
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from app.connectors.base import AccountingConnector, SyncResult

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADER_ROW = [
    "Invoice Number", "Vendor", "Invoice Date", "Due Date", "Currency",
    "Subtotal", "Tax", "Total", "Synced At",
]


class GoogleSheetsConnector(AccountingConnector):
    name = "sheets"

    def __init__(self):
        creds_file = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "credentials.json")
        spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        if not spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is not set in .env")
        if not os.path.exists(creds_file):
            raise RuntimeError(
                f"Google service account credentials file not found: {creds_file}. "
                "See README for how to create one."
            )

        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
        client = gspread.authorize(creds)
        self.sheet = client.open_by_key(spreadsheet_id).sheet1

        # Ensure a header row exists
        existing = self.sheet.row_values(1)
        if existing != HEADER_ROW:
            self.sheet.insert_row(HEADER_ROW, 1)

    def check_duplicate(self, invoice_number: str, vendor_name: str) -> bool:
        if not invoice_number:
            return False
        try:
            cell = self.sheet.find(invoice_number)
            if cell is None:
                return False
            row = self.sheet.row_values(cell.row)
            # Confirm vendor also matches, in case of duplicate invoice numbers
            # across different vendors
            return len(row) > 1 and row[1] == vendor_name
        except gspread.exceptions.CellNotFound:
            return False

    def push_invoice(self, invoice: dict) -> SyncResult:
        from datetime import datetime

        row = [
            invoice.get("invoice_number") or "",
            invoice.get("vendor_name") or "",
            invoice.get("invoice_date") or "",
            invoice.get("due_date") or "",
            invoice.get("currency") or "",
            invoice.get("subtotal") or "",
            invoice.get("tax_amount") or "",
            invoice.get("total_amount") or "",
            datetime.utcnow().isoformat(timespec="seconds"),
        ]
        try:
            self.sheet.append_row(row)
            return SyncResult(success=True, message="Row appended to Google Sheet")
        except Exception as exc:  # noqa: BLE001 — surfaced to caller as sync_error
            return SyncResult(success=False, message=str(exc))
