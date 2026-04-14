"""routes/routers.py — router CRUD"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from db import db
from db.models import Router
from core import mikrotik
from core import wireguard
from routes.auth import login_required

routers_bp = Blueprint("routers", __name__, url_prefix="/routers")


@routers_bp.route("/")
@login_required
def list_routers():
    return render_template("routers/list.html",
                           routers=Router.query.order_by(Router.created_at.desc()).all())


@routers_bp.route("/<int:router_id>")
@login_required
def detail(router_id):
    router = Router.query.get_or_404(router_id)
    logs   = router.logs[:25]
    return render_template("routers/detail.html",
                           router=router, logs=logs, commands=mikrotik.COMMANDS)


@routers_bp.route("/<int:router_id>/edit", methods=["GET", "POST"])
@login_required
def edit(router_id):
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
        return redirect(url_for("routers.detail", router_id=router.id))
    return render_template("routers/form.html",
                           client=router.client, router=router, title="Edit Router")


@routers_bp.route("/<int:router_id>/delete", methods=["POST"])
@login_required
def delete(router_id):
    router    = Router.query.get_or_404(router_id)
    client_id = router.client_id
    name      = router.name
    if router.wg_public_key:
        wireguard.remove_peer(router.wg_public_key)
    db.session.delete(router)
    db.session.commit()
    flash(f'Router "{name}" deleted.', "success")
    return redirect(url_for("clients.detail", client_id=client_id))


@routers_bp.route("/add/<int:client_id>", methods=["GET", "POST"])
@login_required
def add(client_id):
    from db.models import Client
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
            ok, msg = wireguard.add_peer(r.wg_public_key, r.wg_ip)
            flash(f'Router "{r.name}" added. WG: {msg}', "success" if ok else "warning")
        else:
            flash(f'Router "{r.name}" added.', "success")
        return redirect(url_for("routers.detail", router_id=r.id))
    return render_template("routers/form.html", client=client, router=None, title="Add Router")
