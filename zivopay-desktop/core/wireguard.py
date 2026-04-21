"""core/wireguard.py — WireGuard peer management via VPS SSH"""
import ipaddress
from core.ssh import vps_run
from core.db  import get_db, get_setting


def used_ips():
    ips = {get_setting("vps_wg_ip", "10.0.0.1")}
    with get_db() as db:
        for row in db.execute("SELECT wg_ip FROM clients WHERE wg_ip IS NOT NULL"):
            ips.add(row["wg_ip"])
    return ips


def next_free_ip():
    net   = ipaddress.ip_network("10.0.0.0/24")
    taken = used_ips()
    for host in net.hosts():
        ip = str(host)
        if ip not in taken:
            return ip
    return None


def register_peer(public_key, wg_ip):
    """Register a new WireGuard peer on the VPS."""
    vps_host = get_setting("vps_host")
    vps_user = get_setting("vps_user")
    vps_pass = get_setting("vps_pass")
    wg_iface = get_setting("wg_interface", "wg0")
    wg_conf  = get_setting("wg_conf", "/etc/wireguard/wg0.conf")

    if not vps_host or not vps_pass:
        return False, "VPS credentials not configured. Go to Settings."

    allowed = f"{wg_ip}/32,192.168.88.0/24"

    # Add peer live
    ok, out = vps_run(
        f"wg set {wg_iface} peer {public_key} allowed-ips {allowed}",
        vps_host, vps_user, vps_pass,
    )
    if not ok:
        return False, out

    # Persist to wg0.conf
    vps_run(
        f"grep -q '{public_key}' {wg_conf} || "
        f"echo -e '\\n[Peer]\\nPublicKey = {public_key}\\nAllowedIPs = {allowed}' >> {wg_conf}",
        vps_host, vps_user, vps_pass,
    )

    return True, f"Peer registered: {wg_ip}"


def remove_peer(public_key):
    vps_host = get_setting("vps_host")
    vps_user = get_setting("vps_user")
    vps_pass = get_setting("vps_pass")
    wg_iface = get_setting("wg_interface", "wg0")

    ok, out = vps_run(
        f"wg set {wg_iface} peer {public_key} remove",
        vps_host, vps_user, vps_pass,
    )
    return ok, out


def list_peers():
    vps_host = get_setting("vps_host")
    vps_user = get_setting("vps_user")
    vps_pass = get_setting("vps_pass")
    wg_iface = get_setting("wg_interface", "wg0")

    ok, out = vps_run(f"wg show {wg_iface}", vps_host, vps_user, vps_pass)
    return ok, out
