"""core/wireguard.py — WireGuard peer management (runs on VPS)"""
import subprocess
import ipaddress
import os
import time
from config import Config


def _run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.returncode == 0, r.stdout.strip(), r.stderr.strip()


def list_peers():
    ok, out, _ = _run(f"wg show {Config.WG_INTERFACE} dump")
    if not ok or not out:
        return []
    peers = []
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 4:
            peers.append({
                "public_key":  parts[0],
                "endpoint":    parts[2],
                "allowed_ips": parts[3],
                "handshake":   parts[4] if len(parts) > 4 else "0",
            })
    return peers


def used_ips():
    ips = set()
    for p in list_peers():
        for cidr in p["allowed_ips"].split(","):
            try:
                ips.add(str(ipaddress.ip_interface(cidr.strip()).ip))
            except Exception:
                pass
    return ips


def next_free_ip():
    net   = ipaddress.ip_network(Config.WG_SUBNET, strict=False)
    taken = used_ips()
    taken.add(Config.VPS_WG_IP)
    for host in net.hosts():
        ip = str(host)
        if ip not in taken:
            return ip
    return None


def add_peer(public_key, allowed_ip, extra_routes=""):
    allowed = f"{allowed_ip}/32"
    if extra_routes:
        allowed += "," + extra_routes.strip().strip(",")
    ok, _, err = _run(f"wg set {Config.WG_INTERFACE} peer {public_key} allowed-ips {allowed}")
    if not ok:
        return False, f"wg set failed: {err}"
    _persist_peer(public_key, allowed)
    return True, f"Peer registered: {allowed_ip}"


def remove_peer(public_key):
    ok, _, err = _run(f"wg set {Config.WG_INTERFACE} peer {public_key} remove")
    if not ok:
        return False, f"Remove failed: {err}"
    _remove_peer_from_conf(public_key)
    return True, "Peer removed"


def peer_online(public_key, max_age_sec=180):
    try:
        ok, out, _ = _run(f"wg show {Config.WG_INTERFACE} latest-handshakes")
        if not ok:
            return False
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == public_key:
                return (int(time.time()) - int(parts[1])) < max_age_sec
    except Exception:
        pass
    return False


def _persist_peer(public_key, allowed_ips):
    if not os.path.exists(Config.WG_CONF):
        return
    with open(Config.WG_CONF) as f:
        content = f.read()
    if public_key in content:
        return
    with open(Config.WG_CONF, "a") as f:
        f.write(f"\n[Peer]\nPublicKey = {public_key}\nAllowedIPs = {allowed_ips}\n")


def _remove_peer_from_conf(public_key):
    if not os.path.exists(Config.WG_CONF):
        return
    with open(Config.WG_CONF) as f:
        lines = f.readlines()
    out, skip = [], False
    for line in lines:
        if line.strip() == "[Peer]":
            out.append(line)
            skip = False
            continue
        if skip:
            if line.strip().startswith("["):
                skip = False
                out.append(line)
            continue
        if f"PublicKey = {public_key}" in line:
            out.pop()
            skip = True
            continue
        out.append(line)
    with open(Config.WG_CONF, "w") as f:
        f.writelines(out)
