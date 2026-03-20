import json
import os
import asyncio

from app.services.pdf_generator import generate_pdf, ASSETS_DIR
from app.services.file_packager import create_invoice_zip
from app.services.whatsapp import (
    send_text_message, upload_media, send_document,
    get_media_url, download_media,
)


# ── Field mapping ─────────────────────────────────────────────────────────────

def _map_flow_to_pdf(data: dict) -> dict:
    """Map WhatsApp Flow response fields → pdf_generator data format."""

    # Build line items (up to 5)
    items = []
    for i in range(1, 6):
        desc = (data.get(f"item{i}_description") or "").strip()
        if not desc:
            continue
        try:
            qty   = float(data.get(f"item{i}_quantity")   or 0)
            price = float(data.get(f"item{i}_unit_price") or 0)
        except (ValueError, TypeError):
            continue
        if qty > 0:
            items.append({
                "description": desc,
                "qty":         qty,
                "unit_price":  price,
                "total":       round(qty * price, 2),
            })

    # Build customer address from parts
    addr_parts = filter(None, [
        data.get("customer_address", ""),
        data.get("customer_city",    ""),
        data.get("customer_country", ""),
    ])
    customer_address = ", ".join(addr_parts)

    return {
        "doc_type":         "Invoice",
        "company_name":     data.get("company_name",    ""),
        "company_email":    data.get("company_email",   ""),
        "company_phone":    data.get("company_phone",   ""),
        "company_website":  data.get("company_website", ""),
        "company_logo":     data.get("company_logo"),       # media_id or None
        "client_name":      data.get("customer_name",    "Client"),
        "client_email":     data.get("customer_email",   ""),
        "client_phone":     data.get("customer_phone",   ""),
        "client_company":   data.get("customer_company", ""),
        "client_address":   customer_address,
        "invoice_number":   data.get("invoice_number",  ""),
        "invoice_date":     data.get("invoice_date",    ""),
        "due_date":         data.get("due_date",        ""),
        "currency":         data.get("currency",        "USD"),
        "tax_number":       data.get("tax_number",      ""),
        "tax_rate":         data.get("tax_rate",        0),
        "items":            items,
        "payment_terms":    data.get("payment_terms",   ""),
        "banking_details":  data.get("payment_details", ""),
        "notes":            data.get("notes",           ""),
        "po_number":        data.get("po_number",       ""),
    }


# ── Logo resolver ─────────────────────────────────────────────────────────────

async def _resolve_logo(logo_data) -> str | None:
    """
    If the user uploaded a logo via the Flow's PhotoPicker, download it.
    logo_data may be a media_id string or a dict with an 'id' key.
    Returns local file path on success, None on failure.
    """
    if not logo_data:
        return None
    try:
        media_id = logo_data if isinstance(logo_data, str) else logo_data.get("id")
        if not media_id:
            return None
        media_url = await get_media_url(media_id)
        save_path = os.path.join(ASSETS_DIR, f"logo_upload_{media_id[:8]}.jpg")
        os.makedirs(ASSETS_DIR, exist_ok=True)
        await download_media(media_url, save_path)
        print(f"[LOGO] Downloaded to: {save_path}")
        return save_path
    except Exception as exc:
        print(f"[LOGO] Could not download logo: {exc}")
        return None


# ── Main handler ──────────────────────────────────────────────────────────────

async def handle_flow_submission(sender: str, response_json: str) -> None:
    """
    End-to-end handler for a completed invoice Flow submission:
      1. Parse and map form data
      2. Optionally download uploaded company logo
      3. Generate PDF invoice
      4. Package into ZIP
      5. Upload both files to WhatsApp
      6. Send them back to the user
    """
    try:
        data     = json.loads(response_json)
        pdf_data = _map_flow_to_pdf(data)

        # Resolve uploaded logo (if any)
        logo_path = await _resolve_logo(pdf_data.get("company_logo"))
        if logo_path:
            pdf_data["company_logo_path"] = logo_path

        await send_text_message(sender, "⏳ Generating your invoice, please wait a moment...")

        # Run blocking PDF generation off the event loop
        loop     = asyncio.get_event_loop()
        pdf_path = await loop.run_in_executor(None, generate_pdf, pdf_data)

        # Package into ZIP
        zip_path = await loop.run_in_executor(None, create_invoice_zip, pdf_path, logo_path)

        # Upload both files to WhatsApp media API
        pdf_media_id = await upload_media(pdf_path, "application/pdf")
        zip_media_id = await upload_media(zip_path, "application/zip")

        client_name = pdf_data.get("client_name", "Client")

        # Send PDF
        await send_document(
            sender,
            pdf_media_id,
            os.path.basename(pdf_path),
            f"📄 Invoice for {client_name}",
        )

        # Send ZIP
        await send_document(
            sender,
            zip_media_id,
            os.path.basename(zip_path),
            "🗜️ Invoice package (PDF + assets)",
        )

        await send_text_message(
            sender,
            "✅ All done! Your invoice has been delivered.\n\n"
            "Send *hi* to generate another one.",
        )

    except Exception as exc:
        print(f"[FLOW] Error processing submission: {exc}")
        await send_text_message(
            sender,
            "❌ Something went wrong while generating your invoice.\n"
            "Please try again or send *hi* to restart.",
        )
