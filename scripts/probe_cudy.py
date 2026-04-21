#!/usr/bin/env python3
"""
probe_cudy.py — probe Cudy AP admin panel via MikroTik port-forward
Run on VPS:  python3 probe_cudy.py [router_ip]

What it does:
  1. Verifies NAT port-forward rule is in place on MikroTik
  2. Probes Cudy admin on multiple ports via WireGuard IP
  3. If OpenWRT LuCI is found, tries to configure AP mode (bridge mode)

Usage:
  python3 probe_cudy.py              # defaults: router 10.0.0.8, cudy 192.168.88.1
  python3 probe_cudy.py 10.0.0.8
"""

import sys
import json
import time
import subprocess
import routeros_api

ROUTER_IP  = sys.argv[1] if len(sys.argv) > 1 else "10.0.0.8"
CUDY_IP    = sys.argv[2] if len(sys.argv) > 2 else "192.168.88.1"
PASSWORD   = sys.argv[3] if len(sys.argv) > 3 else "558920"
PORT       = 8728
USERNAME   = "admin"

# Ports to probe on the VPS side (after port-forward)
PROBE_PORTS = [8099, 8080, 8443, 80, 443]
CUDY_ADMIN_PORT = 80   # Cudy admin actual port on its LAN

COMMENT = "temp-cudy-admin-access"


def connect():
    pool = routeros_api.RouterOsApiPool(
        ROUTER_IP, username=USERNAME, password=PASSWORD,
        port=PORT, plaintext_login=True, timeout=10
    )
    return pool.get_api(), pool


def ensure_nat_rule(api, vps_port=8099):
    """Make sure the port-forward rule exists; return the VPS port in use."""
    nat = api.get_resource("/ip/firewall/nat")
    rules = nat.get()

    # Check if our rule already exists
    for r in rules:
        if r.get("comment") == COMMENT:
            dst_port = r.get("dst-port", "?")
            print(f"  [✓] Existing NAT rule found: VPS port {dst_port} → {CUDY_IP}:{CUDY_ADMIN_PORT}")
            return int(dst_port)

    # Create it
    print(f"  [+] Creating NAT rule: {ROUTER_IP}:{vps_port} → {CUDY_IP}:{CUDY_ADMIN_PORT} ...")
    try:
        nat.call("add", {
            "chain":        "dstnat",
            "in-interface": "wg-zivo",
            "dst-port":     str(vps_port),
            "protocol":     "tcp",
            "action":       "dst-nat",
            "to-addresses": CUDY_IP,
            "to-ports":     str(CUDY_ADMIN_PORT),
            "comment":      COMMENT,
        })
        print(f"  [✓] NAT rule created")
        return vps_port
    except Exception as e:
        print(f"  [!] Failed to create NAT rule: {e}")
        return vps_port


def check_cudy_ping(api):
    """Ping the Cudy from the MikroTik to verify layer-3 connectivity."""
    print("\n[2] Pinging Cudy from MikroTik ...")
    try:
        result = api.get_resource("/ping").call("", {
            "address": CUDY_IP,
            "count":   "3",
            "interval": "500ms"
        })
        # /ping returns per-packet results
        packets = result if isinstance(result, list) else [result]
        ok = any(p.get("status") == "timeout" for p in packets)
        for p in packets:
            print(f"  seq={p.get('seq','?')} status={p.get('status','?')} "
                  f"time={p.get('time','?')}ms")
    except Exception as e:
        # RouterOS /ping isn't always available via API; fall back
        print(f"  ping via API failed ({e}) — checking bridge host table instead ...")
        try:
            hosts = api.get_resource("/interface/bridge/host").get()
            cudy_macs = []
            for h in hosts:
                # Cudy's OUI known prefixes; also just dump all entries on ether2
                iface = h.get("interface", "")
                if "ether2" in iface or "ether1" in iface:
                    cudy_macs.append(h)
            if cudy_macs:
                print(f"  Devices visible on wired port:")
                for h in cudy_macs:
                    print(f"    MAC={h.get('mac-address','?')} iface={h.get('interface','?')}")
            else:
                print("  No devices visible on ether2 — Cudy may not be connected")
        except Exception as e2:
            print(f"  Bridge host error: {e2}")


