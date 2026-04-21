"""seed.py — pre-load all known routers into DB"""
import os, sys
os.makedirs("data", exist_ok=True)

from main import app
from db import db
from db.models import Client, Router

SITES = [
    {
        "client": {"name": "Sylvester", "business_name": "Sylvester", "location": "Zimbabwe",
                   "phone": "", "email": "", "notes": ""},
        "router": {"name": "sylvester_main", "host": "10.0.0.2", "port": 8728,
                   "username": "admin", "password": "558920", "connection_type": "wireguard",
                   "wg_ip": "10.0.0.2", "wg_public_key": "", "ssid": "", "notes": ""},
    },
    {
        "client": {"name": "B-Tech", "business_name": "B-Tech Enterprises", "location": "Zimbabwe",
                   "phone": "", "email": "", "notes": ""},
        "router": {"name": "btech_main", "host": "10.0.0.4", "port": 8728,
                   "username": "admin", "password": "558920", "connection_type": "wireguard",
                   "wg_ip": "10.0.0.4", "wg_public_key": "", "ssid": "", "notes": ""},
    },
    {
        "client": {"name": "Ringonckz", "business_name": "Ringonckz", "location": "Zimbabwe",
                   "phone": "", "email": "", "notes": ""},
        "router": {"name": "ringonckz_main", "host": "10.0.0.5", "port": 8728,
                   "username": "admin", "password": "558920", "connection_type": "wireguard",
                   "wg_ip": "10.0.0.5", "wg_public_key": "", "ssid": "", "notes": ""},
    },
    {
        "client": {"name": "Siganda", "business_name": "Siganda Enterprises", "location": "Zimbabwe",
                   "phone": "", "email": "", "notes": ""},
        "router": {"name": "siganda_secondary", "host": "10.0.0.7", "port": 8728,
                   "username": "admin", "password": "558920", "connection_type": "wireguard",
                   "wg_ip": "10.0.0.7", "wg_public_key": "", "ssid": "", "notes": ""},
    },
    {
        "client": {"name": "S & J Enterprises", "business_name": "S & J Enterprises",
                   "location": "Zimbabwe", "phone": "", "email": "",
                   "notes": "Cudy AP on ether2 — needs AP mode fix"},
        "router": {"name": "sj_enterprises", "host": "10.0.0.8", "port": 8728,
                   "username": "admin", "password": "558920", "connection_type": "wireguard",
                   "wg_ip": "10.0.0.8", "wg_public_key": "", "ssid": "S & J Enterprises",
                   "notes": "Cudy AP attached — fix: set AP mode, LAN IP 192.168.88.2"},
    },
]

with app.app_context():
    db.create_all()
    added = 0
    for site in SITES:
        if Router.query.filter_by(host=site["router"]["host"]).first():
            print(f"  [skip] {site['router']['name']} — already exists")
            continue
        client = Client.query.filter_by(name=site["client"]["name"]).first()
        if not client:
            client = Client(**site["client"])
            db.session.add(client)
            db.session.flush()
        router = Router(client_id=client.id, **site["router"])
        db.session.add(router)
        added += 1
        print(f"  [+] {site['router']['name']} ({site['router']['host']})")
    db.session.commit()
    print(f"\n  Done — {added} added, {Router.query.count()} total in DB")
