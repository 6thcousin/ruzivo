import subprocess

from fastapi import APIRouter, HTTPException

from app.models.wireguard import (
    GenerateKeypairResponse,
    PeerInfo,
    ProvisionPeerRequest,
    ProvisionPeerResponse,
    RegisterPeerRequest,
)
from app.services import wireguard as wg

router = APIRouter()


# ── keypair generation ────────────────────────────────────────────────────────

@router.post(
    "/keypair",
    response_model=GenerateKeypairResponse,
    summary="Generate a WireGuard keypair",
    description="Returns a new private key, public key, and preshared key. "
                "Use this when you want to configure the MikroTik side manually.",
)
def generate_keypair():
    try:
        return wg.generate_keypair()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise HTTPException(status_code=500, detail=f"WireGuard error: {exc}")


# ── peer registration ─────────────────────────────────────────────────────────

@router.post(
    "/peers",
    response_model=PeerInfo,
    status_code=201,
    summary="Register an existing WireGuard public key",
    description="Use when the MikroTik already has a WireGuard keypair and you "
                "just need to register its public key on the VPS.",
)
def register_peer(body: RegisterPeerRequest):
    try:
        peer = wg.register_peer(
            public_key=body.public_key,
            client_name=body.client_name,
            preshared_key=body.preshared_key,
        )
        return PeerInfo(**peer)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"WireGuard error: {exc.stderr}")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post(
    "/provision",
    response_model=ProvisionPeerResponse,
    status_code=201,
    summary="Auto-provision a new WireGuard client",
    description="Generates a keypair, registers the peer on the VPS, and returns "
                "the complete WireGuard config to apply to the MikroTik router.",
)
def provision_peer(body: ProvisionPeerRequest):
    try:
        peer = wg.provision_peer(client_name=body.client_name)
        return ProvisionPeerResponse(**peer)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"WireGuard error: {exc.stderr}")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# ── peer management ───────────────────────────────────────────────────────────

@router.get(
    "/peers",
    response_model=list[PeerInfo],
    summary="List all registered WireGuard peers",
)
def list_peers():
    return wg.list_peers()


@router.get(
    "/peers/{public_key}",
    response_model=PeerInfo,
    summary="Get a specific WireGuard peer",
)
def get_peer(public_key: str):
    peer = wg.get_peer(public_key)
    if peer is None:
        raise HTTPException(status_code=404, detail="Peer not found")
    return PeerInfo(**peer)


@router.delete(
    "/peers/{public_key}",
    status_code=204,
    summary="Remove a WireGuard peer",
)
def remove_peer(public_key: str):
    try:
        found = wg.remove_peer(public_key)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"WireGuard error: {exc.stderr}")
    if not found:
        raise HTTPException(status_code=404, detail="Peer not found")