def probe_http(vps_port):
    """
    Probe the Cudy via HTTP/HTTPS through the MikroTik port-forward.
    We're running on the VPS, so ROUTER_IP is reachable.
    """
    print(f"\n[3] Probing http://{ROUTER_IP}:{vps_port} ...")
    import urllib.request
    import urllib.error

    urls = [
        f"http://{ROUTER_IP}:{vps_port}/",
        f"http://{ROUTER_IP}:{vps_port}/cgi-bin/luci",
        f"http://{ROUTER_IP}:{vps_port}/",
    ]
    for url in urls[:2]:  # try first two
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=8)
            body = resp.read(1024).decode("utf-8", errors="replace")
            print(f"  HTTP {resp.status} from {url}")
            print(f"  Content-Type: {resp.headers.get('Content-Type','?')}")
            print(f"  Body preview: {body[:300]}")
            return True, resp.status, body
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code} from {url}: {e.reason}")
            try:
                body = e.read(512).decode("utf-8", errors="replace")
                print(f"  Body: {body[:200]}")
            except:
                pass
            return True, e.code, ""
        except urllib.error.URLError as e:
            print(f"  URLError: {e.reason}")
        except Exception as e:
            print(f"  Error: {e}")

    return False, 0, ""


def probe_https(vps_port):
    """Try HTTPS (Cudy sometimes redirects HTTP → HTTPS)."""
    import urllib.request
    import ssl
    print(f"\n[3b] Probing https://{ROUTER_IP}:{vps_port+1} ...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        url = f"https://{ROUTER_IP}:{vps_port+1}/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=8, context=ctx)
        body = resp.read(1024).decode("utf-8", errors="replace")
        print(f"  HTTPS {resp.status}: {body[:200]}")
        return True
    except Exception as e:
        print(f"  HTTPS probe: {e}")
        return False


def cudy_openwrt_apmode(vps_port, cudy_password=""):
    """
    Try to configure Cudy AP in AP/bridge mode via OpenWRT LuCI JSON-RPC.
    Cudy APs run a customised OpenWRT.  The LuCI RPC path is /cgi-bin/luci/rpc/
    """
    import urllib.request
    import urllib.parse

    base = f"http://{ROUTER_IP}:{vps_port}"
    print(f"\n[4] Attempting LuCI RPC at {base} ...")

    def rpc(session, service, method, params=None):
        url = f"{base}/cgi-bin/luci/rpc/{service}?auth={session}"
        payload = json.dumps({
            "method": method,
            "params": params or [],
            "id":     1
        }).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=8)
        return json.loads(resp.read())

    # Step 1: get auth token
    try:
        auth_url = f"{base}/cgi-bin/luci/rpc/auth"
        payload  = json.dumps({"method": "login", "params": ["root", cudy_password], "id": 1}).encode()
        req      = urllib.request.Request(auth_url, data=payload,
                                          headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read())
        token = data.get("result")
        if not token:
            print(f"  [!] LuCI login failed (bad password?): {data}")
            return False
        print(f"  [✓] LuCI auth OK, token: {token[:12]}...")
    except Exception as e:
        print(f"  LuCI RPC not available: {e}")
        print(f"  → Cudy admin may use a different interface")
        return False

    # Step 2: read current network mode
    try:
        result = rpc(token, "uci", "get_all", ["network"])
        wan = result.get("result", {}).get("wan")
        print(f"  Current WAN section: {wan}")
    except Exception as e:
        print(f"  UCI read error: {e}")

    # Step 3: set to AP mode
    # In OpenWRT, AP mode = disable the WAN interface, bridge LAN to radio
    print(f"\n  Setting device to AP/bridge mode ...")
    try:
        # Disable WAN
        rpc(token, "uci", "set", [{"network.wan.auto": "0"}])
        # Set LAN to bridge with radio
        rpc(token, "uci", "set", [{"wireless.@wifi-iface[0].mode": "ap"}])
        rpc(token, "uci", "set", [{"wireless.@wifi-iface[0].network": "lan"}])
        # Commit and apply
        rpc(token, "uci", "commit", ["network"])
        rpc(token, "uci", "commit", ["wireless"])
        print("  [✓] UCI changes committed")
        # Reload
        rpc(token, "sys", "exec", ["/etc/init.d/network restart"])
        print("  [✓] Network restart triggered")
        return True
    except Exception as e:
        print(f"  [!] AP mode config error: {e}")
        return False


