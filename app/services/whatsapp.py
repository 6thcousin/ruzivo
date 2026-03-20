import os
import httpx
from app.config import settings


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }


_TIMEOUT = httpx.Timeout(connect=15.0, read=30.0, write=30.0, pool=5.0)


async def _post(payload: dict, label: str) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            settings.whatsapp_api_url, headers=_headers(), json=payload
        )
        if not response.is_success:
            print(f"[WA] {label} error {response.status_code}: {response.text}")
        response.raise_for_status()
        return response.json()


# ── Text ──────────────────────────────────────────────────────────────────────

async def send_text_message(to: str, message: str) -> dict:
    return await _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }, "send_text")


# ── Interactive reply buttons (max 3) ─────────────────────────────────────────

async def send_buttons(
    to: str,
    body: str,
    buttons: list[dict],
    header: str | None = None,
    footer: str | None = None,
) -> dict:
    """
    Send an interactive reply-buttons message.
    Each button dict: {"id": "unique_id", "title": "Label (max 20 chars)"}
    """
    interactive: dict = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                for b in buttons[:3]
            ]
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": header}
    if footer:
        interactive["footer"] = {"text": footer}

    return await _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    }, "send_buttons")


# ── Catalog message ───────────────────────────────────────────────────────────

async def send_catalog_message(to: str) -> dict:
    """
    Send an interactive catalog message.
    Opens the product catalog linked to the WABA so the user can browse and cart items.
    """
    return await _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "catalog_message",
            "body": {
                "text": (
                    "🛍️ Browse our product catalog below.\n"
                    "Add the items you need to your cart, "
                    "then tap *Send* when you're done."
                )
            },
            "action": {
                "name": "catalog_message",
            },
        },
    }, "send_catalog")


# ── Flow message ──────────────────────────────────────────────────────────────

async def send_flow(to: str, flow_token: str) -> dict:
    parameters = {
        "flow_message_version": "3",
        "flow_token":           flow_token,
        "flow_id":              settings.flow_id,
        "flow_cta":             "Generate Invoice",
        "flow_action":          "navigate",
        "flow_action_payload":  {"screen": "COMPANY_INFO"},
    }
    if settings.flow_mode == "draft":
        parameters["mode"] = "draft"

    return await _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "header": {"type": "text", "text": "ZivoPay Invoice Generator"},
            "body":   {"text": "Generate a professional invoice in seconds. 📄"},
            "footer": {"text": "Powered by ZivoPay"},
            "action": {"name": "flow", "parameters": parameters},
        },
    }, "send_flow")


# ── Media helpers ─────────────────────────────────────────────────────────────

async def get_media_url(media_id: str) -> str:
    auth_headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(
            f"https://graph.facebook.com/{settings.api_version}/{media_id}",
            headers=auth_headers,
        )
        response.raise_for_status()
        return response.json()["url"]


async def download_media(media_url: str, save_path: str) -> str:
    auth_headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(media_url, headers=auth_headers)
        response.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(response.content)
    return save_path


async def upload_media(file_path: str, mime_type: str) -> str:
    auth_headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=15.0, read=60.0, write=60.0, pool=5.0)) as client:
        with open(file_path, "rb") as f:
            response = await client.post(
                settings.whatsapp_media_url,
                headers=auth_headers,
                data={"messaging_product": "whatsapp", "type": mime_type},
                files={"file": (os.path.basename(file_path), f, mime_type)},
            )
        if not response.is_success:
            print(f"[WA] upload_media error {response.status_code}: {response.text}")
        response.raise_for_status()
        return response.json()["id"]


async def get_product_name(retailer_id: str) -> str:
    """
    Look up a product's display name from the Meta Commerce Catalog by retailer_id.
    Returns the name string, or falls back to the retailer_id if not found.
    """
    try:
        url = (
            f"https://graph.facebook.com/{settings.api_version}"
            f"/{settings.catalog_id}/products"
        )
        params = {
            "access_token": settings.whatsapp_token,
            "filter":       f'{{"retailer_id":{{"eq":"{retailer_id}"}}}}',
            "fields":       "name,price,currency",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(url, params=params)
            data = r.json().get("data", [])
            if data:
                return data[0].get("name", retailer_id)
    except Exception as exc:
        print(f"[WA] get_product_name error: {exc}")
    return retailer_id   # fallback to SKU if lookup fails


async def send_document(to: str, media_id: str, filename: str, caption: str = "") -> dict:
    return await _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "document",
        "document": {"id": media_id, "filename": filename, "caption": caption},
    }, "send_document")
