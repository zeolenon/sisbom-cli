# SISDO via HTTPX

O grupo `sisbom sisdo` obtém uma sessão por ticket SSO do SISBOM.
Cookies e CSRF ficam em memória. Não há publicação automática de OSs.

Comandos: `listar`, `criar`, `inserir`, `funcao`, `imprimir`, `remover`,
`acrescentar-vagas`, `reduzir-vagas` e `escala`. Consulte `--help` em cada comando.
Os comandos pontuais de escrita e `escala` usam prévia por padrão e exigem
`--executar` para enviar alterações. Prévia pode consultar os sistemas.
`imprimir` baixa PDF oficial para um destino novo, com permissão 0600.

`escala` exige modelo JSON, estado privado e um cliente de consultas externo
compatível (`--consulta-script`). Esse cliente não é distribuído neste pacote;
instalar o CLI sozinho não habilita a integração Escalador. Configure caminhos
e acesso separadamente no Linux. Não use wrappers que enviem mensagens.
O modelo contém `quartel_id`, `unidade_lancamento`, `campos` comuns do formulário
e `tipos_diaria` com regras explícitas de `tipo_os` e `funcao`.

OSs existentes precisam de vínculo explícito por ID interno e número impresso.
Só OSs digitadas do modelo/unidade podem ser reconciliadas. Tipos desconhecidos,
conflitos, divergências entre consultas ou mudança após a prévia interrompem.
`--esperar-hash` confere a origem; `--esperar-conferencia` confere o SISDO.
Retiradas exigem justificativa. A saída do último militar conserva uma vaga vazia.
Nunca apague o estado ou lock para forçar retomada sem conferir o processo.

As escritas são seguidas de leitura e não são repetidas automaticamente.
Falha após envio pode representar operação salva: releia antes de continuar.
A redução usa GET mutante e só atua sobre vagas relidas como vazias.
Remoção e ajustes de vagas foram validados com HTTP simulado; seus efeitos
em produção não foram exercitados nesta atualização.

Não versione estados, PDFs, respostas institucionais, nomes, matrículas ou
credenciais reais. As fixtures da suíte são sintéticas.

## Validação offline

```sh
python -m unittest discover -s tests -v
python -m sisbom_cli.cli sisdo --help
```

Maré usa a rota pública atual e exige o dia exato no fuso America/Fortaleza.
O catálogo BG usa `/api-bg`, normaliza `BG 182` para `182` e preserva aditamentos.

## Mapa de força e viaturas

`sisbom mapa-forca --lotacao CODIGO --date YYYY-MM-DD [--json]` já consulta
`MilitaresMapaForca` e `MapaGuarnicoesMilitar` na API GraphQL SISBOM.
Guarnições conservam `_viatura`, prefixo e militares com função/atividade/DO;
a consulta `FrotasViaturasMapaForca` já existe no cliente para cadastro de VTRs.
A data padrão usa Fortaleza. Trata-se do registro do sistema, sem comprovação
independente de presença. Não é calculado a partir da previsão Escalador.
Testes fictícios validam filtros de data/unidade e disposição por viatura/função.
A origem SISBOM foi confirmada pelo solicitante. O contrato GraphQL existente
é coberto offline; atualização/visibilidade real requer teste autenticado.
