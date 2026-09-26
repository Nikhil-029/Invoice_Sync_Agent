import os

import requests

from app.connectors.base import AccountingConnector, SyncResult

TALLY_XML_TEMPLATE = """<ENVELOPE>
 <HEADER>
  <TALLYREQUEST>Import Data</TALLYREQUEST>
 </HEADER>
 <BODY>
  <IMPORTDATA>
   <REQUESTDESC>
    <REPORTNAME>Vouchers</REPORTNAME>
    <STATICVARIABLES>
     <SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
    </STATICVARIABLES>
   </REQUESTDESC>
   <REQUESTDATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
     <VOUCHER VCHTYPE="Purchase" ACTION="Create">
      <DATE>{date}</DATE>
      <NARRATION>Auto-synced invoice {invoice_number} from {vendor}</NARRATION>
      <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
      <PARTYLEDGERNAME>{vendor}</PARTYLEDGERNAME>
      <ALLLEDGERENTRIES.LIST>
       <LEDGERNAME>{vendor}</LEDGERNAME>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <AMOUNT>-{total}</AMOUNT>
      </ALLLEDGERENTRIES.LIST>
      <ALLLEDGERENTRIES.LIST>
       <LEDGERNAME>Purchase Account</LEDGERNAME>
       <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
       <AMOUNT>{total}</AMOUNT>
      </ALLLEDGERENTRIES.LIST>
     </VOUCHER>
    </TALLYMESSAGE>
   </REQUESTDATA>
  </IMPORTDATA>
 </BODY>
</ENVELOPE>"""


class TallyConnector(AccountingConnector):
    """
    Talks to a locally running TallyPrime instance over its XML HTTP
    gateway (enabled in Tally under F1 > Settings > Connectivity).

    This posts a minimal Purchase Voucher per invoice. Ledger names
    (vendor, "Purchase Account") must already exist in the target company
    for Tally to accept the voucher — matches how your existing Tally MCP
    server work handles ledger creation.
    """
    name = "tally"

    def __init__(self):
        self.host = os.getenv("TALLY_HOST", "localhost")
        self.port = os.getenv("TALLY_PORT", "9000")
        self.company = os.getenv("TALLY_COMPANY_NAME")
        if not self.company:
            raise RuntimeError("TALLY_COMPANY_NAME is not set in .env")
        self.url = f"http://{self.host}:{self.port}"

    def test_connection(self) -> bool:
        try:
            resp = requests.get(self.url, timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def check_duplicate(self, invoice_number: str, vendor_name: str) -> bool:
        # A full implementation would query Tally's "Voucher Register" report
        # filtered by narration/invoice number. Left as an extension point —
        # duplicate detection for Tally needs a report XML request, not just
        # an import call.
        return False

    def push_invoice(self, invoice: dict) -> SyncResult:
        xml = TALLY_XML_TEMPLATE.format(
            company=self.company,
            date=(invoice.get("invoice_date") or "").replace("-", ""),
            invoice_number=invoice.get("invoice_number") or "",
            vendor=invoice.get("vendor_name") or "Unknown Vendor",
            total=invoice.get("total_amount") or 0,
        )
        try:
            resp = requests.post(self.url, data=xml.encode("utf-8"), timeout=30)
            resp.raise_for_status()
            if "LINEERROR" in resp.text.upper():
                return SyncResult(success=False, message=f"Tally rejected voucher: {resp.text[:300]}")
            return SyncResult(success=True, message="Voucher created in Tally")
        except requests.RequestException as exc:
            return SyncResult(success=False, message=f"Could not reach Tally: {exc}")
