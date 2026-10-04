# Histórico de versões

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
