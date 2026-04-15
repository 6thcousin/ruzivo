"""
ZivoPay Desktop — app.py
Flask backend for the desktop app.
"""

import os
import json
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, flash, send_from_directory)

from core.db        import get_db, init_db, get_setting, set_setting, log_activity
from core.wireguard import next_free_ip, register_peer, remove_peer, list_peers
from core.mikrotik  import test_connection, get_stats, push_full_config, apply_quick_fix
from core.logo      import process_logo, get_logo_url

# ── Init ──────────────────────────────────────────────────────────────────────
init_db()

PORT       = int(os.environ.get("PORT", 5090))
SECRET_KEY = os.environ.get("SECRET_KEY", "zivopay-desktop-2026")

app = Flask(__name__)
app.secret_key = SECRET_KEY


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username=? AND password=?", (u, p)
            ).fetchone()
        if user:
            session["user"]     = user["username"]
            session["role"]     = user["role"]
            return redirect(url_for("dashboard"))
        error = "Invalid credentials"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    with get_db() as db:
        clients = db.execute(
            "SELECT * FROM clients ORDER BY created_at DESC"
        ).fetchall()
    return render_template("dashboard.html", clients=clients)


# ── Onboarding wizard ─────────────────────────────────────────────────────────

@app.route("/onboard", methods=["GET"])
@login_required
def onboard():
    wg_ip     = next_free_ip()
    vps_key   = get_setting("vps_wg_pubkey")
    return render_template("onboard.html", wg_ip=wg_ip, vps_key=vps_key, step=1)


