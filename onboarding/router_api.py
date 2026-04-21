"""
router_api.py — RouterOS API wrapper for ZivoPay Onboarding
"""

import json
import time
import routeros_api


# ── Connection ────────────────────────────────────────────────────────────────

def _connect(host, port, username, password):
    pool = routeros_api.RouterOsApiPool(
        host, username=username, password=password,
        port=int(port), plaintext_login=True,
        timeout=8,
    )
    return pool.get_api(), pool


def test_connection(host, port, username, password):
    try:
        api, pool = _connect(host, port, username, password)
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
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Live stats ────────────────────────────────────────────────────────────────

def get_stats(host, port, username, password):
    try:
        api, pool = _connect(host, port, username, password)

        res  = api.get_resource("/system/resource").get()[0]
        name = api.get_resource("/system/identity").get()[0].get("name", "?")

        cpu       = res.get("cpu-load", "?")
        free_mem  = int(res.get("free-memory",  0))
        total_mem = int(res.get("total-memory", 1))
        mem_pct   = round((total_mem - free_mem) / total_mem * 100)
        used_mb   = round((total_mem - free_mem) / 1_048_576, 1)
        total_mb  = round(total_mem / 1_048_576, 1)

        # Hotspot sessions
        try:
            sessions = len(api.get_resource("/ip/hotspot/active").get())
        except Exception:
            sessions = "N/A"

        # WiFi registered peers (new wifi package)
        try:
            wifi_res = api.get_resource("/interface/wifi")
            ifaces   = wifi_res.get()
            peers    = 0
            channels = []
            for iface in ifaces:
                try:
                    mon = wifi_res.call("monitor", {"numbers": iface.get("name"), "once": ""})
                    if mon:
                        peers    += int(mon[0].get("registered-peers", 0))
                        channels.append(mon[0].get("channel", "?"))
                except Exception:
                    pass
        except Exception:
            peers, channels = "N/A", []

        pool.disconnect()
        return {
            "success":    True,
            "identity":   name,
            "cpu_load":   f"{cpu}%",
            "memory":     f"{mem_pct}% ({used_mb}/{total_mb} MB)",
            "uptime":     res.get("uptime", "?"),
            "version":    res.get("version", "?"),
            "sessions":   sessions,
            "wifi_peers": peers,
            "channels":   ", ".join(channels) if channels else "N/A",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Predefined commands ───────────────────────────────────────────────────────

COMMANDS = {
    "system_info":     ("System Info",          "bi-cpu"),
    "hotspot_users":   ("Hotspot Sessions",      "bi-people"),
    "wifi_clients":    ("WiFi Clients",          "bi-wifi"),
    "dhcp_leases":     ("DHCP Leases",           "bi-list-ul"),
    "ip_bindings":     ("IP Bindings",           "bi-shield"),
    "vouchers":        ("Vouchers / Users",      "bi-ticket-perforated"),
    "wg_status":       ("WireGuard Status",      "bi-shield-lock"),
    "bridge_status":   ("Bridge Status",         "bi-diagram-3"),
    "restart_hotspot": ("Restart Hotspot",       "bi-arrow-repeat"),
    "apply_wifi_fixes":("Apply WiFi Fixes",      "bi-tools"),
    "reboot":          ("Reboot Router",         "bi-power"),
}


def run_command(host, port, username, password, cmd_key):
    handlers = {
        "system_info":      _system_info,
        "hotspot_users":    _hotspot_users,
        "wifi_clients":     _wifi_clients,
        "dhcp_leases":      _dhcp_leases,
        "ip_bindings":      _ip_bindings,
        "vouchers":         _vouchers,
        "wg_status":        _wg_status,
        "bridge_status":    _bridge_status,
        "restart_hotspot":  _restart_hotspot,
        "apply_wifi_fixes": _apply_wifi_fixes,
        "reboot":           _reboot,
    }
    if cmd_key not in handlers:
        return {"success": False, "output": f"Unknown command: {cmd_key}"}
    try:
        api, pool = _connect(host, port, username, password)
        output = handlers[cmd_key](api)
        pool.disconnect()
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "output": f"Connection error: {e}"}


