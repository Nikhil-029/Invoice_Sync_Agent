import os
from typing import Optional

import requests

from app.connectors.base import AccountingConnector, SyncResult

SANDBOX_BASE = "https://sandbox-quickbooks.api.intuit.com"
PROD_BASE = "https://quickbooks.api.intuit.com"


class QuickBooksConnector(AccountingConnector):
    """
    Pushes invoices into QuickBooks Online as Bills via their v3 API.

    Requires an existing OAuth2 refresh token (obtained once via QuickBooks'
    OAuth flow — out of scope for this connector, see README). This class
    only handles token refresh + the API call, not the initial consent flow.
    """
    name = "quickbooks"

    def __init__(self):
        self.client_id = os.getenv("QB_CLIENT_ID")
        self.client_secret = os.getenv("QB_CLIENT_SECRET")
        self.refresh_token = os.getenv("QB_REFRESH_TOKEN")
        self.realm_id = os.getenv("QB_REALM_ID")
        env = os.getenv("QB_ENVIRONMENT", "sandbox")
        self.base_url = SANDBOX_BASE if env == "sandbox" else PROD_BASE

        missing = [
            n for n, v in [
                ("QB_CLIENT_ID", self.client_id),
                ("QB_CLIENT_SECRET", self.client_secret),
                ("QB_REFRESH_TOKEN", self.refresh_token),
                ("QB_REALM_ID", self.realm_id),
            ] if not v
        ]
        if missing:
            raise RuntimeError(f"Missing QuickBooks env vars: {', '.join(missing)}")

        self._access_token: Optional[str] = None

    def _refresh_access_token(self) -> str:
        resp = requests.post(
            "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]
        return self._access_token

    def _headers(self) -> dict:
        if not self._access_token:
            self._refresh_access_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def check_duplicate(self, invoice_number: str, vendor_name: str) -> bool:
        if not invoice_number:
            return False
        query = (
            f"select Id from Bill where DocNumber = '{invoice_number}'"
        )
        url = f"{self.base_url}/v3/company/{self.realm_id}/query"
        resp = requests.get(
            url, headers=self._headers(), params={"query": query}, timeout=30
        )
        if resp.status_code == 401:
            self._refresh_access_token()
            resp = requests.get(
                url, headers=self._headers(), params={"query": query}, timeout=30
            )
        resp.raise_for_status()
        bills = resp.json().get("QueryResponse", {}).get("Bill", [])
        return len(bills) > 0

    def push_invoice(self, invoice: dict) -> SyncResult:
        # NOTE: QuickBooks requires a VendorRef with a real internal vendor ID.
        # In a production build this would look up/create the vendor first.
        # Left as a clear extension point for the demo.
        payload = {
            "VendorRef": {"name": invoice.get("vendor_name") or "Unknown Vendor"},
            "DocNumber": invoice.get("invoice_number"),
            "TxnDate": invoice.get("invoice_date"),
            "Line": [
                {
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": invoice.get("total_amount") or 0,
                    "AccountBasedExpenseLineDetail": {
                        "AccountRef": {"name": "Accounts Payable"}
                    },
                }
            ],
        }
        url = f"{self.base_url}/v3/company/{self.realm_id}/bill"
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            if resp.status_code == 401:
                self._refresh_access_token()
                resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            resp.raise_for_status()
            bill_id = resp.json().get("Bill", {}).get("Id")
            return SyncResult(success=True, external_id=bill_id, message="Bill created in QuickBooks")
        except requests.HTTPError as exc:
            return SyncResult(success=False, message=f"QuickBooks API error: {exc}")
        except Exception as exc:  # noqa: BLE001
            return SyncResult(success=False, message=str(exc))
