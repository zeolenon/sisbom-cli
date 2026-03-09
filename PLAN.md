# SISBOM CLI — Plano de Implementação

## Descobertas (08/03/2026)

### Arquitetura
- **Frontend:** Angular SPA em `sisbom.cbm.rn.gov.br`
- **API:** GraphQL via `https://us-central1-cfap-app.cloudfunctions.net/api_sisbom`
- **Auth:** JWT Bearer token via mutation `seiLogin(str_cpf, password)`
- **Storage API:** `https://storage.cbm.rn.gov.br`
- **BG API:** `https://us-central1-cfap-app.cloudfunctions.net/api_bg`
- **WordPress API:** `https://api.sisbom.cbm.rn.gov.br`

### Autenticação
1. `seiLogin(str_cpf, password)` → retorna `{ forca_id, token }`
2. Token é JWT, usado como `Authorization: Bearer <token>`
3. Credenciais: CPF (sem formatação) + senha (mesma do SEI)

### Queries Disponíveis (principais para nosso uso)

#### Pessoal/Efetivo
- `me` — dados do usuário logado
- `militares(active, forca_id, lotacao)` — listar militares
- `militar(_id, str_matricula, str_cpf)` — detalhes de um militar
- `MilitarEfetivo` — efetivo completo
- `MilitarElevacaoNivel` — elevação de nível
- `dados_funcional` — dados funcionais
- `dt_nascimento(ano, mes, dia)` — aniversariantes

#### Diárias
- `MilitarDiarias` — listar diárias
- `MilitarDiariasBy` — filtrar diárias
- `MilitarDiariaById` — detalhe de diária
- `StartMilitarDiaria` (mutation) — iniciar diária
- `CreateMilitarDiaria` (mutation) — criar diária

#### Escalas/Guarnições
- `MapaGuarnicoes` — mapa de guarnições
- `MapaGuarnicaoBy` — filtrar
- `ListaGuarnicoes` — lista
- `DiasServicosMilitar` — dias de serviço
- `MapaIndividuals` — mapa individual

#### Férias
- `FeriasMilitar` — férias de militar
- `FeriasLotacao` — férias por lotação
- `FeriasTurmas` — turmas de férias

#### Permutas
- `MilitarPermutas` — listar permutas
- `MilitarPermutasBy` — filtrar

#### Lotações
- `Lotacoes` — listar lotações
- `lotacoes` (lookup) — referência

#### Frotas/Viaturas
- `FrotasViaturas` — listar viaturas
- `FrotasViaturasBy` — filtrar
- `FrotasAbastecimentos` — abastecimentos
- `FrotasOdometros` — odômetros
- `FrotasRegistros` — registros gerais

#### Ocorrências
- `Ocorrencias` — listar ocorrências
- `OcorrenciaBy` — filtrar

#### Cursos
- `Cursos` — listar cursos
- `CursosMilitar` — cursos de militar

#### Saúde
- `SaudeAgendamentos` — agendamentos
- `SaudePacientes` — pacientes

#### Licenças
- `Licencas` — listar licenças
- `MilitarLicencas` — licenças de militar

#### TAF
- `TafsMilitar` — TAFs de militar
- `TafAgendamentos` — agendamentos de TAF

### Mutations Úteis
- `CreateMilitarDiaria` / `UpdateMilitarDiaria` — gerenciar diárias
- `CreateMapaGuarnicao` — criar guarnição
- `CreateMilitarPermuta` — criar permuta
- `CreateOcorrencia` — registrar ocorrência

## Prioridades de Implementação

### Fase 1 — Core (essencial)
1. **Auth** — login, token management, auto-refresh
2. **Efetivo** — listar militares, consultar por matrícula/CPF
3. **Diárias** — listar, criar, consultar
4. **BGs** — download via API (substituir Playwright)

### Fase 2 — Gestão
5. **Escalas/Guarnições** — consultar mapas
6. **Férias** — consultar por lotação
7. **Permutas** — listar e consultar
8. **Frotas** — viaturas, abastecimentos

### Fase 3 — Relatórios
9. **Ocorrências** — listar e filtrar
10. **Licenças** — consultar
11. **Cursos** — listar por militar
12. **Aniversariantes** — dt_nascimento

## Stack
- Python 3 + httpx + click + rich
- JWT token persistence (arquivo local)
- Bitwarden para credenciais
- Mesmo padrão do sei-cli
