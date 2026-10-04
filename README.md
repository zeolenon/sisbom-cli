# SISBOM CLI

CLI Python3.12+ para SISBOM/CBMRN e SISDO, por HTTPX, sem navegador.

**[Guia completo para agentes: todas as funcionalidades, opções, exemplos e efeitos](docs/guia-agentes.md)**

Pessoal/frota, boletins regulares/especiais/aditamentos, maré Natal/BRT, mapa diário/mensal/exportação, E-Funcional, férias, GraphQL/introspecção, OSs SISDO, reconciliação Escalador, consultas/prévias de voluntariado e inventário/cadastro pendente RI.

Voluntariado permite **inscrição própria aditiva com --executar e conferência posterior**, sem retirar quartéis atuais. Não exporta lista definitiva. Escritas exigem autorização e conferência conforme guia. Integração Escalador requer cliente externo não distribuído. JSON/PDF institucionais devem permanecer privados.

Instale a wheel de [Releases](https://github.com/zeolenon/sisbom-cli/releases) em venv, ou para desenvolvimento:

```sh
python -m pip install -e .
sisbom --help
python -m unittest discover -s tests -v
```

Dependências httpx, Click e Rich. Autenticação pelo provedor configurado pelo operador/cache privado/SSO oficial, sem segredos em issues/logs. Veja [AGENTS.md](AGENTS.md), [SISDO](docs/sisdo-httpx.md), [voluntariado](docs/voluntariado-sisdo.md) e [changelog](CHANGELOG.md).
