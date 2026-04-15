"""
ZivoPay AutoConfig — Technician Onboarding Tool
================================================
Steps:
  1. Technician fills client details
  2. App generates RouterOS bootstrap .rsc
  3. Technician pastes script on MikroTik, copies WireGuard public key output
  4. Technician enters that key here → peer registered on VPS

Run:  python app.py
"""

import os, subprocess, ipaddress, sqlite3
from datetime import datetime
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, send_file, abort)
import io

# ── CONFIG ────────────────────────────────────────────────────────────────────
VPS_WG_PUBKEY  = os.environ.get("VPS_WG_PUBKEY",  "")          # set on VPS
VPS_WG_HOST    = os.environ.get("VPS_WG_HOST",    "164.90.160.138")
VPS_WG_PORT    = int(os.environ.get("VPS_WG_PORT", "13231"))
VPS_WG_IP      = os.environ.get("VPS_WG_IP",      "10.0.0.1")
WG_INTERFACE   = os.environ.get("WG_INTERFACE",   "wg0")
WG_CONF        = os.environ.get("WG_CONF",        "/etc/wireguard/wg0.conf")
ADMIN_USER     = os.environ.get("ADMIN_USER",     "admin")
ADMIN_PASS     = os.environ.get("ADMIN_PASS",     "zivopay2026")
SECRET_KEY     = os.environ.get("SECRET_KEY",     "autoconfig-zivopay-2026")
PORT           = int(os.environ.get("PORT",        5003))

_HERE   = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "data", "autoconfig.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = SECRET_KEY


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                business_name TEXT,
                location      TEXT,
                phone         TEXT,
                ssid          TEXT,
                router_pass   TEXT,
                wg_ip         TEXT UNIQUE NOT NULL,
                wg_public_key TEXT,
                status        TEXT DEFAULT 'pending',
                notes         TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        db.commit()


init_db()


# ── WireGuard helpers ─────────────────────────────────────────────────────────

def used_ips():
    ips = {VPS_WG_IP}
    with get_db() as db:
        for row in db.execute("SELECT wg_ip FROM clients"):
            ips.add(row["wg_ip"])
    return ips


def next_free_ip():
    net   = ipaddress.ip_network("10.0.0.0/24")
    taken = used_ips()
    for host in net.hosts():
        ip = str(host)
        if ip not in taken:
            return ip
    return None


