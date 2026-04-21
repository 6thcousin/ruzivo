"""
WireGuard peer management service.

Manages VPS-side WireGuard peers for client MikroTik routers.
Each client gets a unique tunnel IP in the configured subnet (default 10.0.0.0/24).
The server holds IP .1; clients are assigned from .2 upward.

Environment variables (all optional, have defaults):
    WG_INTERFACE      WireGuard interface name        (default: wg0)
    WG_SUBNET         Tunnel subnet in CIDR notation  (default: 10.0.0.0/24)
    WG_SERVER_IP      VPS public IP or hostname       (required for client configs)
    WG_SERVER_PORT    WireGuard listen port           (default: 51820)
    WG_SERVER_PUBKEY  Server's WireGuard public key   (required for client configs)
    WG_PEERS_FILE     Path to peer metadata JSON      (default: /etc/wireguard/ruzivo_peers.json)
"""

import ipaddress
import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

WG_INTERFACE    = os.getenv("WG_INTERFACE",    "wg0")
WG_SUBNET       = os.getenv("WG_SUBNET",       "10.0.0.0/24")
WG_SERVER_IP    = os.getenv("WG_SERVER_IP",    "")
WG_SERVER_PORT  = int(os.getenv("WG_SERVER_PORT", "51820"))
WG_SERVER_PUBKEY = os.getenv("WG_SERVER_PUBKEY", "")
WG_PEERS_FILE   = Path(os.getenv("WG_PEERS_FILE", "/etc/wireguard/ruzivo_peers.json"))


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str], stdin: str | None = None) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, input=stdin, check=True
    )
    return result.stdout.strip()


def _load_peers() -> dict:
    if not WG_PEERS_FILE.exists():
        return {}
    try:
        return json.loads(WG_PEERS_FILE.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load peers file %s: %s", WG_PEERS_FILE, exc)
        return {}


def _save_peers(peers: dict) -> None:
    WG_PEERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WG_PEERS_FILE.write_text(json.dumps(peers, indent=2))


def _next_ip() -> str:
    network  = ipaddress.ip_network(WG_SUBNET, strict=False)
    hosts    = list(network.hosts())
    used_ips = {p["tunnel_ip"] for p in _load_peers().values()}
    # hosts[0] (.1) is reserved for the server
    for host in hosts[1:]:
        ip = str(host)
        if ip not in used_ips:
            return ip
    raise RuntimeError(f"No available IPs left in WireGuard subnet {WG_SUBNET}")


def _persist_wg_config() -> None:
    """Save live WireGuard state back to the config file (wg-quick setups)."""
    try:
        _run(["wg-quick", "save", WG_INTERFACE])
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        # Non-fatal: peer is live but won't survive a reboot via wg-quick.
        # Operators using systemd-networkd/wg-quick may need to persist manually.
        logger.warning("wg-quick save failed (peer is live but not persisted): %s", exc)


# ── public API ────────────────────────────────────────────────────────────────

def generate_keypair() -> dict[str, str]:
    """Generate a WireGuard private key, public key, and preshared key."""
    private_key  = _run(["wg", "genkey"])
    public_key   = _run(["wg", "pubkey"], stdin=private_key)
    preshared_key = _run(["wg", "genpsk"])
    return {
        "private_key":   private_key,
        "public_key":    public_key,
        "preshared_key": preshared_key,
    }


def register_peer(
    public_key:    str,
    client_name:   str,
    preshared_key: str | None = None,
) -> dict:
    """
    Register a WireGuard peer on the VPS.

    If the public key is already registered the existing record is returned
    unchanged (idempotent).

    Returns the peer record including the assigned tunnel IP and server info.
    """
    peers = _load_peers()
    if public_key in peers:
        logger.info("Peer %s already registered, returning existing record", public_key[:16])
        return peers[public_key]

    tunnel_ip   = _next_ip()
    allowed_ips = f"{tunnel_ip}/32"

    # Build wg-set command
    cmd = ["wg", "set", WG_INTERFACE, "peer", public_key, "allowed-ips", allowed_ips]
    if preshared_key:
        cmd += ["preshared-key", "/dev/stdin"]
    _run(cmd, stdin=preshared_key)

    _persist_wg_config()

    peer = {
        "public_key":      public_key,
        "tunnel_ip":       tunnel_ip,
        "client_name":     client_name,
        "server_pubkey":   WG_SERVER_PUBKEY,
        "server_endpoint": f"{WG_SERVER_IP}:{WG_SERVER_PORT}",
    }
    if preshared_key:
        peer["preshared_key"] = preshared_key

    peers[public_key] = peer
    _save_peers(peers)
    logger.info("Registered peer '%s' → %s", client_name, tunnel_ip)
    return peer


def provision_peer(client_name: str) -> dict:
    """
    Auto-provision a new peer: generate a keypair, register it, and return
    the full config needed to configure the MikroTik router.
    """
    keys = generate_keypair()
    peer = register_peer(
        public_key=keys["public_key"],
        client_name=client_name,
        preshared_key=keys["preshared_key"],
    )
    peer["private_key"]    = keys["private_key"]
    peer["mikrotik_config"] = build_mikrotik_config(
        tunnel_ip=peer["tunnel_ip"],
        private_key=keys["private_key"],
        server_pubkey=peer["server_pubkey"],
        server_endpoint=peer["server_endpoint"],
        preshared_key=keys["preshared_key"],
    )
    return peer


def remove_peer(public_key: str) -> bool:
    """
    Remove a peer from the live WireGuard interface and from persistent storage.
    Returns True if the peer existed and was removed, False if not found.
    """
    peers = _load_peers()
    if public_key not in peers:
        return False

    _run(["wg", "set", WG_INTERFACE, "peer", public_key, "remove"])
    _persist_wg_config()

    client_name = peers[public_key].get("client_name", "unknown")
    del peers[public_key]
    _save_peers(peers)
    logger.info("Removed peer '%s'", client_name)
    return True


def list_peers() -> list[dict]:
    """Return all registered peers (without private keys)."""
    return [
        {k: v for k, v in p.items() if k != "private_key"}
        for p in _load_peers().values()
    ]


def get_peer(public_key: str) -> dict | None:
    return _load_peers().get(public_key)


def build_mikrotik_config(
    tunnel_ip:       str,
    private_key:     str,
    server_pubkey:   str,
    server_endpoint: str,
    preshared_key:   str | None = None,
) -> str:
    """Return a standard WireGuard config block ready to apply to a MikroTik router."""
    lines = [
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {tunnel_ip}/32",
        "",
        "[Peer]",
        f"PublicKey = {server_pubkey}",
        f"Endpoint = {server_endpoint}",
        "AllowedIPs = 0.0.0.0/0",
        "PersistentKeepalive = 25",
    ]
    if preshared_key:
        lines.insert(-2, f"PresharedKey = {preshared_key}")
    return "\n".join(lines) + "\n"
