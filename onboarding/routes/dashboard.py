"""routes/dashboard.py — main service center overview"""
from flask import Blueprint, render_template
from db.models import Client, CommandLog, Router
from routes.auth import login_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    clients     = Client.query.all()
    routers     = Router.query.order_by(Router.created_at.desc()).all()
    recent_logs = (CommandLog.query
                   .order_by(CommandLog.executed_at.desc())
                   .limit(10).all())
    return render_template("dashboard.html",
                           clients=clients,
                           routers=routers,
                           recent_logs=recent_logs)
