#!/usr/bin/env python3
"""
fix_sj_wifi.py — run on VPS to fix sj_enterprises WiFi
Usage:  python3 fix_sj_wifi.py <router_ip> [password]
"""
import sys
import time
import routeros_api

HOST     = sys.argv[1] if len(sys.argv) > 1 else "10.0.0.6"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "558920"
PORT     = 8728
USER     = "admin"

def c(label, fn):
    try:
        result = fn()
        print(f"  [✓] {label}" + (f": {result}" if result else ""))
    except Exception as e:
        print(f"  [!] {label}: {e}")

print(f"\nConnecting to {HOST}:{PORT} ...")
pool = routeros_api.RouterOsApiPool(HOST, username=USER, password=PASSWORD,
                                     port=PORT, plaintext_login=True, timeout=10)
api  = pool.get_api()
name = api.get_resource("/system/identity").get()[0].get("name", "?")
print(f"Connected → {name}\n")

# ── Disable wifi2 (5GHz broken/DFS) ─────────────────────────────────────────
print("[1] Disabling wifi2 (5GHz — DFS/inactive channel issue)...")
c("wifi2 disabled", lambda: api.get_resource("/interface/wifi")
  .call("disable", {"numbers": "wifi2"}))

# ── Fix wifi1: channel 6, 20MHz ──────────────────────────────────────────────
print("\n[2] Setting wifi1 → channel 6 (2437 MHz), 20 MHz width...")
c("wifi1 channel set", lambda: api.get_resource("/interface/wifi")
  .call("set", {"numbers": "wifi1", "channel.frequency": "2437", "channel.width": "20mhz"}))

# ── Fix bridge ────────────────────────────────────────────────────────────────
print("\n[3] Fixing bridge (disable RSTP, disable fast-forward)...")
bridges = api.get_resource("/interface/bridge").get()
for b in bridges:
    c(f"bridge {b.get('name')}", lambda bid=b[".id"]:
      api.get_resource("/interface/bridge").call("set", {
          "numbers": bid, "protocol-mode": "none", "fast-forward": "no"
      }))

# ── Fix DHCP ──────────────────────────────────────────────────────────────────
print("\n[4] Fixing DHCP (addresses-per-mac=0, lease-time=30m)...")
servers = api.get_resource("/ip/dhcp-server").get()
for s in servers:
    c(f"dhcp {s.get('name')}", lambda sid=s[".id"]:
      api.get_resource("/ip/dhcp-server").call("set", {
          "numbers": sid, "lease-time": "30m", "addresses-per-mac": "0"
      }))

# ── Clear stale leases ────────────────────────────────────────────────────────
print("\n[5] Clearing stale DHCP leases...")
leases = api.get_resource("/ip/dhcp-server/lease").get()
stale  = [l for l in leases if l.get("status") in ("expired", "abandoned")]
for l in stale:
    api.get_resource("/ip/dhcp-server/lease").remove(id=l[".id"])
print(f"  [✓] Removed {len(stale)} stale lease(s)")

# ── Clear blocked bindings ────────────────────────────────────────────────────
print("\n[6] Clearing blocked IP bindings...")
binds   = api.get_resource("/ip/hotspot/ip-binding").get()
blocked = [b for b in binds if b.get("type") == "blocked"]
for b in blocked:
    api.get_resource("/ip/hotspot/ip-binding").remove(id=b[".id"])
print(f"  [✓] Removed {len(blocked)} blocked binding(s)")

# ── Hotspot keepalive ─────────────────────────────────────────────────────────
print("\n[7] Setting hotspot keepalive-timeout=2m...")
hs = api.get_resource("/ip/hotspot").get()
for h in hs:
    c(f"hotspot {h.get('name')}", lambda hid=h[".id"]:
      api.get_resource("/ip/hotspot").call("set", {
          "numbers": hid, "keepalive-timeout": "2m"
      }))

# ── Restart hotspot ───────────────────────────────────────────────────────────
print("\n[8] Restarting hotspot...")
for h in hs:
    api.get_resource("/ip/hotspot").call("set", {"numbers": h[".id"], "disabled": "yes"})
time.sleep(2)
for h in hs:
    api.get_resource("/ip/hotspot").call("set", {"numbers": h[".id"], "disabled": "no"})
print(f"  [✓] Hotspot restarted")

# ── Verify ────────────────────────────────────────────────────────────────────
print("\n[9] Verifying...")
wifi_r = api.get_resource("/interface/wifi")
for iface in wifi_r.get():
    nm = iface.get("name")
    disabled = iface.get("disabled", "false")
    if disabled == "true":
        print(f"  {nm}: disabled (ok for wifi2)")
        continue
    try:
        mon = wifi_r.call("monitor", {"numbers": nm, "once": ""})
        if mon:
            ch = mon[0].get("channel","?")
            st = mon[0].get("state","?")
            peers = mon[0].get("registered-peers","0")
            print(f"  {nm}: state={st}  channel={ch}  clients={peers}")
    except Exception as e:
        print(f"  {nm}: {e}")

pool.disconnect()
print("\n✓ Done. Tell clients to reconnect to 'S & J Enterprises'.\n")
