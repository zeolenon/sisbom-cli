# Histórico de versões

## 1.1.0 — 2026-10-04

- Repositório Institucional browserless: catálogo, fila paginada, validação offline, cadastro de manual PDF pendente e reconciliação por ID/URL/hash/status com diário local e bloqueio após resposta incerta.
- SISDO voluntariado: consultas por competência/quartéis, perfil do próprio usuário e prévias preservando inscrições anteriores. Inclui inscrição própria aditiva explícita, com preservação das seleções, diário e confirmação por perfil após POST. Retirada/substituição e exportação definitiva permanecem desabilitadas.
- Guia completo de agentes e referência gerada das opções reais; documentação de consultas versus escritas, autenticação, datas BRT, paginação, JSON e limites legados.
- Login permite seleção explícita de endpoint oficial sem mudar configuração global; retorno não contém prévia de token.
- CI Python3.12/3.13, testes sintéticos, build wheel/sdist e instalação/smoke limpos. Preserva funcionalidades/correções1.0.0. Sem publicação PyPI ou dados operacionais.


## 1.0.0

Primeira release publicada no GitHub, reunindo as funcionalidades existentes
e as atualizações SISDO, BG, maré e mapa de força.

- SISDO via HTTPX e SSO: listagem de OSs, criação digitada, efetivo, funções,
  impressão PDF, remoção e ajustes de vagas, com prévia nos comandos de escrita.
- Reconciliação Escalador com regras explícitas, estado privado, vínculos de OS,
  hashes de origem/conferência e leitura após envio; sem publicação automática.
- Mapa de força SISBOM: militares, guarnições por viatura/função, visão mensal
  e exportação; data diária padrão em America/Fortaleza.
- BGs pela API pública atual; normaliza números regulares e preserva aditamentos.
- Maré pública com validação estrita do dia solicitado, horários e alturas.
- Bitwarden sem token de sessão nos argumentos do processo.
- Mantém consultas de efetivo, militares, lotações, diárias, viaturas,
  E-Funcional, GraphQL/introspecção e reaprazamento de férias.

Validação: 41 testes offline com dados sintéticos, construção/instalação de
wheel e verificação do entry point. Sem operações institucionais nesta revisão.
Remoção e ajustes SISDO foram verificados por HTTP simulado; contratos e
visibilidade atuais dependem de teste autenticado autorizado. Integração
Escalador exige cliente externo, modelo e estado privados não distribuídos.
