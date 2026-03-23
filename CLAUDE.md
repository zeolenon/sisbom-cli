# CLAUDE.md — sisbom-cli Agent Instructions

You are an AI agent working with `sisbom-cli`, a Python CLI for the SISBOM system (Corpo de Bombeiros Militar do RN — CBMRN).

## What This Is

Pure HTTP client for SISBOM's GraphQL APIs. No browser, no Playwright. Fast (~1-2s per operation).

## Architecture

- **Stack:** Python 3.12+ / httpx / click / rich
- **Entry point:** `sisbom` CLI (installed via `pip install -e .`)
- **Client:** `sisbom_cli/client.py` — all GraphQL + HTTP logic
- **Auth:** `sisbom_cli/auth.py` — JWT token management (Bitwarden or env vars)
- **Config:** `sisbom_cli/config.py` — API endpoints, token path, defaults

## Setup

### Authentication (choose one)

**Option A — Bitwarden (recommended):**
```bash
export SISBOM_BW_ITEM="SEI SISBOM RN CBMRN"   # vault item name
export BW_SESSION_PATH="$HOME/.bw_session"      # session token file
```
The vault item must have `login.username` = CPF and `login.password` = senha.

**Option B — Environment variables:**
```bash
export SISBOM_CPF="12345678901"
# Password will be prompted on first login
```

**Token persistence:** JWT saved to `~/.config/sisbom-cli/token` (chmod 600). Auto-refreshes on expiry.

## Common Operations

```bash
sisbom login                       # Authenticate and save token
sisbom me                          # Current user info

# Efetivo (personnel)
sisbom efetivo                     # All personnel
sisbom efetivo --lotacao 3GBMA     # Filter by unit
sisbom militar 12345678901         # By CPF
sisbom militar 2415380             # By matrícula
sisbom aniversariantes 03          # March birthdays
sisbom lotacoes                    # All units/locations

# Boletins Gerais (official bulletins)
sisbom bgs --year 2026             # List bulletins for 2026
sisbom bgs                         # List recent (default 20)
sisbom bg-download 040 --year 2026 --dest /path/to/dir

# E-Funcional (digital military ID)
sisbom efuncional                  # Current user's ID card (PDF)
sisbom efuncional --matricula X    # Another soldier's ID card
sisbom efuncional --json           # JSON output

# Férias (vacations)
sisbom ferias                      # Current user's vacation schedule
sisbom ferias --lotacao 3GBMA      # Unit vacation schedule
sisbom ferias-reaprazar --nome "Fulano" --periodos "01/07/2026-15/07/2026" --justificativa "Necessidade do serviço"

# Marés (tides — yes, it's in SISBOM)
sisbom mares                       # Today's tides
sisbom mares --date 2026-03-15     # Specific date

# Mapa de Força (force map — personnel by unit)
sisbom mapa-forca                  # Current force map
sisbom mapa-forca --lotacao 1CAT   # Specific unit
sisbom mapa-forca-export --format csv  # Export to CSV

# Raw GraphQL
sisbom query "{ me { _id str_cpf } }"
sisbom introspect MilitarEfetivo   # Schema introspection
```

## GraphQL APIs

| API | Endpoint | Purpose |
|-----|----------|---------|
| SISBOM | `api_sisbom` | Personnel, vacations, vehicles, tides |
| BG | `api_bg` | Bulletins (list, search, download) |
| Storage | `storage.cbm.rn.gov.br` | PDF downloads (no auth required) |

### Key Queries

```
Efetivo:  militares, militar, MilitarEfetivo, dt_nascimento
Diárias:  MilitarDiarias, MilitarDiariasBy, MilitarDiariaById
Férias:   FeriasMilitar, FeriasLotacao, FeriasTurmas, FeriasTurmasDetalhe
Permutas: MilitarPermutas, MilitarPermutasBy
E-Func:   FuncionalValida, FuncionalAtual, MilitarFuncionals, LogPrint (mutation)
Escalas:  MapaGuarnicoes, MapaIndividuals, DiasServicosMilitar
Frotas:   FrotasViaturas, FrotasAbastecimentos, FrotasOdometros
BGs:      Docs(year, bg_num), DocById
Lotações: Lotacoes, lotacoes
```

## File Structure

```
sisbom_cli/
├── cli.py      # Click CLI commands
├── client.py   # GraphQL + HTTP client (SISBOMClient)
├── auth.py     # JWT auth (Bitwarden + env var + cache)
└── config.py   # API URLs, token path, defaults
```

## Critical Rules

1. **Never expose tokens or credentials** in output or logs
2. **CPF is PII** — never hardcode in scripts or commit to repos
3. **Token auto-refreshes** — don't manually manage JWT lifecycle
4. **GraphQL introspection** is your friend — use `sisbom introspect <Type>` to discover fields

## Integration with sisbom-bg skill

The `sisbom-bg` skill uses this CLI to check for new bulletins and download PDFs:

```bash
sisbom bgs --year 2026 --json   # Check for new BGs
sisbom bg-download 040 --year 2026 --dest /path/to/bulletins
```

## Gotchas

1. **Auth token caching:** Token is saved to `~/.config/sisbom-cli/token`. If login fails after password change, delete this file.
2. **Lotação codes:** Use `sisbom lotacoes` to see valid codes. They're internal abbreviations (e.g., `3GBMA` for 3º GBM Apodi).
3. **GraphQL variables:** When using `sisbom query`, escape `$` in the shell: `\$year`.
4. **E-Funcional PDF:** The hash from `LogPrint` mutation is temporary (~5min). Download immediately.
5. **Férias reaprazamento:** The mutation replaces ALL periods for the exercise year. Always fetch current periods first.
