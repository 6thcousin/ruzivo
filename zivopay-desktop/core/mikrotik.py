"""core/mikrotik.py — RouterOS API operations"""
import routeros_api
import time


def connect(host, port=8728, username="admin", password=""):
    pool = routeros_api.RouterOsApiPool(
        host, username=username, password=password,
        port=int(port), plaintext_login=True,
    )
    return pool.get_api(), pool


def test_connection(host, port, username, password):
    try:
        api, pool = connect(host, port, username, password)
        res  = api.get_resource("/system/resource").get()[0]
        name = api.get_resource("/system/identity").get()[0].get("name", "?")
        pool.disconnect()
        return {
            "success":  True,
            "identity": name,
            "version":  res.get("version", "?"),
            "board":    res.get("board-name", "?"),
            "uptime":   res.get("uptime", "?"),
            "arch":     res.get("architecture-name", "?"),
            "cpu":      res.get("cpu-load", "?"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_stats(host, port, username, password):
    try:
        api, pool = connect(host, port, username, password)
        res  = api.get_resource("/system/resource").get()[0]
        name = api.get_resource("/system/identity").get()[0].get("name", "?")

        fm  = int(res.get("free-memory",  0))
        tm  = int(res.get("total-memory", 1))
        mem = f"{round((tm-fm)/tm*100)}%"

        try:
            sessions = len(api.get_resource("/ip/hotspot/active").get())
        except Exception:
            sessions = 0

        peers = 0
        try:
            wifi = api.get_resource("/interface/wifi")
            for iface in wifi.get():
                mon = wifi.call("monitor", {"numbers": iface.get("name"), "once": ""})
                if mon:
                    peers += int(mon[0].get("registered-peers", 0))
        except Exception:
            pass

        pool.disconnect()
        return {
            "success":  True,
            "identity": name,
            "cpu":      f"{res.get('cpu-load','?')}%",
            "memory":   mem,
            "uptime":   res.get("uptime", "?"),
            "version":  res.get("version", "?"),
            "sessions": sessions,
            "peers":    peers,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def push_full_config(host, port, username, password, cfg):
    """
    Push complete onboarding config to a fresh MikroTik.
    cfg = {
        identity, router_pass, ssid, ssid_5g,
        wg_ip, vps_pubkey, vps_host, vps_port,
        hotspot_name
    }
    Returns (success, message, wg_public_key)
    """
    results = []
    try:
        api, pool = connect(host, port, username, password)

        identity  = cfg["identity"].lower().replace(" ", "_").replace("&", "and")
        wg_listen = 15000 + int(cfg["wg_ip"].split(".")[-1])

        def r(label, fn):
            try:
                fn()
                results.append(f"[✓] {label}")
            except Exception as e:
                results.append(f"[!] {label}: {e}")

        # 1. Identity
        r("Identity", lambda: api.get_resource("/system/identity").call("set", {"name": identity}))

        # 2. Admin password
        r("Admin password", lambda: api.get_resource("/user").call(
            "set", {"numbers": "0", "password": cfg["router_pass"]}
        ))

        # 3. WireGuard interface
        r("WireGuard interface", lambda: api.get_resource("/interface/wireguard").call("add", {
            "name": "wg-zivo", "listen-port": str(wg_listen), "mtu": "1420"
        }))

        # 4. WireGuard peer (VPS)
        r("WireGuard peer", lambda: api.get_resource("/interface/wireguard/peers").call("add", {
            "interface":           "wg-zivo",
            "public-key":          cfg["vps_pubkey"],
            "endpoint-address":    cfg["vps_host"],
            "endpoint-port":       str(cfg["vps_port"]),
            "allowed-address":     "10.0.0.0/24",
            "persistent-keepalive": "25",
        }))

        # 5. WireGuard IP
        r("WireGuard IP", lambda: api.get_resource("/ip/address").call("add", {
            "address": f"{cfg['wg_ip']}/24", "interface": "wg-zivo"
        }))

        # 6. Bridge
        r("Bridge", lambda: api.get_resource("/interface/bridge").call("add", {
            "name": "bridgeLocal", "protocol-mode": "none", "fast-forward": "no"
        }))

        # 7. Bridge ports
        r("Bridge port ether2", lambda: api.get_resource("/interface/bridge/port").call("add", {
            "bridge": "bridgeLocal", "interface": "ether2"
        }))
        r("Bridge port wifi1", lambda: api.get_resource("/interface/bridge/port").call("add", {
            "bridge": "bridgeLocal", "interface": "wifi1"
        }))

        # 8. LAN IP
        r("LAN IP", lambda: api.get_resource("/ip/address").call("add", {
            "address": "192.168.88.1/24", "interface": "bridgeLocal"
        }))

        # 9. DHCP pool
        r("DHCP pool", lambda: api.get_resource("/ip/pool").call("add", {
            "name": "hs_pool", "ranges": "192.168.88.10-192.168.88.254"
        }))

        # 10. DHCP server
        r("DHCP server", lambda: api.get_resource("/ip/dhcp-server").call("add", {
            "name": "hs_dhcp", "interface": "bridgeLocal",
            "address-pool": "hs_pool", "lease-time": "30m", "disabled": "no"
        }))

        # 11. DHCP network
        r("DHCP network", lambda: api.get_resource("/ip/dhcp-server/network").call("add", {
            "address": "192.168.88.0/24",
            "gateway": "192.168.88.1",
            "dns-server": "8.8.8.8,8.8.4.4"
        }))

        # 12. DNS
        r("DNS", lambda: api.get_resource("/ip/dns").call("set", {
            "allow-remote-requests": "yes", "servers": "8.8.8.8,8.8.4.4"
        }))

        # 13. NAT
        r("NAT masquerade", lambda: api.get_resource("/ip/firewall/nat").call("add", {
            "chain": "srcnat", "action": "masquerade", "out-interface": "ether1"
        }))

        # 14. WiFi 2.4GHz
        r("WiFi 2.4GHz", lambda: api.get_resource("/interface/wifi").call("set", {
            "numbers": "wifi1",
            "configuration.ssid": cfg["ssid"],
            "configuration.country": "Zimbabwe",
            "channel.frequency": "2437",
            "channel.width": "20mhz",
            "disabled": "no"
        }))

        # 15. WiFi 5GHz (if specified)
        if cfg.get("ssid_5g"):
            r("WiFi 5GHz enable", lambda: api.get_resource("/interface/wifi").call("set", {
                "numbers": "wifi2",
                "configuration.ssid": cfg["ssid_5g"],
                "configuration.country": "Zimbabwe",
                "channel.frequency": "5180",
                "channel.width": "20mhz",
                "disabled": "no"
            }))
            r("Bridge port wifi2", lambda: api.get_resource("/interface/bridge/port").call("add", {
                "bridge": "bridgeLocal", "interface": "wifi2"
            }))

        # 16. Hotspot profile
        r("Hotspot profile", lambda: api.get_resource("/ip/hotspot/profile").call("add", {
            "name": "hsprof1",
            "hotspot-address": "192.168.88.1",
            "login-by": "http-chap,mac",
            "use-radius": "no",
            "html-directory": "hotspot",
        }))

        # 17. Hotspot server
        r("Hotspot server", lambda: api.get_resource("/ip/hotspot").call("add", {
            "name": "hotspot1",
            "interface": "bridgeLocal",
            "address-pool": "hs_pool",
            "profile": "hsprof1",
            "keepalive-timeout": "2m",
            "disabled": "no",
        }))

        # 18. Route
        r("VPN route", lambda: api.get_resource("/ip/route").call("add", {
            "dst-address": "10.0.0.0/24", "gateway": "wg-zivo"
        }))

        # 19. Enable API service
        r("API service", lambda: api.get_resource("/ip/service").call(
            "set", {"numbers": "api", "disabled": "no"}
        ))

        # 20. Read WireGuard public key
        wg_key = ""
        try:
            ifaces = api.get_resource("/interface/wireguard").get()
            for i in ifaces:
                if i.get("name") == "wg-zivo":
                    wg_key = i.get("public-key", "")
                    break
            results.append(f"[✓] WireGuard public key: {wg_key[:20]}…")
        except Exception as e:
            results.append(f"[!] Could not read WG key: {e}")

        pool.disconnect()
        return True, "\n".join(results), wg_key

    except Exception as e:
        return False, f"Connection failed: {e}\n" + "\n".join(results), ""


def apply_quick_fix(host, port, username, password, fix_key):
    fixes = {
        "wifi_fix":        _fix_wifi,
        "bridge_fix":      _fix_bridge,
        "dhcp_cleanup":    _fix_dhcp,
        "hotspot_restart": _fix_hotspot_restart,
        "clear_bindings":  _fix_clear_bindings,
        "reboot":          _fix_reboot,
    }
    if fix_key not in fixes:
        return False, "Unknown fix"
    try:
        api, pool = connect(host, port, username, password)
        result = fixes[fix_key](api)
        pool.disconnect()
        return True, result
    except Exception as e:
        return False, str(e)


def _fix_wifi(api):
    out = []
    try:
        wifi = api.get_resource("/interface/wifi")
        for i in wifi.get():
            nm = i.get("name")
            wifi.call("set", {"numbers": nm, "configuration.country": "Zimbabwe"})
        out.append("[✓] WiFi country set to Zimbabwe")
        # Clear reject rules
        r = api.get_resource("/interface/wifi/access-list")
        rejects = [x for x in r.get() if x.get("action") == "reject"]
        for x in rejects:
            r.remove(id=x.get(".id") or x.get("id"))
        out.append(f"[✓] Removed {len(rejects)} reject rule(s)")
    except Exception as e:
        out.append(f"[!] WiFi fix error: {e}")
    return "\n".join(out)


def _fix_bridge(api):
    out = []
    try:
        for b in api.get_resource("/interface/bridge").get():
            api.get_resource("/interface/bridge").call("set", {
                "numbers": b.get(".id"), "protocol-mode": "none", "fast-forward": "no"
            })
        out.append("[✓] Bridge: protocol-mode=none, fast-forward=no")
    except Exception as e:
        out.append(f"[!] Bridge fix error: {e}")
    return "\n".join(out)


def _fix_dhcp(api):
    out = []
    try:
        leases = api.get_resource("/ip/dhcp-server/lease")
        stale  = [l for l in leases.get() if l.get("status") in ("expired", "abandoned")]
        for l in stale:
            leases.remove(id=l.get(".id"))
        out.append(f"[✓] Cleared {len(stale)} stale DHCP leases")
    except Exception as e:
        out.append(f"[!] DHCP cleanup error: {e}")
    return "\n".join(out)


def _fix_hotspot_restart(api):
    out = []
    try:
        hs = api.get_resource("/ip/hotspot").get()
        for h in hs:
            api.get_resource("/ip/hotspot").call("set", {"numbers": h.get(".id"), "disabled": "yes"})
        time.sleep(2)
        for h in hs:
            api.get_resource("/ip/hotspot").call("set", {"numbers": h.get(".id"), "disabled": "no"})
        out.append(f"[✓] Hotspot restarted ({len(hs)} instance(s))")
    except Exception as e:
        out.append(f"[!] Hotspot restart error: {e}")
    return "\n".join(out)


def _fix_clear_bindings(api):
    out = []
    try:
        binds   = api.get_resource("/ip/hotspot/ip-binding")
        blocked = [b for b in binds.get() if b.get("type") == "blocked"]
        for b in blocked:
            binds.remove(id=b.get(".id"))
        out.append(f"[✓] Cleared {len(blocked)} blocked IP binding(s)")
    except Exception as e:
        out.append(f"[!] Clear bindings error: {e}")
    return "\n".join(out)


def _fix_reboot(api):
    api.get_resource("/system").call("reboot")
    return "[✓] Reboot command sent"
