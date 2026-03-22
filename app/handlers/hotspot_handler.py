"""
WhatsApp conversation flow for collecting client data and generating
a personalized MikroTik hotspot login page.

States
------
HOTSPOT_NAME       — waiting for company name
HOTSPOT_LOGO       — waiting for logo URL (or "skip")
HOTSPOT_WIFI       — waiting for WiFi / hotspot name
HOTSPOT_VOUCHER    — waiting for "where to buy voucher" text
HOTSPOT_PAYMENT    — showing payment-method buttons
HOTSPOT_CONFIRM    — showing summary + confirm button
"""

from pathlib import Path

from app.services.session_manager import session_manager
from app.services.whatsapp import (
    send_text_message, send_buttons,
    upload_media, send_document,
)
from app.services.hotspot_generator import generate_hotspot_page

# ── State constants ────────────────────────────────────────────────────────────

S_HOTSPOT_NAME    = "HOTSPOT_NAME"
S_HOTSPOT_LOGO    = "HOTSPOT_LOGO"
S_HOTSPOT_WIFI    = "HOTSPOT_WIFI"
S_HOTSPOT_VOUCHER = "HOTSPOT_VOUCHER"
S_HOTSPOT_PAYMENT = "HOTSPOT_PAYMENT"
S_HOTSPOT_CONFIRM = "HOTSPOT_CONFIRM"


# ── Entry point (called when user taps "Mikrotik" button) ─────────────────────

async def start_hotspot_setup(sender: str, session: dict) -> None:
    session["state"] = S_HOTSPOT_NAME
    session["data"]  = {}
    session_manager.save(sender, session)

    await send_text_message(
        sender,
        "🛜 *Hotspot Login Page Setup*\n\n"
        "I'll collect a few details to build your personalised login page.\n\n"
        "First, what is the *company / business name*?\n"
        "_e.g. Cafe Harare_"
    )


# ── Step-by-step text collectors ──────────────────────────────────────────────

async def handle_hotspot_name(sender: str, session: dict, text: str) -> None:
    session["data"]["company_name"] = text.strip()
    session["state"] = S_HOTSPOT_LOGO
    session_manager.save(sender, session)

    await send_text_message(
        sender,
        f"✅ *{text.strip()}* — got it!\n\n"
        "Now send the *public URL* of your company logo\n"
        "_(paste a direct image link)_\n\n"
        "Or type *skip* to leave the logo out."
    )


async def handle_hotspot_logo(sender: str, session: dict, text: str) -> None:
    logo = "" if text.strip().lower() == "skip" else text.strip()
    session["data"]["company_logo_url"] = logo
    session["state"] = S_HOTSPOT_WIFI
    session_manager.save(sender, session)

    await send_text_message(
        sender,
        "What is the *WiFi / hotspot name* customers will see?\n"
        "_e.g. CafeHarare_Free_"
    )


async def handle_hotspot_wifi(sender: str, session: dict, text: str) -> None:
    session["data"]["wifi_name"] = text.strip()
    session["state"] = S_HOTSPOT_VOUCHER
    session_manager.save(sender, session)

    await send_text_message(
        sender,
        "Where can customers *buy a voucher*?\n"
        "_e.g. At the counter, or WhatsApp 0771 234 567_\n\n"
        "Or type *skip* to leave this out."
    )


async def handle_hotspot_voucher(sender: str, session: dict, text: str) -> None:
    voucher = "" if text.strip().lower() == "skip" else text.strip()
    session["data"]["voucher_location"] = voucher
    session["state"] = S_HOTSPOT_PAYMENT
    session_manager.save(sender, session)

    await send_buttons(
        to=sender,
        body="Which *payment methods* do you accept for vouchers?",
        buttons=[
            {"id": "hs_pay_both",    "title": "EcoCash & Cash"},
            {"id": "hs_pay_ecocash", "title": "EcoCash only"},
            {"id": "hs_pay_cash",    "title": "Cash only"},
        ],
        footer="Choose one — or type 'none' to skip"
    )


# ── Payment button handler (called from message_handler button router) ─────────

async def handle_hotspot_payment_button(
    sender: str, session: dict, btn_id: str
) -> None:
    mapping = {
        "hs_pay_both":    ["ecocash", "cash"],
        "hs_pay_ecocash": ["ecocash"],
        "hs_pay_cash":    ["cash"],
    }
    session["data"]["payment_modes"] = mapping.get(btn_id, [])
    session["state"] = S_HOTSPOT_CONFIRM
    session_manager.save(sender, session)

    await _send_confirmation(sender, session["data"])


async def handle_hotspot_payment_text(
    sender: str, session: dict, text: str
) -> None:
    """Handle 'none' / 'skip' typed during payment step."""
    session["data"]["payment_modes"] = []
    session["state"] = S_HOTSPOT_CONFIRM
    session_manager.save(sender, session)

    await _send_confirmation(sender, session["data"])


async def _send_confirmation(sender: str, data: dict) -> None:
    pay = ", ".join(data.get("payment_modes", [])).upper() or "None"
    logo_line = data.get("company_logo_url") or "_(no logo)_"
    voucher_line = data.get("voucher_location") or "_(not set)_"

    summary = (
        "📋 *Here's your hotspot page summary:*\n\n"
        f"🏢 Business name:  *{data['company_name']}*\n"
        f"🖼️ Logo URL:        {logo_line}\n"
        f"📶 WiFi name:       *{data['wifi_name']}*\n"
        f"🎟️ Voucher info:    {voucher_line}\n"
        f"💳 Payments:        *{pay}*\n\n"
        "Tap *Confirm* to generate your login page, or *Start Over* to redo."
    )

    await send_buttons(
        to=sender,
        body=summary,
        buttons=[
            {"id": "hs_confirm",    "title": "✅ Confirm"},
            {"id": "hs_start_over", "title": "🔄 Start Over"},
        ],
    )


# ── Final step — generate HTML and send it ────────────────────────────────────

async def handle_hotspot_confirm(sender: str, session: dict) -> None:
    data = session.get("data", {})

    await send_text_message(sender, "⏳ Generating your login page...")

    try:
        out_file: Path = generate_hotspot_page(data)
        media_id       = await upload_media(str(out_file), "text/html")

        slug = out_file.parent.name
        await send_document(
            to=sender,
            media_id=media_id,
            filename="login.html",
            caption=(
                f"✅ *Your hotspot login page is ready!*\n\n"
                f"📁 Filename: `login.html`\n\n"
                f"*Upload to MikroTik:*\n"
                f"1. Open Winbox → Files\n"
                f"2. Upload `login.html` to the *hotspot* folder\n"
                f"3. Rename it to `login.html` if asked\n\n"
                f"Powered by *ZivoPay Myzivo* 🛜"
            ),
        )
    except Exception as exc:
        await send_text_message(
            sender,
            f"❌ Something went wrong generating the page:\n{exc}\n\n"
            "Please try again or contact support."
        )
        return

    # Reset session
    session["state"] = "IDLE"
    session["data"]  = {}
    session_manager.save(sender, session)
