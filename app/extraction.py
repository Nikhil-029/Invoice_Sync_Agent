"""
Extraction pipeline: file -> OCR text -> structured invoice JSON via LLM.

Design:
1. OCR the uploaded file (PDF or image) to raw text with pytesseract.
2. Send the raw text to an LLM (Groq/Llama by default) with a strict JSON
   schema prompt, asking it to also self-report a confidence (0-1) per field.
3. Return a normalized dict the rest of the app can work with.

The LLM call is wrapped behind `extract_invoice_fields` so the LLM provider
can be swapped (Groq / OpenAI / local model) without touching callers.
"""
import io
import json
import os
from typing import Any, Dict, List

import pytesseract
from PIL import Image
from pdf2image import convert_from_path

from groq import Groq

TESSERACT_CMD = os.getenv("TESSERACT_CMD")
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file."
            )
        _client = Groq(api_key=api_key)
    return _client


def ocr_file(file_path: str) -> str:
    """Run OCR on a PDF or image file and return the concatenated text."""
    ext = os.path.splitext(file_path)[1].lower()
    text_chunks: List[str] = []

    if ext == ".pdf":
        pages = convert_from_path(file_path, dpi=300)
        for page in pages:
            text_chunks.append(pytesseract.image_to_string(page))
    else:
        image = Image.open(file_path)
        text_chunks.append(pytesseract.image_to_string(image))

    return "\n".join(text_chunks).strip()


EXTRACTION_SYSTEM_PROMPT = """You are an invoice data extraction engine.
You will receive raw OCR text from an invoice or receipt, which may contain
OCR noise, misaligned columns, or garbled characters.

Extract the following fields and respond with ONLY valid JSON, no markdown
fences, no commentary:

{
  "vendor_name": string or null,
  "invoice_number": string or null,
  "invoice_date": string (ISO 8601 YYYY-MM-DD) or null,
  "due_date": string (ISO 8601 YYYY-MM-DD) or null,
  "currency": string (3-letter ISO code, e.g. USD/INR/EUR) or null,
  "subtotal": number or null,
  "tax_amount": number or null,
  "total_amount": number or null,
  "line_items": [
    {"description": string, "quantity": number or null, "unit_price": number or null, "amount": number or null}
  ],
  "confidence": {
    "vendor_name": number (0-1),
    "invoice_number": number (0-1),
    "invoice_date": number (0-1),
    "total_amount": number (0-1)
  }
}

Rules:
- If a field cannot be determined, set it to null and give it a low confidence score.
- Never invent numbers that are not supported by the text.
- total_amount should equal subtotal + tax_amount when both are present; if
  the OCR text disagrees, trust the explicit "total" on the document and
  lower its confidence score.
"""


def extract_invoice_fields(ocr_text: str) -> Dict[str, Any]:
    """Send OCR text to the LLM and parse the structured JSON response."""
    client = _get_client()

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"OCR TEXT:\n\n{ocr_text}"},
        ],
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fall back to a minimal structure so the pipeline never hard-crashes
        data = {
            "vendor_name": None,
            "invoice_number": None,
            "invoice_date": None,
            "due_date": None,
            "currency": None,
            "subtotal": None,
            "tax_amount": None,
            "total_amount": None,
            "line_items": [],
            "confidence": {},
            "parse_error": True,
            "raw_response": raw,
        }
    return data


LOW_CONFIDENCE_THRESHOLD = 0.6


def is_low_confidence(confidence: Dict[str, float]) -> bool:
    if not confidence:
        return True
    return any(v < LOW_CONFIDENCE_THRESHOLD for v in confidence.values())


def process_file(file_path: str) -> Dict[str, Any]:
    """Full pipeline: OCR -> LLM extraction -> normalized result dict."""
    ocr_text = ocr_file(file_path)
    if not ocr_text:
        raise ValueError("OCR produced no text — file may be unreadable or blank.")

    fields = extract_invoice_fields(ocr_text)
    fields["_ocr_text"] = ocr_text
    fields["_low_confidence"] = is_low_confidence(fields.get("confidence", {}))
    return fields
