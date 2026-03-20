import uuid

from app.models.webhook import WhatsAppMessage
from app.services.whatsapp import send_text_message, send_buttons
from app.services.session_manager import session_manager
from app.handlers.flow_handler import handle_flow_submission
from app.handlers.quote_handler import (
    start_quote, send_products, handle_order,
    ask_name, handle_name, handle_address, handle_phone,
    S_QUOTE_PRODUCTS, S_QUOTE_CONFIRM,
    S_QUOTE_NAME, S_QUOTE_ADDRESS, S_QUOTE_PHONE,
)

# ── Main menu ─────────────────────────────────────────────────────────────────

WELCOME = (
    "👋 Welcome to *ZivoPay*!\n\n"
    "How can we help you today?"
)

MENU_BUTTONS = [
    {"id": "btn_mikrotik",  "title": "Mikrotik"},
    {"id": "btn_get_quote", "title": "Get Quote"},
    {"id": "btn_livechat",  "title": "Live Chat"},
]


async def send_main_menu(sender: str) -> None:
    await send_buttons(
        to=sender,
        body=WELCOME,
        buttons=MENU_BUTTONS,
        footer="Powered by ZivoPay",
    )


# ── Main router ───────────────────────────────────────────────────────────────

async def handle_message(message: WhatsAppMessage) -> None:
    sender  = message.from_
    session = session_manager.get(sender)
    state   = session.get("state", "IDLE")

    # ── Interactive messages (button clicks & flow submissions) ───────────────
    if message.type == "interactive" and message.interactive:
        interactive = message.interactive

        # WhatsApp Flow form submitted
        if interactive.type == "nfm_reply" and interactive.nfm_reply:
            await handle_flow_submission(sender, interactive.nfm_reply.response_json)
            return

        # Reply button clicked
        if interactive.type == "button_reply" and interactive.button_reply:
            await _handle_button(sender, session, state, interactive.button_reply.id)
            return

    # ── Catalog order (user sent their cart) ──────────────────────────────────
    if message.type == "order":
        if state == S_QUOTE_PRODUCTS:
            await handle_order(sender, session, message)
        else:
            await send_text_message(sender, "👋 Send *hi* to start a new quote.")
        return

    # ── Text messages ─────────────────────────────────────────────────────────
    if message.type != "text" or not message.text:
        return

    text = message.text.body.strip()

    # State-based text collection
    if state == S_QUOTE_NAME:
        await handle_name(sender, session, text)
        return

    if state == S_QUOTE_ADDRESS:
        await handle_address(sender, session, text)
        return

    if state == S_QUOTE_PHONE:
        await handle_phone(sender, session, text)
        return

    # Default: show main menu on any greeting
    if text.lower() in ("hi", "hello", "hey", "start", "menu"):
        session["state"] = "IDLE"
        session_manager.save(sender, session)
        await send_main_menu(sender)
    else:
        await send_text_message(sender, "👋 Send *hi* to see the main menu.")


# ── Button router ─────────────────────────────────────────────────────────────

async def _handle_button(sender: str, session: dict, state: str, btn_id: str) -> None:

    # ── Main menu buttons ─────────────────────────────────────────────────────
    if btn_id == "btn_get_quote":
        await start_quote(sender, session)
        return

    if btn_id == "btn_mikrotik":
        await send_text_message(
            sender,
            "🔧 *Mikrotik* section coming soon!\n\nSend *hi* to go back to the menu."
        )
        return

    if btn_id == "btn_livechat":
        await send_text_message(
            sender,
            "💬 *Live Chat* coming soon!\n\nSend *hi* to go back to the menu."
        )
        return

    # ── Quote flow buttons ────────────────────────────────────────────────────
    if btn_id == "btn_start_quote":
        await send_products(sender, session)
        return

    if btn_id == "btn_confirm_products" and state == S_QUOTE_CONFIRM:
        await ask_name(sender, session)
        return

    if btn_id == "btn_change_products":
        await send_products(sender, session)
        return

    # ── Fallback ──────────────────────────────────────────────────────────────
    await send_main_menu(sender)
