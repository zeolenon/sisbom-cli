# sisbom-cli

CLI Python para interagir com o **SISBOM (CBMRN)** via GraphQL API.

Sem browser. Sem Playwright. Puro `httpx`.

> **Filosofia:** CLI first. Browser só como último recurso (fallback).

## Instalação

```bash
git clone <este-repo>
cd sisbom-cli
pip install -e .
```

### Dependências

- **Python 3.12+**
- httpx (HTTP client)
- click (CLI framework)
- rich (tabelas formatadas no terminal)

## Autenticação

O CLI suporta três métodos de autenticação:

### 1. Bitwarden (recomendado)

O CLI busca credenciais no vault Bitwarden automaticamente.

```bash
# Item no vault deve ter:
# - login.username = seu CPF (11 dígitos)
# - login.password = sua senha do SISBOM
# Ou: campo customizado "cpf" no item

# Configurar via variáveis de ambiente:
export SISBOM_BW_ITEM="SEI SISBOM RN CBMRN"  # nome do item no vault
export BW_SESSION_PATH="$HOME/.bw_session"     # path do session token
export SISBOM_CPF="12345678901"                # CPF (se não estiver no vault)
```

### 2. Variáveis de ambiente

Se não usar Bitwarden, defina as variáveis diretamente:

```bash
export SISBOM_CPF="12345678901"
# A senha será solicitada interativamente no login
```

### Nota sobre o token

O token JWT é salvo em `~/.config/sisbom-cli/token` (chmod 600) e reaproveitado até expirar. O CLI faz auto-login transparente quando o token expira.

```bash
sisbom login          # Login e salva token
sisbom me             # Ver usuário logado
```

## Comandos

### Efetivo

```bash
sisbom efetivo                     # Todos os militares do CBMRN
sisbom efetivo --lotacao 3GBMA     # Filtrar por lotação
sisbom militar 12345678901         # Por CPF (11 dígitos)
sisbom militar 2415380             # Por matrícula
sisbom aniversariantes 03          # Aniversariantes de março
sisbom lotacoes                    # Lotações do CBMRN
```

### Boletins Gerais

```bash
sisbom bgs --year 2026             # Listar BGs do ano
sisbom bgs                         # Listar últimos 20
sisbom bgs --num 040               # BG específico
sisbom bg-download 040 --year 2026 # Baixar PDF (sem autenticação necessária)
sisbom bg-download 040 --dest ~/Downloads/bgs
```

### Diárias

```bash
sisbom diarias                     # Registros de diárias
sisbom diarias --json              # Saída JSON
```

### Viaturas

```bash
sisbom viaturas                    # Viaturas do CBMRN
sisbom viaturas --json
```

### Lotações

```bash
sisbom lotacoes                    # Todas as lotações
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
3. `GET doc_print?hash=<temp>` → PDF com QR code de validação

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

# Com variáveis JSON
sisbom query "query Docs(\$year: String){ Docs(year: \$year){ bg_num url } }" \
  --vars '{"year": "2026"}'
```

## Arquitetura

- **`sisbom_cli/client.py`** — Client GraphQL + download BG
- **`sisbom_cli/cli.py`** — Interface CLI (click + rich)
- **`sisbom_cli/auth.py`** — JWT token management (Bitwarden + cache)
- **`sisbom_cli/config.py`** — URLs e configuração

## APIs

| API | URL | Uso |
|-----|-----|-----|
| SISBOM GraphQL | `https://us-central1-cfap-app.cloudfunctions.net/api_sisbom` | Efetivo, diárias, viaturas, etc |
| BG GraphQL | `https://us-central1-cfap-app.cloudfunctions.net/api_bg` | Listar/buscar BGs |
| Storage | `https://storage.cbm.rn.gov.br/v0/boletins/{year}/{hash}.pdf` | Download PDFs (sem auth) |
| Reports | `api_sisbom/reports/doc_print` | E-Funcional PDF (hash via LogPrint) |

## Queries GraphQL Disponíveis (principais)

```
Efetivo:  militares, militar, MilitarEfetivo, dt_nascimento
Diárias:  MilitarDiarias, MilitarDiariasBy, MilitarDiariaById
Férias:   FeriasMilitar, FeriasLotacao, FeriasTurmas
Permutas: MilitarPermutas, MilitarPermutasBy
E-Func:   FuncionalValida, FuncionalAtual, MilitarFuncionals, LogPrint (mutation)
Escalas:  MapaGuarnicoes, MapaIndividuals, DiasServicosMilitar
Frotas:   FrotasViaturas, FrotasAbastecimentos, FrotasOdometros
BGs:      Docs(year, bg_num), DocById
Lotações: Lotacoes, lotacoes
```

## Integração com sisbom-bg skill

O `sisbom-cli` é usado pela skill `sisbom-bg` para verificar e baixar boletins:

```bash
# ~2s via httpx (vs ~30s via browser):
sisbom bgs --year 2026 --json
sisbom bg-download 040 --year 2026 --dest /path/to/bulletins
```
