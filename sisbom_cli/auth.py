"""Authentication for SISBOM API."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .config import BW_ITEM_NAME, BW_SESSION_PATH, DEFAULT_CPF, TOKEN_PATH


def _get_bw_session() -> str:
    """Read Bitwarden session token."""
    if not BW_SESSION_PATH.exists():
        raise RuntimeError(
            f"Bitwarden session not found at {BW_SESSION_PATH}. "
            "Run bw_unlock_gateway.sh first."
        )
    return BW_SESSION_PATH.read_text().strip()


def get_credentials() -> tuple[str, str]:
    """Get CPF and password from Bitwarden vault.

    Returns:
        (cpf, password) tuple.
    """
    session = _get_bw_session()
    result = subprocess.check_output(
        ["bw", "get", "item", BW_ITEM_NAME, "--session", session],
        text=True,
        timeout=15,
    )
    item = json.loads(result)
    password = item["login"]["password"]

    # Try to get CPF: check custom fields, then env var, then username
    cpf = os.environ.get("SISBOM_CPF", "")

    if not cpf:
        # Check custom fields in vault
        for field in item.get("fields") or []:
            if "cpf" in (field.get("name") or "").lower():
                cpf = field["value"]
                break

    if not cpf:
        username = item["login"].get("username", "")
        # If username is all digits (possibly with dots/dashes), it's a CPF
        digits = "".join(c for c in username if c.isdigit())
        if len(digits) == 11:
            cpf = digits

    if not cpf:
        cpf = DEFAULT_CPF  # fallback para scripts não-interativos

    # Remove formatting from CPF
    cpf = "".join(c for c in cpf if c.isdigit())
    return cpf, password


def load_token() -> str | None:
    """Load saved JWT token if still valid."""
    if not TOKEN_PATH.exists():
        return None

    try:
        data = json.loads(TOKEN_PATH.read_text())
        token = data.get("token", "")
        expires = data.get("expires", 0)

        if time.time() < expires and token:
            return token
    except (json.JSONDecodeError, KeyError):
        pass

    return None


def save_token(token: str, expires_ms: int | None = None) -> None:
    """Save JWT token to disk."""
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    # JWT tokens from SISBOM have exp in the payload
    # Parse it to get expiry
    if expires_ms is None:
        import base64

        try:
            # Decode JWT payload (middle part)
            parts = token.split(".")
            if len(parts) == 3:
                payload = parts[1]
                # Add padding
                payload += "=" * (4 - len(payload) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(payload))
                exp = decoded.get("exp", 0)
                # SISBOM uses millisecond timestamps
                if exp > 1e12:
                    expires_ms = exp
                else:
                    expires_ms = int(exp * 1000)
        except Exception:
            # Default: 24h from now
            expires_ms = int((time.time() + 86400) * 1000)

    TOKEN_PATH.write_text(
        json.dumps({
            "token": token,
            "expires": expires_ms / 1000 if expires_ms > 1e12 else expires_ms,
            "saved_at": time.time(),
        })
    )
