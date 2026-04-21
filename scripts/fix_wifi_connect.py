#!/usr/bin/env python3
"""
fix_wifi_connect.py
───────────────────
Diagnoses and fixes total WiFi connection failures on MikroTik (RouterOS 7, new wifi package).
Run on the VPS:  python3 /tmp/fix_wifi_connect.py <router_ip>

Common causes addressed:
  1. WiFi access-list deny rules (blocking association at OS level)
  2. wifi2 (5GHz) disabled or unconfigured
  3. 40 MHz channel width compatibility (Ce → C to force 20MHz)
  4. max-station-count too low
  5. Hotspot interface binding issues
"""

import sys
import routeros_api

ROUTER_IP = sys.argv[1] if len(sys.argv) > 1 else "10.0.0.7"
USERNAME   = "admin"
PASSWORD   = "558920"
PORT       = 8728

def connect():
    pool = routeros_api.RouterOsApiPool(
        ROUTER_IP, username=USERNAME, password=PASSWORD,
        port=PORT, plaintext_login=True
    )
    return pool.get_api(), pool


def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def diagnose(api):
    section("1. WiFi Access-List (must be empty or allow-only)")
    try:
        r = api.get_resource("/interface/wifi/access-list")
        rules = r.get()
        if not rules:
            print("  [✓] Access-list is empty — no deny rules")
        else:
            print(f"  [!] {len(rules)} rule(s) found:")
            for rule in rules:
                action = rule.get("action", "?")
                mac    = rule.get("mac-address", "*")
                ssid   = rule.get("ssid-regexp", "any")
                print(f"      action={action}  mac={mac}  ssid={ssid}")
                if action == "reject":
                    print(f"      *** REJECT rule — this blocks devices! ***")
    except Exception as e:
        print(f"  access-list error: {e}")

    section("2. WiFi Interface Status")
    try:
        r = api.get_resource("/interface/wifi")
        ifaces = r.get()
        for iface in ifaces:
            name     = iface.get("name", "?")
            disabled = iface.get("disabled", "false")
            running  = iface.get("running", "false")
            mac      = iface.get("mac-address", "?")
            print(f"  {name}: disabled={disabled} running={running} mac={mac}")
    except Exception as e:
        print(f"  wifi interface error: {e}")

    section("3. WiFi Monitor (live radio state)")
    try:
        r = api.get_resource("/interface/wifi")
        ifaces = r.get()
        for iface in ifaces:
            name = iface.get("name")
            try:
                mon = r.call("monitor", {"numbers": name, "once": ""})
                for m in mon:
                    ch        = m.get("channel", "?")
                    tx_power  = m.get("tx-power", "?")
                    clients   = m.get("registered-peers", "0")
                    state     = m.get("state", "?")
                    print(f"  {name}: channel={ch} tx-power={tx_power} clients={clients} state={state}")
            except Exception as e:
                print(f"  {name} monitor error: {e}")
    except Exception as e:
        print(f"  monitor error: {e}")

    section("4. WiFi Security Profiles")
    try:
        r = api.get_resource("/interface/wifi/security")
        items = r.get()
        if not items:
            print("  [✓] No security profiles (open network — correct for hotspot)")
        else:
            for i in items:
                print(f"  {i}")
    except Exception as e:
        print(f"  security error: {e}")

    section("5. WiFi Datapath (bridge assignment)")
    try:
        r = api.get_resource("/interface/wifi/datapath")
        items = r.get()
        for i in items:
            print(f"  {i}")
        if not items:
            print("  No datapath configs defined")
    except Exception as e:
        print(f"  datapath error: {e}")

    section("6. Hotspot Interface Binding")
    try:
        r = api.get_resource("/ip/hotspot")
        hs = r.get()
        for h in hs:
            print(f"  hotspot: name={h.get('name')} interface={h.get('interface')} disabled={h.get('disabled')}")
    except Exception as e:
        print(f"  hotspot error: {e}")

    section("7. Hotspot IP Bindings (blocked MACs)")
    try:
        r = api.get_resource("/ip/hotspot/ip-binding")
        binds = r.get()
        blocked = [b for b in binds if b.get("type") == "blocked"]
        print(f"  Total bindings: {len(binds)}, Blocked: {len(blocked)}")
        for b in blocked:
            print(f"  BLOCKED: mac={b.get('mac-address')} ip={b.get('address')}")
    except Exception as e:
        print(f"  ip-binding error: {e}")

    section("8. DHCP Server + Pool")
    try:
        r = api.get_resource("/ip/dhcp-server")
        servers = r.get()
        for s in servers:
            print(f"  DHCP: name={s.get('name')} interface={s.get('interface')} disabled={s.get('disabled')} lease-time={s.get('lease-time')}")
        r2 = api.get_resource("/ip/pool")
        pools = r2.get()
        for p in pools:
            print(f"  Pool: name={p.get('name')} ranges={p.get('ranges')}")
    except Exception as e:
        print(f"  DHCP error: {e}")

    section("9. Bridge + Port State")
    try:
        r = api.get_resource("/interface/bridge")
        bridges = r.get()
        for b in bridges:
            print(f"  Bridge: {b.get('name')} protocol-mode={b.get('protocol-mode')} fast-forward={b.get('fast-forward')}")
        r2 = api.get_resource("/interface/bridge/port")
        ports = r2.get()
        for p in ports:
            print(f"  Port: iface={p.get('interface')} bridge={p.get('bridge')} disabled={p.get('disabled')} edge={p.get('edge')} horizon={p.get('horizon')}")
    except Exception as e:
        print(f"  bridge error: {e}")

    section("10. Log entries mentioning wifi/assoc/auth")
    try:
        r = api.get_resource("/log")
        logs = r.get()
        wifi_logs = [
            l for l in logs
            if any(kw in l.get("message","").lower()
                   for kw in ("wifi", "assoc", "auth", "deauth", "disassoc", "rejected", "blocked", "denied"))
        ]
        if wifi_logs:
            for l in wifi_logs[-20:]:
                print(f"  [{l.get('time','')}] {l.get('message','')}")
        else:
            print("  No wifi-related log entries found")
    except Exception as e:
        print(f"  log error: {e}")


