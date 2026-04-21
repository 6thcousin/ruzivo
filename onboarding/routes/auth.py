"""routes/auth.py — login / logout"""
import functools
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from config import Config

auth_bp = Blueprint("auth", __name__)


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard.index"))
    error = None
    if request.method == "POST":
        if (request.form.get("username") == Config.ADMIN_USER and
                request.form.get("password") == Config.ADMIN_PASS):
            session["logged_in"] = True
            session.permanent = True
            return redirect(request.args.get("next") or url_for("dashboard.index"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
