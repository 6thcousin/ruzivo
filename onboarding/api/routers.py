"""api/routers.py — JSON endpoints for router commands and stats"""
from flask import Blueprint, jsonify, request
from db import db
from db.models import CommandLog, Router
from core import mikrotik
from routes.auth import login_required

routers_api_bp = Blueprint("routers_api", __name__, url_prefix="/api/routers")


@routers_api_bp.route("/<int:router_id>/test")
@login_required
def test(router_id):
    r = Router.query.get_or_404(router_id)
    return jsonify(mikrotik.test_connection(r.host, r.port, r.username, r.password))


@routers_api_bp.route("/<int:router_id>/stats")
@login_required
def stats(router_id):
    r = Router.query.get_or_404(router_id)
    return jsonify(mikrotik.get_stats(r.host, r.port, r.username, r.password))


@routers_api_bp.route("/<int:router_id>/command", methods=["POST"])
@login_required
def command(router_id):
    r       = Router.query.get_or_404(router_id)
    cmd_key = request.form.get("cmd_key", "")
    raw     = request.form.get("raw_cmd", "").strip()

    if raw:
        result    = mikrotik.run_raw(r.host, r.port, r.username, r.password, raw)
        cmd_label = raw
    else:
        result    = mikrotik.run_command(r.host, r.port, r.username, r.password, cmd_key)
        cmd_label = mikrotik.COMMANDS.get(cmd_key, ("?",))[0]

    db.session.add(CommandLog(
        router_id = router_id,
        command   = cmd_label,
        output    = result.get("output", ""),
        status    = "success" if result.get("success") else "error",
    ))
    db.session.commit()
    return jsonify(result)


@routers_api_bp.route("/<int:router_id>/reboot", methods=["POST"])
@login_required
def reboot(router_id):
    r      = Router.query.get_or_404(router_id)
    result = mikrotik.run_command(r.host, r.port, r.username, r.password, "reboot")
    db.session.add(CommandLog(router_id=router_id, command="reboot",
                              output=result.get("output", ""),
                              status="success" if result["success"] else "error"))
    db.session.commit()
    return jsonify(result)


@routers_api_bp.route("/test-adhoc", methods=["POST"])
@login_required
def test_adhoc():
    host = request.form.get("host", "").strip()
    if not host:
        return jsonify({"success": False, "error": "No host provided"})
    return jsonify(mikrotik.test_connection(
        host,
        request.form.get("port", 8728),
        request.form.get("username", "admin"),
        request.form.get("password", ""),
    ))
