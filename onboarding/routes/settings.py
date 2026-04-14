"""routes/settings.py — WireGuard peers + VPS config overview"""
from flask import Blueprint, render_template
from db.models import Router
from core import wireguard
from config import Config
from routes.auth import login_required

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/")
@login_required
def index():
    peers, wg_err = [], None
    try:
        peers = wireguard.list_peers()
    except Exception as e:
        wg_err = str(e)
    wg_routers = Router.query.filter_by(connection_type="wireguard").all()
    return render_template("settings.html",
                           peers=peers,
                           wg_err=wg_err,
                           routers=wg_routers,
                           wg_iface=Config.WG_INTERFACE,
                           vps_wg_ip=Config.VPS_WG_IP)
