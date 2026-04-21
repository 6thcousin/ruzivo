from fastapi import FastAPI
from app.routes.webhook import router as webhook_router
from app.routes.wireguard import router as wireguard_router

app = FastAPI(title="ZivoPay WhatsApp Invoice Bot", version="2.0.0")

app.include_router(webhook_router, prefix="/webhook", tags=["Webhook"])
app.include_router(wireguard_router, prefix="/wireguard", tags=["WireGuard"])


@app.get("/")
def health_check():
    return {"status": "running", "bot": "ZivoPay Invoice Bot"}