def run_raw(host, port, username, password, raw):
    """Execute a raw RouterOS API path + print, e.g. '/ip/address print'."""
    try:
        api, pool = _connect(host, port, username, password)
        parts  = raw.strip().split()
        path   = parts[0]
        action = parts[1] if len(parts) > 1 else "print"
        r      = api.get_resource(path)
        result = r.call(action) if action != "print" else r.get()
        pool.disconnect()
        return {"success": True, "output": json.dumps(result, indent=2, default=str)}
    except Exception as e:
        return {"success": False, "output": f"Error: {e}"}


# ── Command handlers ──────────────────────────────────────────────────────────

def _system_info(api):
    res  = api.get_resource("/system/resource").get()[0]
    name = api.get_resource("/system/identity").get()[0].get("name", "?")
    fm   = int(res.get("free-memory", 0))
    tm   = int(res.get("total-memory", 1))
    return "\n".join([
        f"Identity   : {name}",
        f"Version    : {res.get('version','?')}",
        f"Board      : {res.get('board-name','?')}",
        f"Arch       : {res.get('architecture-name','?')}",
        f"CPU Load   : {res.get('cpu-load','?')}%",
        f"Memory     : {round((tm-fm)/tm*100)}% ({round((tm-fm)/1_048_576,1)}/{round(tm/1_048_576,1)} MB)",
        f"Uptime     : {res.get('uptime','?')}",
        f"Free HDD   : {round(int(res.get('free-hdd-space',0))/1024)} KB",
        f"Write Sect : {res.get('write-sect-since-reboot','?')}",
    ])


def _hotspot_users(api):
    active = api.get_resource("/ip/hotspot/active").get()
    if not active:
        return "No active hotspot sessions."
    lines = [f"Active Sessions: {len(active)}\n"]
    for u in active:
        lines.append(
            f"  MAC: {u.get('mac-address','?'):<18}  IP: {u.get('address','?'):<16}"
            f"  User: {u.get('user','?'):<20}  Uptime: {u.get('uptime','?')}"
        )
    return "\n".join(lines)


def _wifi_clients(api):
    r      = api.get_resource("/interface/wifi")
    ifaces = r.get()
    lines  = []
    total  = 0
    for iface in ifaces:
        nm = iface.get("name", "?")
        try:
            mon  = r.call("monitor", {"numbers": nm, "once": ""})
            p    = int(mon[0].get("registered-peers", 0)) if mon else 0
            ch   = mon[0].get("channel", "?") if mon else "?"
            st   = mon[0].get("state", "?") if mon else "?"
            total += p
            lines.append(f"  {nm}: {p} clients  channel={ch}  state={st}")
        except Exception as e:
            lines.append(f"  {nm}: (error: {e})")
    return f"Total WiFi Clients: {total}\n" + "\n".join(lines)


def _dhcp_leases(api):
    leases = api.get_resource("/ip/dhcp-server/lease").get()
    if not leases:
        return "No DHCP leases."
    bound  = [l for l in leases if l.get("status") == "bound"]
    lines  = [f"Total: {len(leases)}   Active (bound): {len(bound)}\n"]
    for l in bound[:30]:
        lines.append(
            f"  {l.get('address','?'):<16}  {l.get('mac-address','?'):<18}"
            f"  {l.get('host-name','?'):<24}  expires: {l.get('expires-after','?')}"
        )
    if len(bound) > 30:
        lines.append(f"  ... and {len(bound)-30} more")
    return "\n".join(lines)


