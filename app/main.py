from fastapi import FastAPI
from app.routes.webhook import router as webhook_router

app = FastAPI(title="ZivoPay WhatsApp Invoice Bot", version="2.0.0")

app.include_router(webhook_router, prefix="/webhook", tags=["Webhook"])


@app.get("/")
def health_check():
    return {"status": "running", "bot": "ZivoPay Invoice Bot"}
