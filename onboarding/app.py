"""
ZivoPay Onboarding — app.py
"""

import json
import os
import functools

from flask import (Flask, flash, jsonify, redirect, render_template,
                   request, session, url_for)

from database import Client, CommandLog, Router, db
import router_api
import wg_manager

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

# Admin credentials (set via env vars in production)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "zivopay2026")


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USER and
                request.form.get("password") == ADMIN_PASS):
            session["logged_in"] = True
            session.permanent = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    clients     = Client.query.all()
    routers     = Router.query.order_by(Router.created_at.desc()).all()
    recent_logs = (CommandLog.query
                   .order_by(CommandLog.executed_at.desc())
                   .limit(10).all())
    return render_template("dashboard.html",
                           clients=clients,
                           routers=routers,
                           recent_logs=recent_logs)


# ── Clients ───────────────────────────────────────────────────────────────────

@app.route("/clients")
@login_required
def clients():
    q    = request.args.get("q", "").strip()
    base = Client.query
    if q:
        base = base.filter(
            Client.name.ilike(f"%{q}%") |
            Client.business_name.ilike(f"%{q}%") |
            Client.phone.ilike(f"%{q}%")
        )
    all_clients = base.order_by(Client.created_at.desc()).all()
    return render_template("clients.html", clients=all_clients, q=q)


@app.route("/clients/add", methods=["GET", "POST"])
@login_required
def add_client():
    if request.method == "POST":
        c = Client(
            name          = request.form["name"],
            business_name = request.form.get("business_name", ""),
            phone         = request.form.get("phone", ""),
            email         = request.form.get("email", ""),
            location      = request.form.get("location", ""),
            notes         = request.form.get("notes", ""),
        )
        db.session.add(c)
        db.session.commit()
        flash(f'Client "{c.name}" added.', "success")
        return redirect(url_for("client_detail", client_id=c.id))
    return render_template("client_form.html", client=None, title="Add Client")


@app.route("/clients/<int:client_id>")
@login_required
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    return render_template("client_detail.html", client=client)


@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    if request.method == "POST":
        client.name          = request.form["name"]
        client.business_name = request.form.get("business_name", "")
        client.phone         = request.form.get("phone", "")
        client.email         = request.form.get("email", "")
        client.location      = request.form.get("location", "")
        client.notes         = request.form.get("notes", "")
        db.session.commit()
        flash("Client updated.", "success")
        return redirect(url_for("client_detail", client_id=client.id))
    return render_template("client_form.html", client=client, title="Edit Client")


@app.route("/clients/<int:client_id>/delete", methods=["POST"])
@login_required
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    name   = client.name
    db.session.delete(client)
    db.session.commit()
    flash(f'Client "{name}" deleted.', "success")
    return redirect(url_for("clients"))


# ── Routers ───────────────────────────────────────────────────────────────────

@app.route("/routers")
@login_required
def routers_all():
    all_routers = Router.query.order_by(Router.created_at.desc()).all()
    return render_template("routers.html", routers=all_routers)


@app.route("/clients/<int:client_id>/routers/add", methods=["GET", "POST"])
@login_required
def add_router(client_id):
    client = Client.query.get_or_404(client_id)
    if request.method == "POST":
        r = Router(
            client_id       = client_id,
            name            = request.form["name"],
            host            = request.form["host"],
            port            = int(request.form.get("port", 8728)),
            username        = request.form.get("username", "admin"),
            password        = request.form.get("password", ""),
            connection_type = request.form.get("connection_type", "wireguard"),
            wg_public_key   = request.form.get("wg_public_key", ""),
            wg_ip           = request.form.get("wg_ip", ""),
            ssid            = request.form.get("ssid", ""),
            notes           = request.form.get("notes", ""),
        )
        db.session.add(r)
        db.session.commit()
        if r.connection_type == "wireguard" and r.wg_public_key and r.wg_ip:
            ok, msg = wg_manager.add_peer(r.wg_public_key, r.wg_ip)
            flash(f'Router "{r.name}" added. WG: {msg}', "success" if ok else "warning")
        else:
            flash(f'Router "{r.name}" added.', "success")
        return redirect(url_for("router_detail", router_id=r.id))
    return render_template("router_form.html", client=client, router=None, title="Add Router")


@app.route("/routers/<int:router_id>")
@login_required
def router_detail(router_id):
    router = Router.query.get_or_404(router_id)
    logs   = (CommandLog.query
              .filter_by(router_id=router_id)
              .order_by(CommandLog.executed_at.desc())
              .limit(25).all())
    commands = router_api.COMMANDS
    return render_template("router_detail.html", router=router, logs=logs, commands=commands)


@app.route("/routers/<int:router_id>/edit", methods=["GET", "POST"])
@login_required
def edit_router(router_id):
    router = Router.query.get_or_404(router_id)
    if request.method == "POST":
        router.name            = request.form["name"]
        router.host            = request.form["host"]
        router.port            = int(request.form.get("port", 8728))
        router.username        = request.form.get("username", "admin")
        router.password        = request.form.get("password", "")
        router.connection_type = request.form.get("connection_type", "wireguard")
        router.wg_public_key   = request.form.get("wg_public_key", "")
        router.wg_ip           = request.form.get("wg_ip", "")
        router.ssid            = request.form.get("ssid", "")
        router.notes           = request.form.get("notes", "")
        db.session.commit()
        flash("Router updated.", "success")
        return redirect(url_for("router_detail", router_id=router.id))
    return render_template("router_form.html",
                           client=router.client, router=router, title="Edit Router")