def _ip_bindings(api):
    binds = api.get_resource("/ip/hotspot/ip-binding").get()
    if not binds:
        return "No IP bindings configured."
    lines = [f"IP Bindings: {len(binds)}\n"]
    for b in binds:
        lines.append(
            f"  {b.get('mac-address','?'):<18}  {b.get('address','?'):<16}"
            f"  type={b.get('type','?'):<10}  disabled={b.get('disabled','?')}"
        )
    return "\n".join(lines)


def _vouchers(api):
    users  = api.get_resource("/ip/hotspot/user").get()
    active = {a.get("user") for a in api.get_resource("/ip/hotspot/active").get()}
    if not users:
        return "No hotspot users/vouchers."
    lines = [f"Hotspot Users: {len(users)}   Currently Active: {len(active)}\n"]
    for u in users[:40]:
        flag = "● ACTIVE" if u.get("name") in active else "  idle  "
        lines.append(
            f"  [{flag}]  {u.get('name','?'):<20}  profile={u.get('profile','?'):<16}"
            f"  limit-uptime={u.get('limit-uptime','-')}"
        )
    if len(users) > 40:
        lines.append(f"  ... and {len(users)-40} more")
    return "\n".join(lines)


def _wg_status(api):
    try:
        ifaces = api.get_resource("/interface/wireguard").get()
        peers  = api.get_resource("/interface/wireguard/peers").get()
    except Exception as e:
        return f"WireGuard not available: {e}"
    lines = [f"WireGuard Interfaces: {len(ifaces)}"]
    for i in ifaces:
        lines.append(f"  {i.get('name','?')}  listen-port={i.get('listen-port','?')}  disabled={i.get('disabled','?')}")
    lines.append(f"\nPeers: {len(peers)}")
    for p in peers:
        hs = p.get("last-handshake", "never")
        lines.append(
            f"  {p.get('public-key','?')[:28]}...  "
            f"endpoint={p.get('endpoint-address','?')}:{p.get('endpoint-port','?')}"
            f"  handshake={hs}"
        )
    return "\n".join(lines)


def _bridge_status(api):
    bridges = api.get_resource("/interface/bridge").get()
    ports   = api.get_resource("/interface/bridge/port").get()
    lines   = [f"Bridges: {len(bridges)}"]
    for b in bridges:
        lines.append(
            f"  {b.get('name','?'):<16}  protocol-mode={b.get('protocol-mode','?'):<8}"
            f"  fast-forward={b.get('fast-forward','?')}"
        )
    lines.append(f"\nPorts: {len(ports)}")
    for p in ports:
        lines.append(
            f"  {p.get('interface','?'):<16} → {p.get('bridge','?'):<16}"
            f"  disabled={p.get('disabled','?')}"
        )
    return "\n".join(lines)


def _restart_hotspot(api):
    hs = api.get_resource("/ip/hotspot").get()
    if not hs:
        return "No hotspot configured."
    for h in hs:
        hid = h.get(".id") or h.get("id") or h.get("name")
        api.get_resource("/ip/hotspot").call("set", {"numbers": hid, "disabled": "yes"})
    time.sleep(2)
    for h in hs:
        hid = h.get(".id") or h.get("id") or h.get("name")
        api.get_resource("/ip/hotspot").call("set", {"numbers": hid, "disabled": "no"})
    return f"[✓] Hotspot restarted ({len(hs)} instance(s))"


