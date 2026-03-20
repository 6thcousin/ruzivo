from pydantic import BaseModel, Field
from typing import Any, Optional


class WhatsAppTextBody(BaseModel):
    body: str


# ── Button reply ──────────────────────────────────────────────────────────────

class WhatsAppButtonReply(BaseModel):
    id:    str
    title: str


# ── Flow / NFM reply ──────────────────────────────────────────────────────────

class WhatsAppNFMReply(BaseModel):
    response_json: str
    body:          str
    name:          str


# ── Interactive (covers button_reply and nfm_reply) ───────────────────────────

class WhatsAppInteractive(BaseModel):
    type:         str
    button_reply: Optional[WhatsAppButtonReply] = None
    nfm_reply:    Optional[WhatsAppNFMReply]    = None


# ── Catalog order ─────────────────────────────────────────────────────────────

class WhatsAppOrderItem(BaseModel):
    product_retailer_id: str
    quantity:            int
    item_price:          float
    currency:            str


class WhatsAppOrder(BaseModel):
    catalog_id:    str
    text:          Optional[str] = None
    product_items: list[WhatsAppOrderItem]


# ── Core message ──────────────────────────────────────────────────────────────

class WhatsAppMessage(BaseModel):
    id:          str
    from_:       str = Field(alias="from")
    timestamp:   str
    type:        str
    text:        Optional[WhatsAppTextBody]    = None
    interactive: Optional[WhatsAppInteractive] = None
    order:       Optional[WhatsAppOrder]       = None

    model_config = {"populate_by_name": True}


# ── Webhook envelope ──────────────────────────────────────────────────────────

class WhatsAppContact(BaseModel):
    profile: dict[str, Any]
    wa_id:   str


class WhatsAppValue(BaseModel):
    messaging_product: Optional[str]            = None   # absent in non-message events
    metadata:          Optional[dict[str, Any]] = None   # absent in non-message events
    contacts:          Optional[list[WhatsAppContact]] = None
    messages:          Optional[list[WhatsAppMessage]] = None

    model_config = {"extra": "allow"}   # silently ignore unknown fields (e.g. FLOW_STATUS_CHANGE)


class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str


class WhatsAppEntry(BaseModel):
    id:      str
    changes: list[WhatsAppChange]


class WebhookPayload(BaseModel):
    object: str
    entry:  list[WhatsAppEntry]
