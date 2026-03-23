"""SISBOM configuration."""

from __future__ import annotations

import os
from pathlib import Path

# API endpoints
API_URL = "https://us-central1-cfap-app.cloudfunctions.net/api_sisbom"
API_BG = "https://us-central1-cfap-app.cloudfunctions.net/api_bg"
STORAGE_URL = "https://storage.cbm.rn.gov.br"
WP_URL = "https://api.sisbom.cbm.rn.gov.br"

# Token persistence
TOKEN_PATH = Path(os.environ.get("SISBOM_TOKEN_PATH", Path.home() / ".config" / "sisbom-cli" / "token"))

# Bitwarden
BW_ITEM_NAME = os.environ.get("SISBOM_BW_ITEM", "SEI SISBOM RN CBMRN")
BW_SESSION_PATH = Path(os.environ.get("BW_SESSION_PATH", Path.home() / ".bw_session"))

# CPF — must be set via SISBOM_CPF env var or Bitwarden vault custom field
DEFAULT_CPF = os.environ.get("SISBOM_CPF", "")
