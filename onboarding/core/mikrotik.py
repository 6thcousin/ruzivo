"""core/mikrotik.py — all RouterOS API logic"""
import json
import time
import routeros_api


# ── Connection ────────────────────────────────────────────────────────────────

def connect(host, port, username, password):
    pool = routeros_api.RouterOsApiPool(
        host, username=username, password=password,
        port=int(port), plaintext_login=True,
    )
    return pool.get_api(), pool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _id(item):
    """Get RouterOS item ID — handles both '.id' and 'id' key variants."""
    return item.get(".id") or item.get("id") or item.get("name")


# ── Public API ────────────────────────────────────────────────────────────────

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
        mem = f"{round((tm-fm)/tm*100)}% ({round((tm-fm)/1_048_576,1)}/{round(tm/1_048_576,1)} MB)"

        try:
            sessions = len(api.get_resource("/ip/hotspot/active").get())
        except Exception:
            sessions = "N/A"

        peers, channels = 0, []
        try:
            wifi = api.get_resource("/interface/wifi")
            for iface in wifi.get():
                mon = wifi.call("monitor", {"numbers": iface.get("name"), "once": ""})
                if mon:
                    peers += int(mon[0].get("registered-peers", 0))
                    channels.append(mon[0].get("channel", "?"))
        except Exception:
            pass

        pool.disconnect()
        return {
            "success":    True,
            "identity":   name,
            "cpu_load":   f"{res.get('cpu-load','?')}%",
            "memory":     mem,
            "uptime":     res.get("uptime", "?"),
            "version":    res.get("version", "?"),
            "sessions":   sessions,
            "wifi_peers": peers,
            "channels":   ", ".join(channels) or "N/A",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_raw(host, port, username, password, raw):
    """Run a raw RouterOS API path, e.g. '/ip/address print'"""
    try:
        api, pool = connect(host, port, username, password)
        parts  = raw.strip().split()
        path   = parts[0]
        action = parts[1] if len(parts) > 1 else "print"
        res    = api.get_resource(path)
        result = res.call(action) if action != "print" else res.get()
        pool.disconnect()
        return {"success": True, "output": json.dumps(result, indent=2, default=str)}
    except Exception as e:
        return {"success": False, "output": f"Error: {e}"}


# ── Command handlers ──────────────────────────────────────────────────────────

COMMANDS = {
    "system_info":     ("System Info",      "bi-cpu"),
    "hotspot_users":   ("Hotspot Sessions", "bi-people"),
    "wifi_clients":    ("WiFi Clients",     "bi-wifi"),
    "dhcp_leases":     ("DHCP Leases",      "bi-list-ul"),
    "ip_bindings":     ("IP Bindings",      "bi-shield"),
    "vouchers":        ("Vouchers",         "bi-ticket-perforated"),
    "wg_status":       ("WireGuard Status", "bi-shield-lock"),
    "bridge_status":   ("Bridge Status",    "bi-diagram-3"),
    "restart_hotspot": ("Restart Hotspot",  "bi-arrow-repeat"),
    "apply_wifi_fixes":("Apply WiFi Fixes", "bi-tools"),
    "reboot":          ("Reboot Router",    "bi-power"),
}


def run_command(host, port, username, password, cmd_key):
    handlers = {
        "system_info":      _cmd_system_info,
        "hotspot_users":    _cmd_hotspot_users,
        "wifi_clients":     _cmd_wifi_clients,
        "dhcp_leases":      _cmd_dhcp_leases,
        "ip_bindings":      _cmd_ip_bindings,
        "vouchers":         _cmd_vouchers,
        "wg_status":        _cmd_wg_status,
        "bridge_status":    _cmd_bridge_status,
        "restart_hotspot":  _cmd_restart_hotspot,
        "apply_wifi_fixes": _cmd_apply_wifi_fixes,
        "reboot":           _cmd_reboot,
    }
    if cmd_key not in handlers:
        return {"success": False, "output": f"Unknown command: {cmd_key}"}
    try:
        api, pool = connect(host, port, username, password)
        output = handlers[cmd_key](api)
        pool.disconnect()
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "output": f"Connection error: {e}"}


