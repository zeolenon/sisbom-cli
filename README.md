# sisbom-cli

CLI Python para interagir com o **SISBOM (CBMRN)** via GraphQL API.

Sem browser. Sem Playwright. Puro `httpx`.

> **Filosofia:** CLI first. Browser só como último recurso (fallback).

## Instalação

```bash
cd ~/Projects/sisbom-cli
pip install -e .
```

## Autenticação

O CLI usa o vault Bitwarden automaticamente (item `SEI SISBOM RN CBMRN`).  
Precisa do campo customizado `cpf` no item, ou da env var `SISBOM_CPF=11199338702`.

Token JWT é salvo em `~/.config/sisbom-cli/token` e reaproveitado até expirar.

```bash
sisbom login          # Login e salva token
sisbom me             # Ver usuário logado
```

## Comandos

### Efetivo

```bash
sisbom efetivo                     # 1252 militares do CBMRN
sisbom efetivo --lotacao 3GBMA     # Filtrar por lotação (usa query militares)
sisbom militar 11199338702         # Por CPF (11 dígitos)
sisbom militar 2415380             # Por matrícula
sisbom aniversariantes 03          # Aniversariantes de março
sisbom lotacoes                    # 78 lotações do CBMRN
```

### Boletins Gerais

```bash
sisbom bgs --year 2026             # Listar BGs de 2026 (43 em março/2026)
sisbom bgs                         # Listar últimos 20 (5813 históricos)
sisbom bgs --num 040               # BG específico
sisbom bg-download 040 --year 2026 # Baixar PDF (sem autenticação necessária)
sisbom bg-download 040 --dest ~/Downloads/bgs
```

### Diárias

```bash
sisbom diarias                     # 1070+ registros de diárias
sisbom diarias --json              # Saída JSON
```

### Viaturas

```bash
sisbom viaturas                    # 340 viaturas do CBMRN
sisbom viaturas --json
```

### Lotações

```bash
sisbom lotacoes                    # 78 lotações
```

### E-Funcional

```bash
sisbom efuncional                              # Exporta e-funcional do último emitido
sisbom efuncional --matricula 2415380          # Por matrícula específica
sisbom efuncional --matricula 2415380 --dest ~/Downloads
sisbom efuncional --matricula 2415380 --list   # Listar todas as emissões
sisbom efuncional --json                       # Saída JSON
```

Fluxo interno:
1. `FuncionalValida(str_matricula)` → hash permanente da funcional
2. `LogPrint(type: "militar-funcional")` → hash temporário de impressão
3. `GET doc_print?hash=<temp>` → PDF com QR code de validação (~1.3MB)

### Marés

```bash
sisbom mare                                    # Areia Branca (tabuademares.com)
sisbom mare --local natal                      # Natal
sisbom mare-sisbom                             # SISBOM API (Natal/RN)
sisbom mare-sisbom --date 2026-03-08           # Data específica
```

### GraphQL Avançado

```bash
# Query raw
sisbom query "{ me { _id str_cpf } }"

# Introspect types
sisbom introspect MilitarEfetivo
sisbom introspect FrotasViatura
sisbom introspect Doc
sisbom introspect MilitarDiaria

# Com variáveis JSON
sisbom query "query Docs(\$year: String){ Docs(year: \$year){ bg_num url } }" \
  --vars '{"year": "2026"}'
```

## Arquitetura

- **`sisbom_cli/client.py`** — Client GraphQL + download BG
- **`sisbom_cli/cli.py`** — Interface CLI (click + rich)
- **`sisbom_cli/auth.py`** — JWT token management (Bitwarden + cache)
- **`sisbom_cli/config.py`** — URLs e configuração

## APIs Descobertas

| API | URL | Uso |
|-----|-----|-----|
| SISBOM GraphQL | `https://us-central1-cfap-app.cloudfunctions.net/api_sisbom` | Efetivo, diárias, viaturas, etc |
| BG GraphQL | `https://us-central1-cfap-app.cloudfunctions.net/api_bg` | Listar/buscar BGs |
| Storage | `https://storage.cbm.rn.gov.br/v0/boletins/{year}/{hash}.pdf` | Download PDFs (sem auth) |
| Reports | `https://us-central1-cfap-app.cloudfunctions.net/api_sisbom/reports/doc_print` | E-Funcional PDF (hash via LogPrint) |

## Queries GraphQL Disponíveis (principais)

```
Efetivo: militares, militar, MilitarEfetivo, dt_nascimento
Diárias: MilitarDiarias, MilitarDiariasBy, MilitarDiariaById
Férias:  FeriasMilitar, FeriasLotacao, FeriasTurmas
Permutas: MilitarPermutas, MilitarPermutasBy
E-Func:  FuncionalValida, FuncionalAtual, MilitarFuncionals, LogPrint (mutation)
Escalas: MapaGuarnicoes, MapaIndividuals, DiasServicosMilitar
Frotas:  FrotasViaturas, FrotasAbastecimentos, FrotasOdometros
BGs:     Docs(year, bg_num), DocById
Lotações: Lotacoes, lotacoes
```

## Integração com sisbom-bg skill

O `sisbom-cli` pode substituir o Playwright na skill `sisbom-bg`:

```bash
# Antes (Playwright, ~30s):
node commands/check-new.js

# Depois (httpx, ~2s):
sisbom bgs --year 2026 --json | python3 -c "..."
sisbom bg-download 040 --year 2026 --dest ~/Library/.../bgbm
```
