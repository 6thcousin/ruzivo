from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Client(db.Model):
    __tablename__ = "clients"
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    business_name = db.Column(db.String(100), default="")
    phone         = db.Column(db.String(30), default="")
    email         = db.Column(db.String(120), default="")
    location      = db.Column(db.String(200), default="")
    notes         = db.Column(db.Text, default="")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    routers       = db.relationship("Router", backref="client", lazy=True,
                                    cascade="all, delete-orphan")

    @property
    def online_count(self):
        return sum(1 for r in self.routers if getattr(r, "_online", False))


class Router(db.Model):
    __tablename__   = "routers"
    id              = db.Column(db.Integer, primary_key=True)
    client_id       = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    name            = db.Column(db.String(100), nullable=False)
    host            = db.Column(db.String(100), nullable=False)
    port            = db.Column(db.Integer, default=8728)
    username        = db.Column(db.String(50), default="admin")
    password        = db.Column(db.String(100), default="")
    connection_type = db.Column(db.String(20), default="wireguard")  # wireguard | local
    wg_public_key   = db.Column(db.String(200), default="")
    wg_ip           = db.Column(db.String(20), default="")
    ssid            = db.Column(db.String(60), default="")
    notes           = db.Column(db.Text, default="")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    command_logs    = db.relationship("CommandLog", backref="router", lazy=True,
                                      cascade="all, delete-orphan")


class CommandLog(db.Model):
    __tablename__ = "command_logs"
    id          = db.Column(db.Integer, primary_key=True)
    router_id   = db.Column(db.Integer, db.ForeignKey("routers.id"), nullable=False)
    command     = db.Column(db.String(300))
    output      = db.Column(db.Text)
    status      = db.Column(db.String(20))   # success | error
    executed_at = db.Column(db.DateTime, default=datetime.utcnow)
