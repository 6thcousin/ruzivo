"""routes/clients.py — client CRUD"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from db import db
from db.models import Client
from routes.auth import login_required

clients_bp = Blueprint("clients", __name__, url_prefix="/clients")


@clients_bp.route("/")
@login_required
def list_clients():
    q    = request.args.get("q", "").strip()
    base = Client.query
    if q:
        base = base.filter(
            Client.name.ilike(f"%{q}%") |
            Client.business_name.ilike(f"%{q}%") |
            Client.phone.ilike(f"%{q}%")
        )
    return render_template("clients/list.html",
                           clients=base.order_by(Client.created_at.desc()).all(), q=q)


@clients_bp.route("/add", methods=["GET", "POST"])
@login_required
def add():
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
        return redirect(url_for("clients.detail", client_id=c.id))
    return render_template("clients/form.html", client=None, title="Add Client")


@clients_bp.route("/<int:client_id>")
@login_required
def detail(client_id):
    return render_template("clients/detail.html",
                           client=Client.query.get_or_404(client_id))


@clients_bp.route("/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
def edit(client_id):
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
        return redirect(url_for("clients.detail", client_id=client.id))
    return render_template("clients/form.html", client=client, title="Edit Client")


@clients_bp.route("/<int:client_id>/delete", methods=["POST"])
@login_required
def delete(client_id):
    client = Client.query.get_or_404(client_id)
    name   = client.name
    db.session.delete(client)
    db.session.commit()
    flash(f'Client "{name}" deleted.', "success")
    return redirect(url_for("clients.list_clients"))
