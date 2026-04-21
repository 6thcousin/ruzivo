from pydantic import BaseModel
from typing import Optional


class RegisterPeerRequest(BaseModel):
    """Register an existing WireGuard public key as a new client peer."""
    public_key:    str
    client_name:   str
    preshared_key: Optional[str] = None


class ProvisionPeerRequest(BaseModel):
    """Auto-generate a keypair and register a new peer in one step."""
    client_name: str


class PeerInfo(BaseModel):
    public_key:      str
    tunnel_ip:       str
    client_name:     str
    server_pubkey:   str
    server_endpoint: str
    preshared_key:   Optional[str] = None


class ProvisionPeerResponse(PeerInfo):
    """Extended response for auto-provisioned peers — includes private key and MikroTik config."""
    private_key:     str
    mikrotik_config: str


class GenerateKeypairResponse(BaseModel):
    private_key:   str
    public_key:    str
    preshared_key: str
