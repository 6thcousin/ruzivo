#!/usr/bin/env python3
"""
wg_sniff_pubkey.py
──────────────────
Capture a WireGuard handshake initiation from an unregistered peer and
extract its static public key — without needing to touch the MikroTik.

How it works:
  WireGuard's Noise IKpsk2 handshake initiation contains the initiator's
  static public key encrypted under the responder's static public key.
  Since we have the VPS private key we can decrypt it from any captured packet.

Run as root on the VPS:
  pip3 install cryptography
  python3 wg_sniff_pubkey.py

Requires: Python 3.9+, cryptography>=2.6
"""

import argparse
import base64
import hashlib
import socket
import struct
import sys


# ── primitives ────────────────────────────────────────────────────────────────

def b2s(data: bytes, digest_size: int = 32) -> bytes:
    """BLAKE2s-{digest_size*8}."""
    return hashlib.blake2s(data, digest_size=digest_size).digest()


def hmac_b2s(key: bytes, data: bytes) -> bytes:
    """HMAC-BLAKE2s-256 (standard HMAC construction, BLAKE2s as hash)."""
    BLOCK = 64
    if len(key) > BLOCK:
        key = b2s(key)
    key = key.ljust(BLOCK, b'\x00')
    ipad = bytes(b ^ 0x36 for b in key)
    opad = bytes(b ^ 0x5C for b in key)
    inner = b2s(ipad + data)
    return b2s(opad + inner)


def kdf(ck: bytes, data: bytes, n: int):
    """WireGuard KDF (HKDF variant). Returns n output keys."""
    temp = hmac_b2s(ck, data)
    out1 = hmac_b2s(temp, b"\x01")
    if n == 1:
        return out1
    out2 = hmac_b2s(temp, out1 + b"\x02")
    if n == 2:
        return out1, out2
    out3 = hmac_b2s(temp, out2 + b"\x03")
    return out1, out2, out3


# ── handshake decryption ──────────────────────────────────────────────────────

# Noise IKpsk2 constants (from WireGuard spec)
_CONSTRUCTION = b"Noise_IKpsk2_25519_ChaChaPoly_BLAKE2s"
_IDENTIFIER   = b"WireGuard v1 zx2c4 Jason@zx2c4.com"


def extract_initiator_pubkey(payload: bytes, responder_privkey_b64: str) -> str:
    """
    Given a raw WireGuard handshake initiation UDP payload (≥148 bytes) and
    the responder's base64 private key, return the initiator's static public
    key as a base64 string.

    WireGuard handshake initiation layout:
      [0]      message type = 1
      [1:4]    reserved
      [4:8]    sender index
      [8:40]   initiator ephemeral public key   (plaintext, 32 B)
      [40:88]  encrypted initiator static key   (32 B payload + 16 B tag)
      [88:116] encrypted timestamp              (12 B + 16 B tag)
      [116:132] MAC1
      [132:148] MAC2
    """
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey, X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    if len(payload) < 148:
        raise ValueError(f"Payload too short: {len(payload)} B (need ≥148)")
    if payload[0] != 1:
        raise ValueError(f"Not a handshake initiation (type={payload[0]})")

    epub_i     = payload[8:40]   # initiator ephemeral pubkey (plaintext)
    enc_static = payload[40:88]  # encrypted initiator static pubkey

    # Load responder keys
    priv_raw = base64.b64decode(responder_privkey_b64)
    spriv_r  = X25519PrivateKey.from_private_bytes(priv_raw)
    spub_r   = spriv_r.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    # Noise IKpsk2 — responder side re-derivation
    Ci = b2s(_CONSTRUCTION)
    Hi = b2s(Ci + _IDENTIFIER)
    Hi = b2s(Hi + spub_r)

    Ci = kdf(Ci, epub_i, 1)      # KDF1(Ci, Epub_i)
    Hi = b2s(Hi + epub_i)

    # DH(Spriv_r, Epub_i) — responder can compute this from the packet
    dh_result   = spriv_r.exchange(X25519PublicKey.from_public_bytes(epub_i))
    _new_ci, k  = kdf(Ci, dh_result, 2)  # KDF2 → (new chaining key, enc key)

    # Decrypt initiator's static public key (nonce = 0)
    spub_i = ChaCha20Poly1305(k).decrypt(bytes(12), enc_static, Hi)
    return base64.b64encode(spub_i).decode()