def _apply_wifi_fixes(api):
    """Apply all recommended WiFi/hotspot fixes for DHCP + connection issues."""
    out = []

    # Bridge: disable RSTP, disable fast-forward
    try:
        bridges = api.get_resource("/interface/bridge").get()
        for b in bridges:
            bid = b.get(".id") or b.get("id") or b.get("name")
            api.get_resource("/interface/bridge").call("set", {
                "numbers": bid, "protocol-mode": "none", "fast-forward": "no"
            })
        out.append(f"[✓] Bridge: protocol-mode=none, fast-forward=no ({len(bridges)} bridge(s))")
    except Exception as e:
        out.append(f"[!] Bridge fix error: {e}")

    # DHCP: addresses-per-mac=0, lease-time=30m
    try:
        servers = api.get_resource("/ip/dhcp-server").get()
        for s in servers:
            sid = s.get(".id") or s.get("id") or s.get("name")
            api.get_resource("/ip/dhcp-server").call("set", {
                "numbers": sid, "lease-time": "30m", "addresses-per-mac": "0"
            })
        out.append(f"[✓] DHCP: addresses-per-mac=0, lease-time=30m ({len(servers)} server(s))")
    except Exception as e:
        out.append(f"[!] DHCP fix error: {e}")

    # Hotspot: keepalive-timeout=2m
    try:
        hs = api.get_resource("/ip/hotspot").get()
        for h in hs:
            hid = h.get(".id") or h.get("id") or h.get("name")
            api.get_resource("/ip/hotspot").call("set", {
                "numbers": hid, "keepalive-timeout": "2m"
            })
        out.append(f"[✓] Hotspot: keepalive-timeout=2m ({len(hs)} instance(s))")
    except Exception as e:
        out.append(f"[!] Hotspot fix error: {e}")

    # WiFi: clear access-list reject rules
    try:
        r     = api.get_resource("/interface/wifi/access-list")
        rules = r.get()
        rejects = [x for x in rules if x.get("action") == "reject"]
        for x in rejects:
            xid = x.get(".id") or x.get("id")
            r.remove(id=xid)
        out.append(f"[✓] WiFi access-list: removed {len(rejects)} reject rule(s)")
    except Exception as e:
        out.append(f"[!] WiFi access-list error: {e}")

    # WiFi: set country Zimbabwe
    try:
        wifi_r = api.get_resource("/interface/wifi")
        ifaces = wifi_r.get()
        for i in ifaces:
            wifi_r.call("set", {"numbers": i.get("name"), "configuration.country": "Zimbabwe"})
        out.append(f"[✓] WiFi: country=Zimbabwe ({len(ifaces)} interface(s))")
    except Exception as e:
        out.append(f"[!] WiFi country error: {e}")

    # WiFi1: force ch6 20MHz
    try:
        wifi_r = api.get_resource("/interface/wifi")
        ifaces = wifi_r.get()
        for i in ifaces:
            name = i.get("name", "")
            if name in ("wifi1", "wlan1"):
                wifi_r.call("set", {
                    "numbers": name,
                    "channel.frequency": "2437",
                    "channel.width": "20mhz",
                })
                out.append(f"[✓] {name}: channel=2437 (ch6), width=20MHz")
    except Exception as e:
        out.append(f"[!] WiFi channel fix error: {e}")

    # Clear blocked IP bindings
    try:
        binds   = api.get_resource("/ip/hotspot/ip-binding")
        blocked = [b for b in binds.get() if b.get("type") == "blocked"]
        for b in blocked:
            bid = b.get(".id") or b.get("id")
            binds.remove(id=bid)
        out.append(f"[✓] Cleared {len(blocked)} blocked IP binding(s)")
    except Exception as e:
        out.append(f"[!] IP binding clear error: {e}")

    # Clear expired/abandoned DHCP leases
    try:
        leases_r = api.get_resource("/ip/dhcp-server/lease")
        leases   = leases_r.get()
        stale    = [l for l in leases if l.get("status") in ("expired", "abandoned")]
        for l in stale:
            lid = l.get(".id") or l.get("id")
            leases_r.remove(id=lid)
        out.append(f"[✓] Cleared {len(stale)} stale DHCP lease(s)")
    except Exception as e:
        out.append(f"[!] DHCP lease clear error: {e}")

    return "\n".join(out)


def _reboot(api):
    api.get_resource("/system").call("reboot")
    return "[✓] Reboot command sent. Router will restart in ~5 seconds."
