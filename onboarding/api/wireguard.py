"""api/wireguard.py — JSON endpoints for WireGuard management"""
from flask import Blueprint, jsonify
from core import wireguard
from routes.auth import login_required

wg_api_bp = Blueprint("wg_api", __name__, url_prefix="/api/wg")


@wg_api_bp.route("/peers")
@login_required
def peers():
    try:
        return jsonify({"success": True, "peers": wireguard.list_peers()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@wg_api_bp.route("/next-ip")
@login_required
def next_ip():
    return jsonify({"ip": wireguard.next_free_ip()})
