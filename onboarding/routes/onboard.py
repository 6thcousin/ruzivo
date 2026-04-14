"""routes/onboard.py — 3-step onboarding wizard"""
import json
from flask import Blueprint, flash, redirect, render_template, request, url_for
from db import db
from db.models import Client, Router
from core import mikrotik, wireguard
from routes.auth import login_required

onboard_bp = Blueprint("onboard", __name__, url_prefix="/onboard")


@onboard_bp.route("/", methods=["GET", "POST"])
@login_required
def wizard():
    if request.method == "GET":
        return render_template("onboard.html", step=1, data={},
                               test_result=None,
                               next_wg_ip=wireguard.next_free_ip() or "")

    step = int(request.form.get("step", 1))
    data = json.loads(request.form.get("data", "{}"))

    # Step 1 → collect client info
    if step == 1:
        data["client"] = {k: request.form.get(k, "")
                          for k in ("name", "business_name", "phone", "email", "location", "notes")}
        return render_template("onboard.html", step=2, data=data,
                               test_result=None,
                               next_wg_ip=wireguard.next_free_ip() or "")

    # Step 2 → collect router info + test connection
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
        rt          = data["router"]
        test_result = mikrotik.test_connection(rt["host"], rt["port"], rt["username"], rt["password"])
        return render_template("onboard.html", step=3, data=data,
                               test_result=test_result, next_wg_ip="")

    # Step 3 → save to DB + register WireGuard
    if step == 3:
        c, rt = data["client"], data["router"]

        client = Client(**{k: c.get(k, "") for k in
                           ("name", "business_name", "phone", "email", "location", "notes")})
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
            ok, wg_msg = wireguard.add_peer(router.wg_public_key, router.wg_ip)
            wg_msg = f" | WG: {wg_msg}"

        flash(f'"{client.name}" onboarded with router "{router.name}"!{wg_msg}', "success")
        return redirect(url_for("routers.detail", router_id=router.id))

    return redirect(url_for("onboard.wizard"))
