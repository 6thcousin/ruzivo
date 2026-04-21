"""
wg_manager.py — WireGuard peer management (runs on the VPS itself)
Called during router onboarding to register a new WireGuard peer.
"""

import subprocess
import ipaddress
import os

WG_INTERFACE = os.environ.get("WG_INTERFACE", "wg0")
WG_CONF      = os.environ.get("WG_CONF", f"/etc/wireguard/{WG_INTERFACE}.conf")
VPS_WG_IP    = os.environ.get("VPS_WG_IP", "10.0.0.1")
WG_SUBNET    = os.environ.get("WG_SUBNET", "10.0.0.0/24")


def _run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0, result.stdout.strip(), result.stderr.strip()


def list_peers():
    """Return list of (public_key, allowed_ips) tuples from `wg show`."""
    ok, out, _ = _run(f"wg show {WG_INTERFACE} dump")
    if not ok:
        return []
    peers = []
    for line in out.splitlines()[1:]:   # skip server line
        parts = line.split("\t")
        if len(parts) >= 4:
            peers.append({
                "public_key":   parts[0],
                "allowed_ips":  parts[3],
                "endpoint":     parts[2],
                "handshake":    parts[4] if len(parts) > 4 else "0",
            })
    return peers


def used_ips():
    """Return set of IPs already in use in WG allowed-ips."""
    ips = set()
    for p in list_peers():
        for cidr in p["allowed_ips"].split(","):
            try:
                ips.add(str(ipaddress.ip_interface(cidr.strip()).ip))
            except Exception:
                pass
    return ips


def next_free_ip():
    """Find the next available IP in WG_SUBNET (skipping VPS IP and used ones)."""
    net    = ipaddress.ip_network(WG_SUBNET, strict=False)
    taken  = used_ips()
    taken.add(VPS_WG_IP)
    for host in net.hosts():
        ip = str(host)
        if ip not in taken:
            return ip
    return None


def add_peer(public_key, allowed_ip, extra_routes=""):
    """
    Register a new WireGuard peer on the VPS.
    allowed_ip  — e.g. "10.0.0.8"  (the /32 is added automatically)
    extra_routes — comma-separated CIDRs, e.g. "192.168.88.0/24"
    Returns (success, message)
    """
    allowed = f"{allowed_ip}/32"
    if extra_routes:
        allowed += "," + extra_routes.strip().strip(",")

    # Add peer live (takes effect immediately)
    ok, out, err = _run(
        f"wg set {WG_INTERFACE} peer {public_key} allowed-ips {allowed}"
    )
    if not ok:
        return False, f"wg set failed: {err}"

    # Persist to conf file so it survives reboot
    _persist_peer(public_key, allowed)

    return True, f"Peer registered: {allowed_ip} ({allowed})"


def remove_peer(public_key):
    """Remove a WireGuard peer."""
    ok, _, err = _run(f"wg set {WG_INTERFACE} peer {public_key} remove")
    if not ok:
        return False, f"Remove failed: {err}"
    _remove_peer_from_conf(public_key)
    return True, "Peer removed"


def peer_online(public_key, max_age_sec=180):
    """Return True if peer had a handshake within max_age_sec seconds."""
    try:
        ok, out, _ = _run(f"wg show {WG_INTERFACE} latest-handshakes")
        if not ok:
            return False
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == public_key:
                import time
                age = int(time.time()) - int(parts[1])
                return age < max_age_sec
    except Exception:
        pass
    return False


def _persist_peer(public_key, allowed_ips):
    """Append [Peer] block to wg conf if not already there."""
    if not os.path.exists(WG_CONF):
        return
    with open(WG_CONF, "r") as f:
        content = f.read()
    if public_key in content:
        return   # already persisted
    block = f"\n[Peer]\nPublicKey = {public_key}\nAllowedIPs = {allowed_ips}\n"
    with open(WG_CONF, "a") as f:
        f.write(block)


def _remove_peer_from_conf(public_key):
    """Remove a [Peer] block from wg conf by public key."""
    if not os.path.exists(WG_CONF):
        return
    with open(WG_CONF, "r") as f:
        lines = f.readlines()

    out_lines = []
    skip = False
    for line in lines:
        if line.strip() == "[Peer]":
            # peek ahead to see if this block has our key
            skip = False
            out_lines.append(line)
            continue
        if skip:
            if line.strip().startswith("["):
                skip = False
                out_lines.append(line)
            continue
        if f"PublicKey = {public_key}" in line:
            # Remove the [Peer] header we just added
            out_lines.pop()
            skip = True
            continue
        out_lines.append(line)

    with open(WG_CONF, "w") as f:
        f.writelines(out_lines)