# ── packet capture ────────────────────────────────────────────────────────────

def capture_wg_initiation(port: int, timeout: int) -> tuple[bytes, str]:
    """
    Sniff incoming UDP packets on <port> and return the first WireGuard
    handshake initiation payload along with the sender's IP.

    Uses AF_INET / SOCK_RAW / IPPROTO_UDP — requires root.
    Raw sockets receive a copy of every packet regardless of bound ports,
    so WireGuard consuming the packet does not prevent us from seeing it.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_UDP)
    sock.settimeout(timeout)

    print(f"[*] Listening for WireGuard handshake initiation on UDP/{port}")
    print(f"[*] MikroTik sends one every 25 s — waiting up to {timeout}s …")

    while True:
        try:
            raw, (src_ip, _) = sock.recvfrom(65535)
        except socket.timeout:
            raise TimeoutError("No WireGuard handshake received within the timeout.")

        ip_ihl   = (raw[0] & 0x0F) * 4
        dst_port = struct.unpack_from("!H", raw, ip_ihl + 2)[0]
        if dst_port != port:
            continue

        payload = raw[ip_ihl + 8:]
        if len(payload) >= 148 and payload[0] == 1:
            print(f"[✓] Handshake initiation from {src_ip}")
            return payload, src_ip


# ── wg0.conf reader ───────────────────────────────────────────────────────────

def read_privkey(conf: str = "/etc/wireguard/wg0.conf") -> str:
    with open(conf) as f:
        for line in f:
            if line.strip().lower().startswith("privatekey"):
                return line.split("=", 1)[1].strip()
    raise ValueError(f"PrivateKey not found in {conf}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Sniff a WireGuard handshake and extract the initiator's public key."
    )
    ap.add_argument("--privkey",   help="VPS WireGuard private key (base64). Reads wg0.conf if omitted.")
    ap.add_argument("--conf",      default="/etc/wireguard/wg0.conf")
    ap.add_argument("--port", "-p", type=int, default=13231)
    ap.add_argument("--timeout",   type=int, default=60)
    ap.add_argument("--client-id", default="sj_enterprises")
    ap.add_argument("--tunnel-ip", default="10.0.0.8")
    args = ap.parse_args()

    privkey = args.privkey or read_privkey(args.conf)

    try:
        payload, src_ip = capture_wg_initiation(args.port, args.timeout)
    except TimeoutError as exc:
        print(f"\n[-] {exc}")
        print("    Check: is the MikroTik online and trying to reach this VPS?")
        sys.exit(1)

    try:
        pubkey = extract_initiator_pubkey(payload, privkey)
    except Exception as exc:
        print(f"\n[-] Decryption failed: {exc}")
        sys.exit(1)

    W = 54
    print(f"\n╔{'═'*W}╗")
    print(f"║  {'Client':<14} {args.client_id:<{W-16}} ║")
    print(f"║  {'WAN IP':<14} {src_ip:<{W-16}} ║")
    print(f"║  {'Tunnel IP':<14} {args.tunnel_ip:<{W-16}} ║")
    print(f"║  {'Public Key':<14} {(pubkey[:36]+'…'):<{W-16}} ║")
    print(f"╚{'═'*W}╝")
    print(f"""
Run this to register the peer on the VPS:

  bash /opt/zivopay/autoconfig/scripts/add-wg-peer.sh \\
      {args.client_id} \\
      "{pubkey}" \\
      {args.tunnel_ip}
""")


if __name__ == "__main__":
    main()
