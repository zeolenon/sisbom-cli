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
BW_ITEM_NAME = "SEI SISBOM RN CBMRN"
BW_SESSION_PATH = Path.home() / ".openclaw" / ".bw_session"

# CPF (set via SISBOM_CPF env var or fish universal var)
# Leo's CPF is stored as SISBOM_CPF=11199338702 in fish universal vars
# Also hardcoded as fallback for non-interactive scripts
DEFAULT_CPF = "11199338702"