@app.route("/routers/<int:router_id>/delete", methods=["POST"])
@login_required
def delete_router(router_id):
    router    = Router.query.get_or_404(router_id)
    client_id = router.client_id
    name      = router.name
    if router.wg_public_key:
        wg_manager.remove_peer(router.wg_public_key)
    db.session.delete(router)
    db.session.commit()
    flash(f'Router "{name}" deleted.', "success")
    return redirect(url_for("client_detail", client_id=client_id))


# ── Router API endpoints ──────────────────────────────────────────────────────

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
        router_id = router_id,
        command   = cmd_label,
        output    = result.get("output", ""),
        status    = "success" if result.get("success") else "error",
    )
    db.session.add(log)
    db.session.commit()
    return jsonify(result)


@app.route("/api/routers/<int:router_id>/reboot", methods=["POST"])
@login_required
def api_reboot(router_id):
    r      = Router.query.get_or_404(router_id)
    result = router_api.run_command(r.host, r.port, r.username, r.password, "reboot")
    log    = CommandLog(router_id=router_id, command="reboot",
                        output=result.get("output",""),
                        status="success" if result["success"] else "error")
    db.session.add(log)
    db.session.commit()
    return jsonify(result)


# ── WireGuard API ─────────────────────────────────────────────────────────────

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


# ── Onboarding wizard ─────────────────────────────────────────────────────────

@app.route("/onboard", methods=["GET", "POST"])
@login_required
def onboard():
    if request.method == "GET":
        next_ip = wg_manager.next_free_ip() or ""
        return render_template("onboard.html", step=1, data={},
                               test_result=None, next_wg_ip=next_ip)

    step = int(request.form.get("step", 1))
    data = json.loads(request.form.get("data", "{}"))

    if step == 1:
        data["client"] = {
            "name":          request.form.get("name", ""),
            "business_name": request.form.get("business_name", ""),
            "phone":         request.form.get("phone", ""),
            "email":         request.form.get("email", ""),
            "location":      request.form.get("location", ""),
            "notes":         request.form.get("notes", ""),
        }
        next_ip = wg_manager.next_free_ip() or ""
        return render_template("onboard.html", step=2, data=data,
                               test_result=None, next_wg_ip=next_ip)

    if step == 2:
        data["router"] = {
            "name":            request.form.get("router_name", ""),
            "host":            request.form.get("host", ""),
            "port":            int(request.form.get("port", 8728)),
            "username":        request.form.get("username", "admin"),
            "password":        request.form.get("password", ""),
            "connection_type": request.form.get("connection_type", "wireguard"),
            "wg_ip":           request.form.get("wg_ip", ""),
            "wg_public_key":   request.form.get("wg_public_key", ""),
            "ssid":            request.form.get("ssid", ""),
        }
        rt = data["router"]
        test_result = router_api.test_connection(
            rt["host"], rt["port"], rt["username"], rt["password"])
        return render_template("onboard.html", step=3, data=data,
                               test_result=test_result, next_wg_ip="")

    if step == 3:
        c  = data["client"]
        rt = data["router"]

        client = Client(
            name          = c["name"],
            business_name = c.get("business_name", ""),
            phone         = c.get("phone", ""),
            email         = c.get("email", ""),
            location      = c.get("location", ""),
            notes         = c.get("notes", ""),
        )
        db.session.add(client)
        db.session.flush()

        router = Router(
            client_id       = client.id,
            name            = rt["name"],
            host            = rt["host"],
            port            = rt["port"],
            username        = rt["username"],
            password        = rt["password"],
            connection_type = rt["connection_type"],
            wg_ip           = rt.get("wg_ip", ""),
            wg_public_key   = rt.get("wg_public_key", ""),
            ssid            = rt.get("ssid", ""),
        )
        db.session.add(router)
        db.session.commit()

        wg_msg = ""
        if router.connection_type == "wireguard" and router.wg_public_key and router.wg_ip:
            ok, wg_msg = wg_manager.add_peer(router.wg_public_key, router.wg_ip)
            wg_msg = f" | WG: {wg_msg}"

        flash(f'"{client.name}" onboarded with router "{router.name}"!{wg_msg}', "success")
        return redirect(url_for("router_detail", router_id=router.id))

    return redirect(url_for("onboard"))


@app.route("/api/test-adhoc", methods=["POST"])
@login_required
def api_test_adhoc():
    host = request.form.get("host", "").strip()
    port = request.form.get("port", 8728)
    user = request.form.get("username", "admin")
    pw   = request.form.get("password", "")
    if not host:
        return jsonify({"success": False, "error": "No host provided"})
    return jsonify(router_api.test_connection(host, port, user, pw))


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/settings")
@login_required
def settings():
    peers  = []
    wg_err = None
    try:
        peers = wg_manager.list_peers()
    except Exception as e:
        wg_err = str(e)
    routers = Router.query.filter_by(connection_type="wireguard").all()
    return render_template("settings.html", peers=peers, wg_err=wg_err, routers=routers,
                           wg_iface=wg_manager.WG_INTERFACE,
                           vps_wg_ip=wg_manager.VPS_WG_IP)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  ZivoPay Onboarding  →  http://localhost:{port}\n")
    app.run(debug=True, host="0.0.0.0", port=port)