def _cmd_system_info(api):
    res  = api.get_resource("/system/resource").get()[0]
    name = api.get_resource("/system/identity").get()[0].get("name", "?")
    fm   = int(res.get("free-memory", 0))
    tm   = int(res.get("total-memory", 1))
    return "\n".join([
        f"Identity : {name}",
        f"Version  : {res.get('version','?')}",
        f"Board    : {res.get('board-name','?')}",
        f"CPU      : {res.get('cpu-load','?')}%",
        f"Memory   : {round((tm-fm)/tm*100)}% ({round((tm-fm)/1_048_576,1)}/{round(tm/1_048_576,1)} MB)",
        f"Uptime   : {res.get('uptime','?')}",
    ])


def _cmd_hotspot_users(api):
    active = api.get_resource("/ip/hotspot/active").get()
    if not active:
        return "No active sessions."
    lines = [f"Active: {len(active)}\n"]
    for u in active:
        lines.append(f"  {u.get('mac-address','?'):<18} {u.get('address','?'):<16} "
                     f"user={u.get('user','?')} uptime={u.get('uptime','?')}")
    return "\n".join(lines)


def _cmd_wifi_clients(api):
    r, lines, total = api.get_resource("/interface/wifi"), [], 0
    for iface in r.get():
        nm = iface.get("name", "?")
        try:
            mon  = r.call("monitor", {"numbers": nm, "once": ""})
            p    = int(mon[0].get("registered-peers", 0)) if mon else 0
            ch   = mon[0].get("channel", "?") if mon else "?"
            st   = mon[0].get("state", "?") if mon else "?"
            total += p
            lines.append(f"  {nm}: {p} clients  channel={ch}  state={st}")
        except Exception as e:
            lines.append(f"  {nm}: error — {e}")
    return f"Total WiFi Clients: {total}\n" + "\n".join(lines)


def _cmd_dhcp_leases(api):
    leases = api.get_resource("/ip/dhcp-server/lease").get()
    bound  = [l for l in leases if l.get("status") == "bound"]
    lines  = [f"Total: {len(leases)}   Bound: {len(bound)}\n"]
    for l in bound[:30]:
        lines.append(f"  {l.get('address','?'):<16} {l.get('mac-address','?'):<18} "
                     f"{l.get('host-name','?'):<24} exp={l.get('expires-after','?')}")
    return "\n".join(lines)


def _cmd_ip_bindings(api):
    binds = api.get_resource("/ip/hotspot/ip-binding").get()
    if not binds:
        return "No IP bindings."
    lines = [f"IP Bindings: {len(binds)}\n"]
    for b in binds:
        lines.append(f"  {b.get('mac-address','?'):<18} {b.get('address','?'):<16} "
                     f"type={b.get('type','?')}")
    return "\n".join(lines)


def _cmd_vouchers(api):
    users  = api.get_resource("/ip/hotspot/user").get()
    active = {a.get("user") for a in api.get_resource("/ip/hotspot/active").get()}
    lines  = [f"Users: {len(users)}   Active: {len(active)}\n"]
    for u in users[:40]:
        flag = "● ACTIVE" if u.get("name") in active else "  idle  "
        lines.append(f"  [{flag}] {u.get('name','?'):<20} profile={u.get('profile','?')}")
    return "\n".join(lines)


def _cmd_wg_status(api):
    try:
        ifaces = api.get_resource("/interface/wireguard").get()
        peers  = api.get_resource("/interface/wireguard/peers").get()
    except Exception as e:
        return f"WireGuard not available: {e}"
    lines = [f"Interfaces: {len(ifaces)}"]
    for i in ifaces:
        lines.append(f"  {i.get('name')} listen-port={i.get('listen-port')} disabled={i.get('disabled')}")
    lines.append(f"\nPeers: {len(peers)}")
    for p in peers:
        lines.append(f"  {p.get('public-key','?')[:28]}…  "
                     f"endpoint={p.get('endpoint-address','?')}:{p.get('endpoint-port','?')}"
                     f"  handshake={p.get('last-handshake','never')}")
    return "\n".join(lines)