def apply_fixes(api):
    section("APPLYING FIXES")

    # Fix 1: Remove reject rules from access-list
    try:
        r = api.get_resource("/interface/wifi/access-list")
        rules = r.get()
        reject_ids = [rule["id"] for rule in rules if rule.get("action") == "reject"]
        if reject_ids:
            for rid in reject_ids:
                r.remove(id=rid)
            print(f"  [✓] Removed {len(reject_ids)} reject rule(s) from access-list")
        else:
            print("  [✓] No reject rules to remove")
    except Exception as e:
        print(f"  access-list fix error: {e}")

    # Fix 2: Enable wifi2 if disabled
    try:
        r = api.get_resource("/interface/wifi")
        ifaces = r.get()
        for iface in ifaces:
            if iface.get("disabled") == "true":
                name = iface.get("name")
                r.call("enable", {"numbers": name})
                print(f"  [✓] Enabled {name}")
    except Exception as e:
        print(f"  enable wifi error: {e}")

    # Fix 3: Force 20 MHz on 2.4GHz (wifi1) to improve compatibility
    # Ce = 40MHz extension above; C = 20MHz only — safer for mixed clients
    try:
        r = api.get_resource("/interface/wifi")
        ifaces = r.get()
        for iface in ifaces:
            name = iface.get("name", "")
            # only adjust 2.4GHz radios
            channel = iface.get("channel", "") or ""
            if "2.4" in channel or "2447" in channel or "2412" in channel or name == "wifi1":
                try:
                    # Set channel width to Ceee (20MHz) or just remove extension
                    r.call("set", {
                        "numbers": name,
                        "channel.width": "20mhz",
                    })
                    print(f"  [✓] {name}: set channel width to 20MHz for compatibility")
                except Exception as e2:
                    print(f"  {name} channel width fix error: {e2}")
    except Exception as e:
        print(f"  channel width error: {e}")

    # Fix 4: max-station-count — ensure no artificial limit
    try:
        r = api.get_resource("/interface/wifi")
        ifaces = r.get()
        for iface in ifaces:
            name = iface.get("name")
            max_st = iface.get("max-station-count", "")
            if max_st and max_st not in ("0", "unlimited", ""):
                try:
                    r.call("set", {"numbers": name, "max-station-count": "0"})
                    print(f"  [✓] {name}: removed max-station-count limit (was {max_st})")
                except Exception as e2:
                    print(f"  max-station fix error: {e2}")
    except Exception as e:
        print(f"  max-station-count error: {e}")

    # Fix 5: Clear blocked IP bindings that shouldn't be there
    try:
        r = api.get_resource("/ip/hotspot/ip-binding")
        binds = r.get()
        blocked = [b for b in binds if b.get("type") == "blocked"]
        for b in blocked:
            r.remove(id=b["id"])
        if blocked:
            print(f"  [✓] Removed {len(blocked)} blocked IP binding(s)")
    except Exception as e:
        print(f"  ip-binding fix error: {e}")

    print("\n  All fixes applied. Recommend running diagnose again to verify.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MikroTik WiFi connect-failure fixer")
    parser.add_argument("router_ip", nargs="?", default="10.0.0.7")
    parser.add_argument("--fix", action="store_true", help="Apply fixes (default: diagnose only)")
    args = parser.parse_args()

    ROUTER_IP = args.router_ip

    print(f"Connecting to {ROUTER_IP}:{PORT} ...")
    api, pool = connect()
    print(f"Connected.")

    diagnose(api)

    if args.fix:
        apply_fixes(api)
        print("\nRe-running diagnostics after fixes:")
        diagnose(api)

    pool.disconnect()
    print("\n=== Done ===")
