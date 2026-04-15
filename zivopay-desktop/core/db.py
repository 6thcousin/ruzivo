"""core/db.py — SQLite database setup and helpers"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "clients.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    business_name TEXT,
    location      TEXT,
    phone         TEXT,
    email         TEXT,
    ssid          TEXT,
    ssid_5g       TEXT,
    router_pass   TEXT DEFAULT '558920',
    wg_ip         TEXT UNIQUE,
    wg_public_key TEXT,
    host          TEXT,
    port          INTEGER DEFAULT 8728,
    username      TEXT DEFAULT 'admin',
    status        TEXT DEFAULT 'pending',
    notes         TEXT,
    logo_path     TEXT,
    onboarded_by  TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT UNIQUE NOT NULL,
    password   TEXT NOT NULL,
    role       TEXT DEFAULT 'technician',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activity_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id  INTEGER,
    action     TEXT,
    detail     TEXT,
    by_user    TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript(SCHEMA)
        # Default admin user
        db.execute("""
            INSERT OR IGNORE INTO users (username, password, role)
            VALUES ('admin', 'zivopay2026', 'admin')
        """)
        # Default settings
        defaults = {
            "vps_host":      "164.90.160.138",
            "vps_user":      "root",
            "vps_pass":      "",
            "vps_wg_pubkey": "",
            "vps_wg_port":   "13231",
            "vps_wg_ip":     "10.0.0.1",
            "wg_interface":  "wg0",
            "wg_conf":       "/etc/wireguard/wg0.conf",
            "app_name":      "ZivoPay AutoConfig",
        }
        for k, v in defaults.items():
            db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
        db.commit()

def get_setting(key, default=""):
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key, value):
    with get_db() as db:
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
        db.commit()

def log_activity(client_id, action, detail="", by_user="system"):
    with get_db() as db:
        db.execute(
            "INSERT INTO activity_log (client_id, action, detail, by_user) VALUES (?,?,?,?)",
            (client_id, action, detail, by_user)
        )
        db.commit()
