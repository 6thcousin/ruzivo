import asyncio
import os

from app.services.session_manager import session_manager
from app.services.whatsapp import (
    send_text_message, send_buttons, send_catalog_message,
    upload_media, send_document, get_product_name,
)
from app.services.pdf_generator import generate_pdf
from app.models.webhook import WhatsAppMessage

# ── States ────────────────────────────────────────────────────────────────────
S_IDLE             = "IDLE"
S_QUOTE_PRODUCTS   = "QUOTE_PRODUCTS"   # waiting for user to send catalog order
S_QUOTE_CONFIRM    = "QUOTE_CONFIRM"    # showing selected items, waiting confirm
S_QUOTE_NAME       = "QUOTE_NAME"       # asking for client name
S_QUOTE_ADDRESS    = "QUOTE_ADDRESS"    # asking for address
S_QUOTE_PHONE      = "QUOTE_PHONE"      # asking for phone number


# ── Step 1 — Show intro & Let's Start button ──────────────────────────────────

async def start_quote(sender: str, session: dict) -> None:
    session["state"] = S_QUOTE_PRODUCTS
    session["data"]  = {}
    session_manager.save(sender, session)

    await send_buttons(
        to=sender,
        body=(
            "📋 *Here's how it works:*\n\n"
            "1️⃣  Browse our product catalog\n"
            "2️⃣  Add the items you need to your cart\n"
            "3️⃣  Send your cart to us\n"
            "4️⃣  We confirm & generate your quote PDF instantly\n\n"
            "Ready to get started? 👇"
        ),
        buttons=[{"id": "btn_start_quote", "title": "Select Products"}],
        footer="Powered by ZivoPay",
    )


# ── Step 2 — Send product catalog ─────────────────────────────────────────────

async def send_products(sender: str, session: dict) -> None:
    session["state"] = S_QUOTE_PRODUCTS
    session_manager.save(sender, session)
    try:
        await send_catalog_message(sender)
    except Exception as exc:
        print(f"[QUOTE] Catalog error: {exc}")
        await send_text_message(
            sender,
            "⚠️ Could not open the product catalog right now.\n\n"
            "This usually means the catalog has no products yet, or it isn't "
            "linked to this WhatsApp number.\n\n"
            "Please check your Meta Commerce Manager and try again."
        )


# ── Step 3 — Receive order from catalog ───────────────────────────────────────

async def handle_order(sender: str, session: dict, message: WhatsAppMessage) -> None:
    order = message.order

    if not order or not order.product_items:
        await send_text_message(
            sender,
            "⚠️ No items received. Please browse the catalog and add products to your cart."
        )
        return

    # Look up real product names from the catalog (best-effort, falls back to retailer_id)
    items = []
    for item in order.product_items:
        name = await get_product_name(item.product_retailer_id)
        items.append({
            "description": name,
            "qty":         float(item.quantity),
            "unit_price":  item.item_price,
            "total":       round(item.quantity * item.item_price, 2),
            "currency":    item.currency,
        })
    session["data"]["order_items"] = items
    session["data"]["currency"]    = order.product_items[0].currency if order.product_items else "USD"
    session["state"] = S_QUOTE_CONFIRM
    session_manager.save(sender, session)

    # Build summary
    lines    = "\n".join(f"• {i['description']}  x{int(i['qty'])}  —  ${i['total']:.2f}" for i in items)
    subtotal = sum(i["total"] for i in items)

    await send_buttons(
        to=sender,
        body=(
            f"🛒 *Here's what you selected:*\n\n"
            f"{lines}\n\n"
            f"*Subtotal: ${subtotal:.2f}*\n\n"
            "Does this look right?"
        ),
        buttons=[
            {"id": "btn_confirm_products", "title": "Confirm ✅"},
            {"id": "btn_change_products",  "title": "Change Products"},
        ],
    )


# ── Step 4 — Collect client details ──────────────────────────────────────────

async def ask_name(sender: str, session: dict) -> None:
    session["state"] = S_QUOTE_NAME
    session_manager.save(sender, session)
    await send_text_message(sender, "👤 What *name* should appear on the quote?")


async def handle_name(sender: str, session: dict, text: str) -> None:
    session["data"]["client_name"] = text.strip().title()
    session["state"] = S_QUOTE_ADDRESS
    session_manager.save(sender, session)
    await send_text_message(sender, "🏠 What is your *delivery address* or city?")


async def handle_address(sender: str, session: dict, text: str) -> None:
    session["data"]["client_address"] = text.strip()
    session["state"] = S_QUOTE_PHONE
    session_manager.save(sender, session)
    await send_text_message(sender, "📞 What is your *phone number*?")


async def handle_phone(sender: str, session: dict, text: str) -> None:
    session["data"]["client_phone"] = text.strip()
    session["state"] = S_IDLE
    session_manager.save(sender, session)

    await _generate_and_send(sender, session["data"])


# ── Step 5 — Generate & send quote PDF ────────────────────────────────────────

async def _generate_and_send(sender: str, data: dict) -> None:
    await send_text_message(sender, "⏳ Generating your quote, please wait a moment...")

    pdf_data = {
        "doc_type":      "Quotation",
        "client_name":   data.get("client_name",   "Client"),
        "client_phone":  data.get("client_phone",  ""),
        "client_address":data.get("client_address",""),
        "items":         data.get("order_items",   []),
        "currency":      data.get("currency",      "USD"),
        "payment_terms": "Due on Receipt",
    }

    try:
        loop     = asyncio.get_event_loop()
        pdf_path = await loop.run_in_executor(None, generate_pdf, pdf_data)

        pdf_media_id = await upload_media(pdf_path, "application/pdf")

        client_name = pdf_data["client_name"]
        await send_document(sender, pdf_media_id, os.path.basename(pdf_path), f"📄 Quote for {client_name}")
        await send_text_message(
            sender,
            "✅ Your quote has been sent!\n\nSend *hi* to create another one."
        )

    except Exception as exc:
        print(f"[QUOTE] PDF error: {exc}")
        await send_text_message(
            sender,
            "❌ Something went wrong generating your quote. Please try again or send *hi* to restart."
        )