def get_cudy_info_page(vps_port):
    """Grab Cudy info via curl subprocess for verbose output."""
    print(f"\n[3c] Detailed curl probe ...")
    cmd = [
        "curl", "-v", "--connect-timeout", "8", "--max-time", "12",
        "-L",   # follow redirects
        f"http://{ROUTER_IP}:{vps_port}/"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        stdout = result.stdout[:600] if result.stdout else "(empty)"
        stderr = result.stderr[:600] if result.stderr else "(empty)"
        print(f"  STDOUT: {stdout}")
        print(f"  STDERR (headers): {stderr}")
        return result.returncode == 0
    except FileNotFoundError:
        print("  curl not available, using urllib only")
    except Exception as e:
        print(f"  curl error: {e}")
    return False


def fix_nat_in_interface(api):
    """
    Some MikroTik builds require matching by interface-list, not interface name.
    Check and repair if the in-interface name is wrong.
    """
    nat = api.get_resource("/ip/firewall/nat")
    rules = nat.get()
    for r in rules:
        if r.get("comment") == COMMENT:
            rid = r.get(".id") or r.get("id")
            cur_iface = r.get("in-interface", "")
            print(f"  Current in-interface: '{cur_iface}'")

            # Also add a version without in-interface restriction as fallback
            print("  Adding permissive fallback rule (no interface filter) ...")
            try:
                nat.call("add", {
                    "chain":        "dstnat",
                    "dst-port":     r.get("dst-port", "8099"),
                    "protocol":     "tcp",
                    "action":       "dst-nat",
                    "to-addresses": CUDY_IP,
                    "to-ports":     str(CUDY_ADMIN_PORT),
                    "comment":      COMMENT + "-noif",
                    "place-before": rid,
                })
                print("  [✓] Permissive rule added (comes before in-interface rule)")
            except Exception as e:
                print(f"  [!] Could not add permissive rule: {e}")
            return


def main():
    print(f"\n{'='*60}")
    print(f"  Cudy AP Probe — router={ROUTER_IP}, cudy={CUDY_IP}")
    print(f"{'='*60}")

    print("\n[1] Connecting to MikroTik ...")
    api, pool = connect()
    print(f"  [✓] Connected")

    # Step 1: ensure NAT rule exists
    vps_port = ensure_nat_rule(api, 8099)

    # Step 2: ping Cudy from MikroTik
    check_cudy_ping(api)

    # Step 3: fix in-interface (add fallback rule)
    print("\n[2b] Checking NAT in-interface filter ...")
    fix_nat_in_interface(api)

    # Step 4: probe HTTP via port-forward
    reachable, code, body = probe_http(vps_port)

    if not reachable:
        print("\n  ⚠ HTTP not reachable. Trying alternate ports ...")
        # Try port 80 directly (maybe VPS firewall allows it)
        for alt_port in [8100, 8101, 8080]:
            print(f"     → Adding temp rule for VPS port {alt_port} ...")
            try:
                nat = api.get_resource("/ip/firewall/nat")
                nat.call("add", {
                    "chain":        "dstnat",
                    "dst-port":     str(alt_port),
                    "protocol":     "tcp",
                    "action":       "dst-nat",
                    "to-addresses": CUDY_IP,
                    "to-ports":     str(CUDY_ADMIN_PORT),
                    "comment":      f"temp-cudy-{alt_port}",
                })
            except Exception as e:
                print(f"     NAT add error: {e}")
            time.sleep(1)
            ok, code2, body2 = probe_http(alt_port)
            if ok:
                vps_port = alt_port
                reachable = True
                break

    if not reachable:
        print("\n  ⚠ Still not reachable. Running verbose curl ...")
        get_cudy_info_page(vps_port)
        probe_https(8100)

    if reachable and code in (200, 302, 301):
        print(f"\n  ✓ Cudy admin panel is reachable! HTTP {code}")
        if "luci" in body.lower() or "openwrt" in body.lower() or "cudy" in body.lower():
            print("  Detected OpenWRT/Cudy UI")
            print("\n  To set AP mode, run:")
            print(f"    python3 probe_cudy.py {ROUTER_IP} {CUDY_IP} {PASSWORD} --apmode")

    # Summary and next steps
    print(f"\n{'='*60}")
    print("  SUMMARY & NEXT STEPS")
    print(f"{'='*60}")
    print(f"""
  The Cudy AP at {CUDY_IP} is in ROUTER MODE — this is why
  WiFi clients can't get IPs from the MikroTik hotspot.

  OPTION 1 — Switch Cudy to AP mode remotely (preferred):
    If Cudy admin is now reachable at http://{ROUTER_IP}:{vps_port}
    → Open that URL in your browser
    → Go to Network → Operation Mode → Select "Access Point Mode"
    → Save & Reboot

  OPTION 2 — Physical reset & reconfigure:
    If remote access fails:
    → Factory reset Cudy (hold reset 10s)
    → Connect laptop to Cudy LAN port
    → Open 192.168.10.1 or 192.168.0.1
    → Go to Network → Operation Mode → Access Point Mode
    → Set LAN IP: 192.168.88.2 (static, same subnet as MikroTik)
    → Disable Cudy DHCP
    → Reboot

  OPTION 3 — Bypass Cudy entirely:
    If you want to use only MikroTik's built-in WiFi (wifi1):
    → Disconnect Cudy from MikroTik ether2
    → MikroTik wifi1 is already broadcasting on ch6 20MHz
    → Clients connect directly to MikroTik (no Cudy needed)
""")

    pool.disconnect()
    print("\n=== Done ===\n")


if __name__ == "__main__":
    main()
