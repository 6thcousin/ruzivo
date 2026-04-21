"""
ZivoPay Onboarding — app.py
"""

import os

from flask import Flask, jsonify, request, session

from db import db
from db.models import Client, CommandLog, Router
import router_api
import wg_manager
from routes import blueprints
from routes.auth import login_required

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "zivopay-onboarding-change-me-2026")

_HERE = os.path.dirname(os.path.abspath(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{_HERE}/data/onboarding.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
os.makedirs(os.path.join(_HERE, "data"), exist_ok=True)

with app.app_context():
    db.create_all()

# ── Register blueprints ───────────────────────────────────────────────────────

for bp in blueprints:
    app.register_blueprint(bp)


# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/api/routers/<int:router_id>/test")
@login_required
def api_test(router_id):
    r = Router.query.get_or_404(router_id)
    return jsonify(router_api.test_connection(r.host, r.port, r.username, r.password))


@app.route("/api/routers/<int:router_id>/stats")
@login_required
def api_stats(router_id):
    r = Router.query.get_or_404(router_id)
    return jsonify(router_api.get_stats(r.host, r.port, r.username, r.password))


@app.route("/api/routers/<int:router_id>/command", methods=["POST"])
@login_required
def api_command(router_id):
    r       = Router.query.get_or_404(router_id)
    cmd_key = request.form.get("cmd_key", "")
    raw     = request.form.get("raw_cmd", "").strip()

    if raw:
        result    = router_api.run_raw(r.host, r.port, r.username, r.password, raw)
        cmd_label = raw
    else:
        result    = router_api.run_command(r.host, r.port, r.username, r.password, cmd_key)
        cmd_label = router_api.COMMANDS.get(cmd_key, ("?",))[0] if cmd_key else "?"

    log = CommandLog(
        router_id=router_id,
        command=cmd_label,
        output=result.get("output", ""),
        status="success" if result.get("success") else "error",
    )
    db.session.add(log)
    db.session.commit()
    return jsonify(result)


@app.route("/api/routers/<int:router_id>/reboot", methods=["POST"])
@login_required
def api_reboot(router_id):
    r      = Router.query.get_or_404(router_id)
    result = router_api.run_command(r.host, r.port, r.username, r.password, "reboot")
    log    = CommandLog(
        router_id=router_id,
        command="reboot",
        output=result.get("output", ""),
        status="success" if result["success"] else "error",
    )
    db.session.add(log)
    db.session.commit()
    return jsonify(result)


@app.route("/api/wg/peers")
@login_required
def api_wg_peers():
    try:
        peers = wg_manager.list_peers()
        return jsonify({"success": True, "peers": peers})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/wg/next-ip")
@login_required
def api_wg_next_ip():
    ip = wg_manager.next_free_ip()
    return jsonify({"ip": ip})


@app.route("/api/test-adhoc", methods=["POST"])
@login_required
def api_test_adhoc():
    host = request.form.get("host", "").strip()
    port = int(request.form.get("port", 8728))
    user = request.form.get("username", "admin")
    pw   = request.form.get("password", "")
    if not host:
        return jsonify({"success": False, "error": "No host provided"})
    return jsonify(router_api.test_connection(host, port, user, pw))


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  ZivoPay Onboarding  →  http://localhost:{port}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
