# Invoice → Accounting Sync Agent

Upload invoice/receipt files, review AI-extracted data in one screen, and
sync approved invoices to a pluggable accounting target — Google Sheets,
QuickBooks Online, or a local TallyPrime instance.

Built as a standalone project: runs entirely on your own machine, no
external platform dependency.

## What it does

1. **Upload** a PDF or image invoice (single or batch).
2. **OCR + LLM extraction** pulls vendor, invoice number, dates, amounts,
   and line items into structured JSON, with a confidence score per field.
3. **Review** — anything low-confidence is flagged in the UI; every field is
   editable inline before you approve it.
4. **Sync** — approved invoices are pushed to whichever connector is active
   (Sheets / QuickBooks / Tally), with duplicate detection so the same
   invoice never gets synced twice.

## Architecture

```
uploaded file
     │
     ▼
  OCR (pytesseract + pdf2image)
     │
     ▼
  LLM structuring (Groq/Llama, JSON-mode)
     │
     ▼
  SQLite (review queue, per-field confidence)
     │
     ▼
  human review + inline edit (web UI)
     │
     ▼
  AccountingConnector interface
     ├── GoogleSheetsConnector
     ├── QuickBooksConnector
     └── TallyConnector
```

The connector layer is the core design decision: the app never talks to a
vendor SDK directly. Every target implements the same `push_invoice` /
`check_duplicate` interface (`app/connectors/base.py`), so adding a new
accounting system later (Xero, Zoho Books, etc.) means writing one new file,
not touching the pipeline.

## Setup

### 1. Prerequisites

- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed
  and on your PATH (`brew install tesseract` / `apt install tesseract-ocr` /
  Windows installer)
- Poppler (needed by `pdf2image` for PDF support):
  `brew install poppler` / `apt install poppler-utils` / Windows binaries
  from the poppler releases page

### 2. Install

```bash
cd invoice-sync-agent
python -m venv venv
source venv/bin/activate    # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
```

### 3. Configure

Edit `.env`:

- `GROQ_API_KEY` — get a free key at https://console.groq.com
- `ACTIVE_CONNECTOR` — set to `sheets`, `quickbooks`, or `tally`

**For the Sheets connector** (easiest to start with):
1. Create a Google Cloud service account, enable the Sheets API, download
   its JSON key as `credentials.json` in the project root.
2. Share your target Google Sheet with the service account's email address.
3. Set `GOOGLE_SHEETS_SPREADSHEET_ID` in `.env` (the long ID in the sheet's URL).

**For QuickBooks**: requires an app registered in the Intuit developer
portal and a one-time OAuth2 consent flow to obtain a refresh token — see
`app/connectors/quickbooks_connector.py` for the fields it expects.

**For Tally**: enable Tally's HTTP XML gateway (F1 → Settings →
Connectivity → Client/Server configuration) and set `TALLY_COMPANY_NAME`
to match an open company in Tally.

### 4. Run

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000

## Demo tips

- Seed a few synthetic invoices (search "sample invoice PDF" or generate
  one) rather than real client documents.
- Deliberately test one blurry/low-quality scan to show the confidence
  flagging and manual-edit flow — that's the feature that makes this
  trustworthy for accounting, not just a novelty.
- Record a 90-second screen capture: upload → review a flagged field →
  approve → sync → show the row land in the target sheet/system.

## Deploying a public demo (Render)

The live "Try demo" version on your portfolio should run in **demo mode** —
it uses `DemoConnector`, which writes synced invoices to an in-app ledger
table instead of touching real Sheets/QuickBooks/Tally credentials. This
means the public deployment needs only one secret: your Groq API key.

1. Push this repo to GitHub (see steps above).
2. Go to https://render.com, sign in with GitHub, click **New → Blueprint**,
   and point it at this repo. Render will read `render.yaml` automatically.
3. When prompted, set `GROQ_API_KEY` to your real key — this is the only
   value you enter manually; everything else in `render.yaml` is already
   configured for demo mode.
4. Deploy. Render builds the Dockerfile (which installs Tesseract + Poppler,
   the two system packages a plain Python buildpack won't include) and
   gives you a live URL like `invoice-sync-agent-demo.onrender.com`.
5. Note: Render's free tier spins the service down after ~15 minutes of
   inactivity — the first request after idle takes 30-60s to wake up. Fine
   for a portfolio demo; mention it near the "Try demo" button so visitors
   aren't confused by the initial delay.

What `DEMO_MODE=true` changes automatically:
- Forces the `DemoConnector` regardless of `ACTIVE_CONNECTOR`, so a
  misconfigured public deploy can never leak real accounting credentials
- Shows a banner in the UI explaining synced rows go to a demo ledger
- Rate-limits uploads per visitor (`DEMO_MAX_UPLOADS_PER_HOUR`, default 8)
  so a public link can't silently drain your Groq quota
- Displays the "synced" ledger table directly on the page, so a visitor
  sees the full loop (upload → review → approve → sync → appears in ledger)
  without you exposing any real system

## Possible extensions

- Vendor auto-creation in QuickBooks before pushing bills
- Tally duplicate detection via the Voucher Register report API
- Batch approve / batch edit
- Webhook or scheduled folder-watch for fully hands-off ingestion