def register_wg_peer(public_key, wg_ip):
    allowed = f"{wg_ip}/32,192.168.88.0/24"
    try:
        r = subprocess.run(
            ["wg", "set", WG_INTERFACE, "peer", public_key, "allowed-ips", allowed],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return False, r.stderr.strip() or "wg set failed"
        if os.path.exists(WG_CONF):
            with open(WG_CONF) as f:
                content = f.read()
            if public_key not in content:
                with open(WG_CONF, "a") as f:
                    f.write(f"\n[Peer]\nPublicKey = {public_key}\nAllowedIPs = {allowed}\n")
        return True, "Peer registered"
    except FileNotFoundError:
        return False, "wg not found — register manually on VPS"
    except Exception as e:
        return False, str(e)


# ── Bootstrap generator ───────────────────────────────────────────────────────

def generate_rsc(name, business, ssid, router_pass, wg_ip):
    identity    = name.lower().replace(" ", "_").replace("&", "and")
    wg_listen   = 15000 + int(wg_ip.split(".")[-1])
    vps_key     = VPS_WG_PUBKEY or "<PASTE_VPS_WG_PUBLIC_KEY_HERE>"
    now         = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""\
# ================================================================
# ZivoPay Bootstrap — {business}
# WireGuard IP : {wg_ip}
# Location     : (see ZivoPay dashboard)
# Generated    : {now}
# ================================================================
# INSTRUCTIONS:
#   1. Open MikroTik terminal (Winbox / SSH / WebFig)
#   2. Paste this entire script
#   3. Copy the WireGuard public key that appears at the end
#   4. Go back to ZivoPay AutoConfig and paste that key
# ================================================================

# ── 1. Identity ─────────────────────────────────────────────────
/system identity set name="{identity}"

# ── 2. Admin password ───────────────────────────────────────────
/user set [find name=admin] password="{router_pass}"

# ── 3. WireGuard tunnel to VPS ──────────────────────────────────
/interface wireguard add name=wg-zivo listen-port={wg_listen} mtu=1420
/interface wireguard peers add interface=wg-zivo \\
    public-key="{vps_key}" \\
    endpoint-address={VPS_WG_HOST} \\
    endpoint-port={VPS_WG_PORT} \\
    allowed-address=10.0.0.0/24 \\
    persistent-keepalive=25
/ip address add address={wg_ip}/24 interface=wg-zivo

# ── 4. Bridge ───────────────────────────────────────────────────
/interface bridge add name=bridgeLocal protocol-mode=none fast-forward=no
/interface bridge port add bridge=bridgeLocal interface=ether2
/interface bridge port add bridge=bridgeLocal interface=wifi1

# ── 5. LAN address ──────────────────────────────────────────────
/ip address add address=192.168.88.1/24 interface=bridgeLocal

# ── 6. DHCP ─────────────────────────────────────────────────────
/ip pool add name=hs_pool ranges=192.168.88.10-192.168.88.254
/ip dhcp-server add name=hs_dhcp interface=bridgeLocal \\
    address-pool=hs_pool lease-time=30m disabled=no
/ip dhcp-server network add address=192.168.88.0/24 \\
    gateway=192.168.88.1 dns-server=8.8.8.8,8.8.4.4
/ip dns set allow-remote-requests=yes servers=8.8.8.8,8.8.4.4

# ── 7. NAT ──────────────────────────────────────────────────────
/ip firewall nat add chain=srcnat action=masquerade out-interface=ether1

# ── 8. WiFi 2.4 GHz ─────────────────────────────────────────────
/interface wifi set wifi1 \\
    configuration.ssid="{ssid}" \\
    configuration.country="Zimbabwe" \\
    channel.frequency=2437 \\
    channel.width=20mhz \\
    disabled=no

# ── 9. Hotspot ───────────────────────────────────────────────────
/ip hotspot profile add name=hsprof1 \\
    hotspot-address=192.168.88.1 \\
    login-by=http-chap,mac \\
    use-radius=no
/ip hotspot add name=hotspot1 \\
    interface=bridgeLocal \\
    address-pool=hs_pool \\
    profile=hsprof1 \\
    keepalive-timeout=2m \\
    disabled=no

# ── 10. Route all VPN traffic through WireGuard ──────────────────
/ip route add dst-address=10.0.0.0/24 gateway=wg-zivo

# ── 11. IP Services — enable API ────────────────────────────────
/ip service enable api

# ================================================================
# COPY THE KEY BELOW AND PASTE IT INTO ZIVOPAY AUTOCONFIG
# ================================================================
:put "================================================================"
:put "CLIENT  : {business}"
:put "WG IP   : {wg_ip}"
:put "PUBLIC KEY (copy this):"
:put [/interface wireguard get wg-zivo public-key]
:put "================================================================"
"""


# ── Auth middleware ───────────────────────────────────────────────────────────

from functools import wraps
from flask import session as fsession


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not fsession.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USER and
                request.form.get("password") == ADMIN_PASS):
            fsession["logged_in"] = True
            return redirect(url_for("index"))
        error = "Invalid credentials"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    fsession.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    with get_db() as db:
        clients = db.execute(
            "SELECT * FROM clients ORDER BY created_at DESC"
        ).fetchall()
    return render_template("index.html", clients=clients)


@app.route("/new", methods=["GET", "POST"])
@login_required
def new_client():
    wg_ip = next_free_ip()
    if request.method == "GET":
        return render_template("new_client.html", wg_ip=wg_ip)

    name        = request.form.get("name", "").strip()
    business    = request.form.get("business_name", "").strip()
    location    = request.form.get("location", "").strip()
    phone       = request.form.get("phone", "").strip()
    ssid        = request.form.get("ssid", "").strip()
    router_pass = request.form.get("router_pass", "558920").strip()
    notes       = request.form.get("notes", "").strip()

    if not name or not ssid:
        flash("Name and SSID are required.", "danger")
        return render_template("new_client.html", wg_ip=wg_ip, v=request.form)

    wg_ip = next_free_ip()
    if not wg_ip:
        flash("No WireGuard IPs available.", "danger")
        return render_template("new_client.html", wg_ip="—", v=request.form)

    with get_db() as db:
        cur = db.execute(
            """INSERT INTO clients
               (name, business_name, location, phone, ssid, router_pass, wg_ip, notes)
               VALUES (?,?,?,?,?,?,?,?)""",
            (name, business, location, phone, ssid, router_pass, wg_ip, notes),
        )
        db.commit()
        client_id = cur.lastrowid

    return redirect(url_for("bootstrap", client_id=client_id))


@app.route("/bootstrap/<int:client_id>")
@login_required
def bootstrap(client_id):
    with get_db() as db:
        client = db.execute(
            "SELECT * FROM clients WHERE id=?", (client_id,)
        ).fetchone()
    if not client:
        abort(404)
    script = generate_rsc(
        client["name"], client["business_name"] or client["name"],
        client["ssid"], client["router_pass"], client["wg_ip"],
    )
    return render_template("bootstrap.html", client=client, script=script)


@app.route("/download/<int:client_id>")
@login_required
def download(client_id):
    with get_db() as db:
        client = db.execute(
            "SELECT * FROM clients WHERE id=?", (client_id,)
        ).fetchone()
    if not client:
        abort(404)
    script = generate_rsc(
        client["name"], client["business_name"] or client["name"],
        client["ssid"], client["router_pass"], client["wg_ip"],
    )
    fname = f"{client['name'].lower().replace(' ','_')}_bootstrap.rsc"
    return send_file(
        io.BytesIO(script.encode()),
        as_attachment=True,
        download_name=fname,
        mimetype="text/plain",
    )


@app.route("/register/<int:client_id>", methods=["POST"])
@login_required
def register_peer(client_id):
    with get_db() as db:
        client = db.execute(
            "SELECT * FROM clients WHERE id=?", (client_id,)
        ).fetchone()
    if not client:
        abort(404)

    pubkey = request.form.get("wg_public_key", "").strip()
    if not pubkey:
        flash("Public key is required.", "danger")
        return redirect(url_for("bootstrap", client_id=client_id))

    ok, msg = register_wg_peer(pubkey, client["wg_ip"])

    with get_db() as db:
        db.execute(
            "UPDATE clients SET wg_public_key=?, status=? WHERE id=?",
            (pubkey, "active" if ok else "key_saved", client_id),
        )
        db.commit()

    if ok:
        flash(f"Peer registered! {client['name']} is now on the VPN.", "success")
    else:
        flash(f"Key saved but VPS registration failed: {msg}. Register manually.", "warning")

    return redirect(url_for("done", client_id=client_id))


@app.route("/done/<int:client_id>")
@login_required
def done(client_id):
    with get_db() as db:
        client = db.execute(
            "SELECT * FROM clients WHERE id=?", (client_id,)
        ).fetchone()
    if not client:
        abort(404)
    return render_template("done.html", client=client)


@app.route("/delete/<int:client_id>", methods=["POST"])
@login_required
def delete_client(client_id):
    with get_db() as db:
        db.execute("DELETE FROM clients WHERE id=?", (client_id,))
        db.commit()
    flash("Client deleted.", "secondary")
    return redirect(url_for("index"))


if __name__ == "__main__":
    print(f"  ZivoPay AutoConfig  →  http://localhost:{PORT}")
    print(f"  Login: {ADMIN_USER} / {ADMIN_PASS}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
