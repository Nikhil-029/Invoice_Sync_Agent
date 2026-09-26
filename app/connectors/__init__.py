import os

from app.connectors.base import AccountingConnector, SyncResult

_CONNECTOR_CACHE = {}


def get_connector(name: str = None) -> AccountingConnector:
    """Factory: returns the connector instance for the given name (or the
    ACTIVE_CONNECTOR from .env if none is given). Instances are cached so
    OAuth clients / sheet handles aren't recreated on every request.
    """
    # DEMO_MODE always wins, even if ACTIVE_CONNECTOR is misconfigured —
    # this is what keeps a public deployment from ever touching real
    # Sheets/QuickBooks/Tally credentials.
    if os.getenv("DEMO_MODE", "false").lower() == "true":
        name = "demo"
    else:
        name = name or os.getenv("ACTIVE_CONNECTOR", "sheets")

    if name in _CONNECTOR_CACHE:
        return _CONNECTOR_CACHE[name]

    if name == "demo":
        from app.connectors.demo_connector import DemoConnector
        connector = DemoConnector()
    elif name == "sheets":
        from app.connectors.sheets_connector import GoogleSheetsConnector
        connector = GoogleSheetsConnector()
    elif name == "quickbooks":
        from app.connectors.quickbooks_connector import QuickBooksConnector
        connector = QuickBooksConnector()
    elif name == "tally":
        from app.connectors.tally_connector import TallyConnector
        connector = TallyConnector()
    else:
        raise ValueError(f"Unknown connector: {name}")

    _CONNECTOR_CACHE[name] = connector
    return connector