def _cmd_bridge_status(api):
    bridges = api.get_resource("/interface/bridge").get()
    ports   = api.get_resource("/interface/bridge/port").get()
    lines   = [f"Bridges: {len(bridges)}"]
    for b in bridges:
        lines.append(f"  {b.get('name'):<16} protocol-mode={b.get('protocol-mode')}"
                     f"  fast-forward={b.get('fast-forward')}")
    lines.append(f"\nPorts: {len(ports)}")
    for p in ports:
        lines.append(f"  {p.get('interface'):<16} → {p.get('bridge'):<16} disabled={p.get('disabled')}")
    return "\n".join(lines)


def _cmd_restart_hotspot(api):
    hs = api.get_resource("/ip/hotspot").get()
    if not hs:
        return "No hotspot configured."
    for h in hs:
        api.get_resource("/ip/hotspot").call("set", {"numbers": _id(h), "disabled": "yes"})
    time.sleep(2)
    for h in hs:
        api.get_resource("/ip/hotspot").call("set", {"numbers": _id(h), "disabled": "no"})
    return f"[✓] Hotspot restarted ({len(hs)} instance(s))"


def _cmd_apply_wifi_fixes(api):
    out = []

    # Bridge: disable RSTP + fast-forward
    try:
        for b in api.get_resource("/interface/bridge").get():
            api.get_resource("/interface/bridge").call("set",
                {"numbers": _id(b), "protocol-mode": "none", "fast-forward": "no"})
        out.append("[✓] Bridge: protocol-mode=none, fast-forward=no")
    except Exception as e:
        out.append(f"[!] Bridge: {e}")

    # DHCP: addresses-per-mac=0, lease-time=30m
    try:
        for s in api.get_resource("/ip/dhcp-server").get():
            api.get_resource("/ip/dhcp-server").call("set",
                {"numbers": _id(s), "lease-time": "30m", "addresses-per-mac": "0"})
        out.append("[✓] DHCP: addresses-per-mac=0, lease-time=30m")
    except Exception as e:
        out.append(f"[!] DHCP: {e}")

    # Hotspot: keepalive-timeout=2m
    try:
        for h in api.get_resource("/ip/hotspot").get():
            api.get_resource("/ip/hotspot").call("set",
                {"numbers": _id(h), "keepalive-timeout": "2m"})
        out.append("[✓] Hotspot: keepalive-timeout=2m")
    except Exception as e:
        out.append(f"[!] Hotspot: {e}")

    # WiFi: set country Zimbabwe
    try:
        wifi = api.get_resource("/interface/wifi")
        ifaces = wifi.get()
        for i in ifaces:
            wifi.call("set", {"numbers": i.get("name"), "configuration.country": "Zimbabwe"})
        out.append(f"[✓] WiFi: country=Zimbabwe ({len(ifaces)} interface(s))")
    except Exception as e:
        out.append(f"[!] WiFi country: {e}")

    # WiFi: clear access-list reject rules
    try:
        r = api.get_resource("/interface/wifi/access-list")
        rejects = [x for x in r.get() if x.get("action") == "reject"]
        for x in rejects:
            r.remove(id=_id(x))
        out.append(f"[✓] Access-list: removed {len(rejects)} reject rule(s)")
    except Exception as e:
        out.append(f"[!] Access-list: {e}")

    # Clear blocked IP bindings
    try:
        binds = api.get_resource("/ip/hotspot/ip-binding")
        blocked = [b for b in binds.get() if b.get("type") == "blocked"]
        for b in blocked:
            binds.remove(id=_id(b))
        out.append(f"[✓] Cleared {len(blocked)} blocked IP binding(s)")
    except Exception as e:
        out.append(f"[!] IP bindings: {e}")

    # Clear stale DHCP leases
    try:
        leases = api.get_resource("/ip/dhcp-server/lease")
        stale  = [l for l in leases.get() if l.get("status") in ("expired", "abandoned")]
        for l in stale:
            leases.remove(id=_id(l))
        out.append(f"[✓] Cleared {len(stale)} stale DHCP lease(s)")
    except Exception as e:
        out.append(f"[!] DHCP leases: {e}")

    return "\n".join(out)


def _cmd_reboot(api):
    api.get_resource("/system").call("reboot")
    return "[✓] Reboot command sent."
