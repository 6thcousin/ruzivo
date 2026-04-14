"""config.py — all configuration in one place"""
import os

class Config:
    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY   = os.environ.get("SECRET_KEY",   "zivopay-change-me-2026")
    ADMIN_USER   = os.environ.get("ADMIN_USER",   "admin")
    ADMIN_PASS   = os.environ.get("ADMIN_PASS",   "zivopay2026")

    # ── Database ──────────────────────────────────────────────────────────────
    _HERE        = os.path.dirname(os.path.abspath(__file__))
    DB_PATH      = os.path.join(_HERE, "data", "onboarding.db")
    SQLALCHEMY_DATABASE_URI       = f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── WireGuard ─────────────────────────────────────────────────────────────
    WG_INTERFACE = os.environ.get("WG_INTERFACE", "wg0")
    WG_CONF      = os.environ.get("WG_CONF",      "/etc/wireguard/wg0.conf")
    VPS_WG_IP    = os.environ.get("VPS_WG_IP",    "10.0.0.1")
    WG_SUBNET    = os.environ.get("WG_SUBNET",    "10.0.0.0/24")

    # ── App ───────────────────────────────────────────────────────────────────
    PORT         = int(os.environ.get("PORT", 5001))
    DEBUG        = os.environ.get("DEBUG", "true").lower() == "true"
