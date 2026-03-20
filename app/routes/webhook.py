from fastapi import APIRouter, Request, HTTPException, Query
from app.config import settings
from app.models.webhook import WebhookPayload
from app.handlers.message_handler import handle_message

router = APIRouter()


@router.get("")
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
):
    """Meta webhook verification handshake."""
    if hub_mode == "subscribe" and hub_verify_token == settings.verify_token:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("")
async def receive_message(request: Request):
    """Receive and process incoming WhatsApp messages."""
    body = await request.json()

    try:
        payload = WebhookPayload(**body)
    except Exception as exc:
        # Unknown / non-message webhook event (e.g. FLOW_STATUS_CHANGE).
        # Always return 200 so Meta doesn't retry.
        print(f"[WEBHOOK] Ignored unrecognised payload: {exc}")
        return {"status": "ok"}

    for entry in payload.entry:
        for change in entry.changes:
            if change.field != "messages":
                continue
            messages = change.value.messages or []
            for message in messages:
                await handle_message(message)

    return {"status": "ok"}