@app.route("/onboard/save", methods=["POST"])
@login_required
def onboard_save():
    """Step 1 — save client details + logo."""
    name        = request.form.get("name", "").strip()
    business    = request.form.get("business_name", "").strip()
    location    = request.form.get("location", "").strip()
    phone       = request.form.get("phone", "").strip()
    ssid        = request.form.get("ssid", "").strip()
    ssid_5g     = request.form.get("ssid_5g", "").strip()
    router_pass = request.form.get("router_pass", "558920").strip()
    notes       = request.form.get("notes", "").strip()
    wg_ip       = next_free_ip()

    if not name or not ssid:
        flash("Name and SSID are required.", "danger")
        return redirect(url_for("onboard"))

    logo_path = ""
    if "logo" in request.files:
        f = request.files["logo"]
        if f and f.filename:
            ok, path, msg = process_logo(f.read(), f.filename, remove_bg=True)
            if ok:
                logo_path = path
            else:
                flash(f"Logo warning: {msg}", "warning")

    with get_db() as db:
        cur = db.execute("""
            INSERT INTO clients
            (name, business_name, location, phone, ssid, ssid_5g,
             router_pass, wg_ip, notes, logo_path, onboarded_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (name, business, location, phone, ssid, ssid_5g,
              router_pass, wg_ip, notes, logo_path, session["user"]))
        db.commit()
        client_id = cur.lastrowid

    log_activity(client_id, "created", f"WG IP: {wg_ip}", session["user"])
    return redirect(url_for("onboard_connect", client_id=client_id))


@app.route("/onboard/<int:client_id>/connect", methods=["GET", "POST"])
@login_required
def onboard_connect(client_id):
    """Step 2 — connect to MikroTik and push config."""
    with get_db() as db:
        client = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client:
        return redirect(url_for("dashboard"))

    test_result = None
    if request.method == "POST":
        host     = request.form.get("host", "").strip()
        port     = request.form.get("port", "8728").strip()
        username = request.form.get("username", "admin").strip()
        password = request.form.get("password", "").strip()

        action = request.form.get("action", "test")

        if action == "test":
            test_result = test_connection(host, port, username, password)
            return render_template("onboard.html", step=2, client=client,
                                   test_result=test_result,
                                   host=host, port=port, username=username, password=password)

        elif action == "push":
            # Push full config to router
            cfg = {
                "identity":    client["name"],
                "router_pass": client["router_pass"],
                "ssid":        client["ssid"],
                "ssid_5g":     client["ssid_5g"] or "",
                "wg_ip":       client["wg_ip"],
                "vps_pubkey":  get_setting("vps_wg_pubkey"),
                "vps_host":    get_setting("vps_host"),
                "vps_port":    get_setting("vps_wg_port", "13231"),
            }
            ok, output, wg_key = push_full_config(host, port, username, password, cfg)

            # Save host/port/credentials + WG key
            with get_db() as db:
                db.execute("""
                    UPDATE clients SET host=?, port=?, username=?,
                    wg_public_key=?, status=?, updated_at=datetime('now')
                    WHERE id=?
                """, (host, port, username, wg_key,
                      "wg_pending" if wg_key else "config_pushed", client_id))
                db.commit()

            log_activity(client_id, "config_pushed", output[:300], session["user"])

            return render_template("onboard.html", step=3, client=client,
                                   output=output, wg_key=wg_key,
                                   ok=ok)

    return render_template("onboard.html", step=2, client=client,
                           test_result=None, host="192.168.88.1",
                           port="8728", username="admin", password="")


@app.route("/onboard/<int:client_id>/register", methods=["POST"])
@login_required
def onboard_register(client_id):
    """Step 3 — register WireGuard peer on VPS."""
    with get_db() as db:
        client = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client:
        return redirect(url_for("dashboard"))

    pubkey = request.form.get("wg_public_key", "").strip()
    if not pubkey:
        flash("Public key required.", "danger")
        return redirect(url_for("onboard_connect", client_id=client_id))

    ok, msg = register_peer(pubkey, client["wg_ip"])

    with get_db() as db:
        db.execute("""
            UPDATE clients SET wg_public_key=?, status=?, updated_at=datetime('now')
            WHERE id=?
        """, (pubkey, "active" if ok else "key_saved", client_id))
        db.commit()

    log_activity(client_id, "peer_registered" if ok else "peer_failed", msg, session["user"])

    if ok:
        flash(f"✓ {client['name']} is live on the VPN!", "success")
    else:
        flash(f"Key saved but VPS registration failed: {msg}", "warning")

    return redirect(url_for("client_detail", client_id=client_id))


# ── Client detail ─────────────────────────────────────────────────────────────

@app.route("/clients/<int:client_id>")
@login_required
def client_detail(client_id):
    with get_db() as db:
        client = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        logs   = db.execute(
            "SELECT * FROM activity_log WHERE client_id=? ORDER BY created_at DESC LIMIT 20",
            (client_id,)
        ).fetchall()
    if not client:
        return redirect(url_for("dashboard"))
    logo_url = get_logo_url(client["logo_path"]) if client["logo_path"] else None
    return render_template("client_detail.html", client=client, logs=logs, logo_url=logo_url)


@app.route("/clients/<int:client_id>/delete", methods=["POST"])
@login_required
def delete_client(client_id):
    with get_db() as db:
        db.execute("DELETE FROM clients WHERE id=?", (client_id,))
        db.commit()
    flash("Client deleted.", "secondary")
    return redirect(url_for("dashboard"))


# ── Quick Fix ─────────────────────────────────────────────────────────────────

@app.route("/quickfix")
@login_required
def quickfix():
    with get_db() as db:
        clients = db.execute(
            "SELECT id, name, business_name, host, port, username, router_pass FROM clients"
            " WHERE host IS NOT NULL ORDER BY name"
        ).fetchall()
    return render_template("quickfix.html", clients=clients)


@app.route("/api/fix/<int:client_id>/<fix_key>", methods=["POST"])
@login_required
def api_fix(client_id, fix_key):
    with get_db() as db:
        c = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not c:
        return jsonify({"success": False, "output": "Client not found"})
    ok, output = apply_quick_fix(c["host"], c["port"], c["username"], c["router_pass"], fix_key)
    log_activity(client_id, f"fix:{fix_key}", output[:200], session.get("user", "?"))
    return jsonify({"success": ok, "output": output})


# ── SSH Terminal ──────────────────────────────────────────────────────────────

@app.route("/terminal")
@login_required
def terminal():
    with get_db() as db:
        clients = db.execute(
            "SELECT id, name, business_name, host FROM clients WHERE host IS NOT NULL ORDER BY name"
        ).fetchall()
    return render_template("terminal.html", clients=clients)


@app.route("/api/ssh", methods=["POST"])
@login_required
def api_ssh():
    data     = request.json
    host     = data.get("host", "")
    port     = int(data.get("port", 22))
    username = data.get("username", "admin")
    password = data.get("password", "")
    command  = data.get("command", "")

    from core.ssh import quick_ssh
    ok, output = quick_ssh(host, port, username, password, command)
    return jsonify({"success": ok, "output": output})


# ── Router stats API ──────────────────────────────────────────────────────────

@app.route("/api/stats/<int:client_id>")
@login_required
def api_stats(client_id):
    with get_db() as db:
        c = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not c or not c["host"]:
        return jsonify({"success": False, "error": "No host configured"})
    return jsonify(get_stats(c["host"], c["port"], c["username"], c["router_pass"]))


# ── WireGuard status ──────────────────────────────────────────────────────────

@app.route("/api/wg/peers")
@login_required
def api_wg_peers():
    ok, out = list_peers()
    return jsonify({"success": ok, "output": out})


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        keys = ["vps_host", "vps_user", "vps_pass", "vps_wg_pubkey",
                "vps_wg_port", "vps_wg_ip", "wg_interface", "wg_conf", "app_name"]
        for k in keys:
            v = request.form.get(k, "").strip()
            if v:
                set_setting(k, v)
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))

    s = {k: get_setting(k) for k in
         ["vps_host", "vps_user", "vps_pass", "vps_wg_pubkey",
          "vps_wg_port", "vps_wg_ip", "wg_interface", "wg_conf", "app_name"]}
    return render_template("settings.html", s=s)


# ── Static logos ──────────────────────────────────────────────────────────────

@app.route("/static/logos/<path:filename>")
def serve_logo(filename):
    logo_dir = os.path.join(os.path.dirname(__file__), "static", "logos")
    return send_from_directory(logo_dir, filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=True)
