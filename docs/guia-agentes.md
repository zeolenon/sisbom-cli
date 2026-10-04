# SISBOM CLI 1.1.0 — guia completo para agentes

Execução HTTPX sem navegador. Use `sisbom`, instalado pelo pacote, ou `python -m sisbom_cli.cli`. Leia AGENTS.md e `--help` antes de operar. As opções completas de todos os comandos estão no final deste guia.

## Instalação e autenticação segura

Python3.12+, httpx, Click e Rich. Instale a wheel GitHub em venv, ou `python -m pip install -e .` para desenvolvimento. Credenciais vêm do provedor Bitwarden configurado pelo operador (`SISBOM_BW_ITEM`, `BW_SESSION_PATH`, opcional `SISBOM_CPF`). O item contém usuário/CPF e senha. Apenas definir CPF não implementa prompt de senha: o provedor continua necessário. Não ler/imprimir/copiar sessões, senhas ou tokens.

Cache canônico: `~/.config/sisbom-cli/token` ou `SISBOM_TOKEN_PATH`, protegido0600. Login/renovação só com autorização; não apagar cache nem exportar cookies para contornar erro. Retorno login não contém prévia de token.

```sh
# Apenas quando autenticação/renovação foi autorizada:
sisbom login --api-url https://sisbom.cbm.rn.gov.br/api --json
sisbom me --json  # dados pessoais; conservar privadamente
```

`--api-url` seleciona entre endpoints oficiais, preservando o padrão legado e configuração global. Comandos legados gerais usam auto-login/retry de autenticação: não os execute em tarefas que proíbam renovação sem avaliar isso. RI e voluntariado falham se cache estiver ausente/rejeitado, sem novo login. SISDO geral pode autenticar pelo cliente legado; ticket SSO/cookies são temporários em memória. Ticket não é consulta sem efeito de autenticação.

## Efeitos, saídas e erros

Leitura não autoriza escrita nem divulgação. JSON/PDF podem conter nomes, matrículas, CPF e documentos; use diretório privado/0600 e não versione respostas reais. Não envie mensagens como consequência de consulta.

|Família|Efeito|
|---|---|
|Pessoal, frota, mapas, BG, marés|Leitura; downloads/exportação gravam arquivo local|
|E-Funcional|Consulta; imprimir usa mutation LogPrint para hash temporário|
|Férias reaprazar|Prévia com `--dry-run`; SEM essa opção altera períodos|
|SISDO criar/inserir/função/remover/vagas/escala|Prévia padrão; `--executar` habilita escrita autorizada|
|SISDO imprimir|PDF para destino novo, sem publicar OS|
|Voluntários/perfil/prévia|Leitura/prévia; exportação definitiva desabilitada|
|Voluntariado-inscrever|Prévia padrão; --executar envia inclusão própria, preserva quartéis atuais e confere perfil|
|RI listar/fila/reconciliar|Leitura HTTP; snapshots locais|
|RI validar|Offline; validação técnica não autoriza upload|
|RI cadastrar|Upload+CreateRepositorio; somente manual PDF pendente, `--enviar` obrigatório|
|GraphQL raw|Pode conter mutation: inspecione texto, nome do comando query não garante leitura|

RI/voluntariado interrompem em sessão, timeout, HTTP, filtros/cabeçalhos divergentes, dados inválidos e paginação inconsistente. Não transformar erro em zero registros. Comandos legados têm saída heterogênea: alguns imprimem erro/não encontrado com exit0. Verifique exit code, formato, resultado, totais e lacunas; não trate qualquer texto como sucesso/PDF. Não exponha erros crus com tickets/segredos. Consultas parciais não comprovam inventário completo.

## Pessoal, frota e GraphQL

```sh
sisbom efetivo --lotacao "$LOTACAO_AUTORIZADA" --json
sisbom militar "$IDENTIFICADOR_AUTORIZADO" --json
sisbom aniversariantes 03 --dia 15 --json
sisbom lotacoes --json
sisbom diarias --json
sisbom viaturas --json
sisbom introspect MilitarEfetivo
sisbom query '{ me { _id } }'
```

`militar` interpreta11 dígitos como CPF, outros como matrícula. `diarias` não tem filtro CLI adicional. Introspecção descreve schema, não prova permissão. `query --vars` recebe objeto JSON; aspas simples preservam `$variavel` GraphQL. Não existem comandos autônomos `ferias`, `mares`, `permutas`; métodos/queries no cliente não equivalem a comandos registrados.

## BGs regulares, especiais e aditamentos

```sh
sisbom bgs --year 2026 --json
sisbom bgs --num 'BG 040' --year 2026 --json
sisbom bg-download 040 --year 2026 --dest ./privado/bgs --json
```

Catálogo público `/api-bg/graphql`, sem login obrigatório. Regulares40/040/BG040 são normalizados para040; especiais/aditamentos preservam rótulo original. Copie `bg_num` exato do catálogo para `--num` ou download, sem inventar grafia. Não há `--tipo`; preservar rótulo não comprova que todo especial exista no servidor. `source_bg_num` conserva origem regular. Número BG não identifica portaria.

Sem ano/número, bgs limita20 (`--limit`); com ano ou número não aplica esse limite. Download sem ano escolhe primeiro ordenado: prefira ano explícito. Docs não tem paginação neste contrato. Conferir ano, URL, arquivo e integridade. Boletins integrais são excluídos do lote RI; recortes exigem revisão/autorização próprias.

## Maré Natal/BRT e mapa de força

```sh
sisbom mare-sisbom --date 2026-10-04 --json
sisbom mare --local natal --json
sisbom mapa-forca --lotacao "$LOTACAO_AUTORIZADA" --date 2026-10-04 --json
sisbom mapa-forca-mensal --lotacao "$LOTACAO_AUTORIZADA" --mes 2026-10 --json
sisbom mapa-forca-export --lotacao "$LOTACAO_AUTORIZADA" --mes 2026-10 --format csv --output ./privado/mapa.csv
```

`mare-sisbom` consulta Natal/RN em `/api/ws/tide_table/YYYY-MM-DD`, dia padrão America/Fortaleza(BRT), valida data/horários/alturas. Display legado alta/baixa usa limiar de altura, não classificação hidrodinâmica comprovada; conservar horários/alturas JSON. `mare` usa tabuademares.com, padrão areia-branca; extração externa tem limites diferentes.

Mapa diário vem de MilitaresMapaForca/MapaGuarnicoesMilitar, conserva viatura/militares/função/atividade/DO. Dia padrão BRT; lotação padrão específica, portanto informe unidade. Mensal conserva dias/DO e admite output; export formatos csv/md. Registro do SISBOM não comprova presença independente nem equivale à previsão Escalador. Não há comando de escrita de mapa.

## E-Funcional e férias

```sh
sisbom efuncional --matricula "$MATRICULA_AUTORIZADA" --list --json
sisbom efuncional --matricula "$MATRICULA_AUTORIZADA" --dest ./privado/funcional --json
sisbom ferias-reaprazar --matricula "$MATRICULA_AUTORIZADA" --exercicio 2026 \
  --periodos '01/11/2026-15/11/2026,01/12/2026-15/12/2026' \
  --justificativa "$JUSTIFICATIVA_AUTORIZADA" --dry-run --json
```

E-Funcional sem matrícula usa usuário atual; sem list pode imprimir/download. LogPrint gera hash temporário; CPF/QR/PDF são privados. Reaprazamento aceita matrícula/nome, exercício e lotação; ambiguidade interrompe. Confira soma de dias e todos os períodos: mutation substitui lista do exercício. `--dry-run` consulta autenticada e monta prévia; retirar flag permite escrita, sem `--executar`. Mensagem de validação/exit0 não é sucesso. Timeout exige leitura/reconciliação, nunca retry cego.

## SISDO: OSs e reconciliação Escalador

```sh
sisbom sisdo listar --status digitadas --json
sisbom sisdo criar --arquivo ./privado/os.json
sisbom sisdo inserir --os-id "$OS_ID" --numero "$OS_NUMERO" --matricula "$MATRICULA_AUTORIZADA" --nome "$NOME_ESPERADO" --funcao Motorista
sisbom sisdo funcao --os-id "$OS_ID" --numero "$OS_NUMERO" --matricula "$MATRICULA_AUTORIZADA" --nome "$NOME_ESPERADO" --funcao Motorista
sisbom sisdo remover --os-id "$OS_ID" --numero "$OS_NUMERO" --matricula "$MATRICULA_AUTORIZADA" --nome "$NOME_ESPERADO" --justificativa "$JUSTIFICATIVA_AUTORIZADA"
sisbom sisdo acrescentar-vagas --os-id "$OS_ID" --numero "$OS_NUMERO" --quantidade 1
sisbom sisdo reduzir-vagas --os-id "$OS_ID" --numero "$OS_NUMERO" --total 2
sisbom sisdo imprimir --os-id "$OS_ID" --numero "$OS_NUMERO" --destino ./privado/os.pdf
```

Exemplos de alteração são prévias sem executar. Status: digitadas/publicadas/fechadas/canceladas/finalizadas; visibilidade é a da unidade de acesso. Criação usa campos/valores do formulário atual, sem enum inventado; [detalhes SISDO](sisdo-httpx.md). ID interno+número impresso devem coincidir, matrícula+nome conferidos. Alteração exige OS digitada/vaga/estado adequados; função deve existir nas opções. Remoção exige justificativa; redução só vagas vazias e usa GET **mutante**. Não há publicação automática de OS. Imprimir exige destino inexistente e salva0600.

Releitura após escrita; timeout/login/mudança de formulário não causam retry automático. SISDO não tem ledger geral de todas as mutações: estado persistido específico é da reconciliação Escalador.

```sh
sisbom sisdo escala --data 2026-10-04 --modelo ./privado/modelo.json \
  --estado ./privado/estado.json --consulta-script ./integracao/consultar.py
```

Cliente externo Escalador não distribuído. Informe consulta-script explicitamente; não depender do caminho histórico de uma instalação. Modelo define quartel/unidade/campos/tipos/funções. `--vincular-os ID:NUMERO` exige vínculo explícito e pode gravar estado **local** na prévia. Estados/locks são privados; não apagar para forçar retomada. `--esperar-hash` e `--esperar-conferencia` prendem à prévia; `--executar` corrige com justificativa para retiradas. Origem relida antes/depois; divergências interrompem, sem publicar OS. Comando pontual não agenda cron.

## Voluntariado: consultas, prévias e inscrição própria

```sh
sisbom sisdo voluntarios --competencia 2026-11 --quartel apodi --quartel mossoro --json
sisbom sisdo voluntariado-perfil
sisbom sisdo voluntariado-prever --competencia 2026-11 --quartel assu --modo adicionar
```

CompetênciaAAAA-MM explícita, quartéis repetíveis assu/apodi/pau-dos-ferros/mossoro ou ID validado no servidor. Cada vínculo conserva competência/quartel de interesse/lotação atual; dedup por competência/quartel/matrícula mantém múltiplos vínculos e falha em conflito. `todas` recusado porque perde contexto. Lista provisória/definitiva disponível **não gera/exporta definitiva**.

Perfil lê ciclo do próprio usuário. Prévia adicionar conserva inscrições existentes; remover/substituir exigem permitir-remocao quando retiram algo; isso só libera prévia. Conjunto vazio recusado, competência deve coincidir com ciclo real. Antes/depois/diferenças/hash saem JSON sem CSRF. No comando voluntariado-prever, `envio_habilitado=false`: ele não envia nem habilita retirada/substituição. Não afirmar inscrito com base em prévia. A inclusão própria é feita pelo comando dedicado abaixo; regras adicionais de elegibilidade são do servidor.

### Inscrever sem abrir SISDO

```sh
# Prévia aditiva, sem POST:
sisbom sisdo voluntariado-inscrever --competencia 2026-11 --quartel assu
# Somente com autorização para a própria inscrição e quartéis/ciclo definidos:
sisbom sisdo voluntariado-inscrever --competencia 2026-11 --quartel assu \
  --diario ./privado/inscricao.json --esperar-hash "$HASH_PREVIA" --executar
sisbom sisdo voluntariado-perfil  # reconciliação somente leitura
```

Quartel repetível; nomes curtos ou IDs disponíveis na sessão. Somente adicionar, sem modo de retirada/substituição. Preserva todos os quartéis atuais e resposta Sim, não escolhe rodada/escala nem exporta lista. Prévia é padrão; execução exige diário privado por usuário e competência, preservado entre retomadas. esperar-hash opcional prende à prévia. Perfil/ciclo/opções/formulário/CSRF são relidos antes de um único POST oficial, e perfil é conferido depois: ciclo/resposta/conjunto completo precisam coincidir. Não define elegibilidade de terceiros.

Diário0600 registra intenção antes do POST, sem CSRF; lock impede processos no mesmo diário. Se já inscrito no conjunto esperado, retorna confirmado/idempotente sem POST. Timeout, erro de servidor, redirecionamento inesperado ou perfil divergente deixam reconciliação necessária, sem retry automático. Reexecutar só lê para confirmar uma intenção anterior; se divergir, bloqueia. Outro diário ou outro usuário perde a proteção local: não trocar/apagar diário para forçar envio. O servidor não oferece garantia de concorrência transacional; mudanças simultâneas ainda exigem conferência.

Fluxo de escrita foi validado com HTTP simulado e fixtures sintéticas; nenhuma inscrição real foi efetuada durante esta release. Confirmação de sucesso em uso real depende da releitura, não só do HTTP200/302. Retirada total/resposta Não e exportação definitiva continuam sem escrita habilitada.

GET `/sisdo/voluntariado` com lotacao_id/mes_referencia e GET `/usuario/voluntariado`. POST de inscrição própria exposto só no comando abaixo; exportação definitiva não exposta. Paginação nova ou vazio sem indicação explícita interrompem. [Detalhes](voluntariado-sisdo.md).

## Repositório Institucional: inventário e cadastro pendente

```sh
sisbom repositorio listar --dest ./privado/ri.json
sisbom repositorio fila --dest ./privado/fila.json
sisbom repositorio validar ./privado/lote.json --raiz ./privado
sisbom repositorio reconciliar ./privado/diario.json
```

Listar retorna todos os tipos/status observáveis, sem paginação GraphQL; não comprova cobertura de coleções privadas distintas. Fila exaure DataTables sem filtros, registra IDs/inícios/quantidades e compara catálogo. Total instável, ID inválido/repetido ou página incompleta interrompem; confira confronto_catalogo antes de afirmar cobertura. Snapshots UTC; status cadastral não prova vigência jurídica.

Escrita inicial só manual PDF, assinatura/tamanho até12MiB e SHA igual ao manifesto. Manifesto `{"itens":[...]}` exige id_fonte/arquivo_local/sha256/nome_proposto/tipo/tema; text_sha256 opcional. data_manual apenas mês explícitoYYYY-MM; não inferir de data de upload. raiz resolve arquivos. catalogo é LISTA analisada com source=Repositorio, _id, url e hashes disponíveis. Envelope bruto listar não é esse catálogo de hashes: preparar/analisar primeiro.

Compara IDs/URLs atuais e bloqueia alteração/correspondência por hash arquivo/texto ou título normalizado em qualquer status. Não substitui análise de órgão/espécie/número/ano/data/versão; mesmo número entre órgãos/anos não prova duplicata. Lacunas download/OCR e adoção institucional ficam explícitas. Temas precisam de confirmação, sem taxonomia inventada.

Somente lote autorizado pode usar:

```sh
sisbom repositorio cadastrar ./privado/lote.json --raiz ./privado \
  --catalogo ./privado/catalogo-analisado.json --diario ./privado/diario.json --enviar
```

Responsável vem de me; opção responsavel precisa coincidir. Upload oficial+CreateRepositorio pendente; sem aprovação/edição/exclusão. Cada registro confirmado por ID único/URL/hash remoto/status antes do próximo. Diário0600+lock; chave fonte/hash/metadados é idempotência LOCAL, não garantia do servidor. Outro diário perde proteção local. Preservar diário; resposta incerta interrompe e exige reconciliar (somente lê, não reenvia/apaga órfãos). BGs excluídos.

## Rotas e desenvolvimento

|Serviço|Rota usada|
|---|---|
|Legado geral|https://us-central1-cfap-app.cloudfunctions.net/api_sisbom/graphql|
|Login atual/RI|https://sisbom.cbm.rn.gov.br/api/graphql|
|BG|https://sisbom.cbm.rn.gov.br/api-bg/graphql|
|Maré|https://sisbom.cbm.rn.gov.br/api/ws/tide_table/YYYY-MM-DD|
|RI fila|https://sisbom.cbm.rn.gov.br/api/server_side/repositorio|
|RI upload|https://storage.cbm.rn.gov.br/uploads/index.php|
|SISDO|https://sisdo.cbm.rn.gov.br — SSO oficial/forms HTML, cookies em memória|

`python -m unittest discover -s tests -v`; MockTransport/fixtures sintéticas, sem operações institucionais. Build wheel/sdist, instalação venv limpa e smoke todos --help. Schema/permissões mudam: testes offline não garantem efeito atual de todas as escritas. Não publicar credenciais, estados, PDFs, listas ou caminhos pessoais. Release GitHub não é publicação PyPI.

## Referência completa das opções registradas
Gerada dos objetos Click desta versão. --help local é fonte final.

### `sisbom`
SISBOM CLI — acesso ao SISBOM via GraphQL.

### `sisbom aniversariantes`
Listar aniversariantes do mês.
- `mes`: STRING; obrigatório. 
- `--dia`: STRING; opcional. 
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom bg-download`
Baixar um BG pelo número.
- `bg_num`: STRING; obrigatório. 
- `--year`: STRING; opcional. Ano (padrão: mais recente)
- `--dest`: STRING; opcional. Diretório de destino
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom bgs`
Listar Boletins Gerais disponíveis no SISBOM.
- `--year`: STRING; opcional. Ano (ex: 2026)
- `--num`: STRING; opcional. Número do BG (ex: 040)
- `--limit`: INT; opcional; padrão `20`. Limite de resultados
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom diarias`
Listar diárias.
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom efetivo`
Listar efetivo militar.
- `--lotacao`: STRING; opcional. Filtrar por lotação
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom efuncional`
Exportar e-Funcional como PDF.
- `--matricula`: STRING; opcional. Matrícula do militar (default: usuário logado)
- `--dest`: STRING; opcional. Diretório destino do PDF
- `--list`: BOOL; opcional; padrão `False`. Listar emissões sem exportar
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom ferias-reaprazar`
Reaprazar (reprogramar) férias de um militar.
- `--matricula`: STRING; opcional. Matrícula do militar (ex: 2241986)
- `--nome`: STRING; opcional. Nome ou parte do nome (str_nomecurto)
- `--exercicio`: STRING; opcional. Ano do exercício (ex: 2025, default: último disponível)
- `--lotacao`: STRING; opcional. Filtro de lotação (ex: 1CAT, 3GBM)
- `--periodos`: STRING; obrigatório. Novos períodos: "DD/MM/YYYY-DD/MM/YYYY,..." (múltiplos separados por vírgula)
- `--justificativa`: STRING; obrigatório. Justificativa do reaprazamento
- `--dry-run`: BOOL; opcional; padrão `False`. Mostrar payload sem executar
- `--json`: BOOL; opcional; padrão `False`. Saída em JSON

### `sisbom introspect`
Introspect a GraphQL type.
- `type_name`: STRING; obrigatório. 

### `sisbom login`
Login no SISBOM e obter token JWT.
- `--api-url`: Choice(['https://us-central1-cfap-app.cloudfunctions.net/api_sisbom', 'https://sisbom.cbm.rn.gov.br/api']); opcional; padrão `https://us-central1-cfap-app.cloudfunctions.net/api_sisbom`. Endpoint oficial de autenticação; seleção explícita, sem alterar configuração global.
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom lotacoes`
Listar lotações disponíveis.
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom mapa-forca`
Mapa de Força — militares e disposição nas viaturas registrados no SISBOM.
- `--lotacao`: STRING; opcional; padrão `PABM_3GBM_APODI`. Código da lotação
- `--date`: STRING; opcional. Data (YYYY-MM-DD), default=hoje
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom mapa-forca-export`
Export DO mensal para preenchimento no Rota.
- `--lotacao`: STRING; opcional; padrão `PABM_3GBM_APODI`. Código da lotação
- `--mes`: STRING; opcional. Mês (YYYY-MM), default=mês atual
- `--format`: Choice(['csv', 'md']); opcional; padrão `csv`. 
- `--output`: STRING; opcional. Salvar em arquivo

### `sisbom mapa-forca-mensal`
Relatório mensal de DOs — controle de diárias.
- `--lotacao`: STRING; opcional; padrão `PABM_3GBM_APODI`. Código da lotação
- `--mes`: STRING; opcional. Mês (YYYY-MM), default=mês atual
- `--output`: STRING; opcional. Salvar markdown em arquivo
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom mare`
Tábua de marés do dia (via tabuademares.com).
- `--local`: STRING; opcional; padrão `areia-branca`. Localidade (slug tabuademares)
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom mare-sisbom`
Tábua de marés do SISBOM (Natal/RN).
- `--date`: STRING; opcional. Data (YYYY-MM-DD, default: hoje)
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom me`
Dados do usuário logado.
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom militar`
Consultar militar por matrícula ou CPF.
- `query`: STRING; obrigatório. 
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom query`
Executar query GraphQL raw.
- `graphql_query`: STRING; obrigatório. 
- `--vars`: STRING; opcional. JSON variables

### `sisbom repositorio`
Repositório Institucional HTTP; sem navegador ou renovação de login.

### `sisbom repositorio cadastrar`
Cadastrar manuais, um por vez; conferir ID/status/hash antes do próximo.
- `manifesto`: <click.types.Path object at 0x105e9db80>; obrigatório. 
- `--raiz`: <click.types.Path object at 0x105e9d9a0>; obrigatório. 
- `--catalogo`: <click.types.Path object at 0x105ea5710>; obrigatório. 
- `--diario`: <click.types.Path object at 0x105ea6350>; obrigatório. 
- `--responsavel`: STRING; opcional. Opcional: deve coincidir com nome curto retornado por me; padrão automático.
- `--enviar`: BOOL; obrigatório. Executar upload e cadastro pendente, com autorização do lote.

### `sisbom repositorio fila`
Exaurir tabela administrativa HTTP; cache válido, todos status, sem filtros.
- `--dest`: <click.types.Path object at 0x105ef85a0>; obrigatório. 

### `sisbom repositorio listar`
Catálogo público completo retornado por Repositorio (todos status).
- `--dest`: <click.types.Path object at 0x105ef8490>; obrigatório. 

### `sisbom repositorio reconciliar`
Somente leitura HTTP. Confirmar IDs de envios anteriores; nunca reenviar.
- `diario`: <click.types.Path object at 0x105e89d90>; obrigatório. 

### `sisbom repositorio validar`
Validação offline, sem login, rede, upload ou aprovação técnica.
- `manifesto`: <click.types.Path object at 0x105e3d750>; obrigatório. 
- `--raiz`: <click.types.Path object at 0x105e3d850>; obrigatório. 

### `sisbom sisdo`
Ordens de serviço do SISDO via HTTPX e SSO do SISBOM.

### `sisbom sisdo acrescentar-vagas`
Acrescentar vagas para inclusões adicionais.
- `--os-id`: INT; obrigatório. 
- `--numero`: STRING; obrigatório. 
- `--quantidade`: INT; obrigatório. 
- `--executar`: BOOL; opcional; padrão `False`. 

### `sisbom sisdo criar`
Criar uma OS digitada com campos explícitos de um JSON.
- `--arquivo`: <click.types.Path object at 0x105e050f0>; obrigatório. 
- `--executar`: BOOL; opcional; padrão `False`. Enviar criação; sem esta opção, apenas validar.

### `sisbom sisdo escala`
Transportar/conferir diárias do Escalador em OSs digitadas do SISDO.
- `--data`: STRING; obrigatório. Data de início, YYYY-MM-DD, no fuso de Fortaleza.
- `--modelo`: <click.types.Path object at 0x105d53380>; obrigatório. 
- `--estado`: <click.types.Path object at 0x105df1a90>; obrigatório. Registro privado de vínculos com OSs.
- `--consulta-script`: <click.types.Path object at 0x105df1f90>; opcional; caminho local configurável, informe explicitamente. 
- `--vincular-os`: STRING; opcional. Vincular explicitamente OS existente: ID:NUMERO.
- `--esperar-hash`: STRING; opcional. Recusar execução se a escala mudou desde a prévia.
- `--esperar-conferencia`: STRING; opcional. Recusar execução se o estado SISDO/diferenças mudou desde a prévia.
- `--justificativa`: STRING; opcional; padrão ``. Obrigatória se a correção retirar militares.
- `--executar`: BOOL; opcional; padrão `False`. Aplicar inclusões/retiradas e ajustar vagas; padrão apenas confere.

### `sisbom sisdo funcao`
Definir uma função disponível no formulário da vaga ocupada.
- `--os-id`: INT; obrigatório. 
- `--numero`: STRING; obrigatório. 
- `--matricula`: STRING; obrigatório. 
- `--nome`: STRING; obrigatório. 
- `--funcao`: STRING; obrigatório. 
- `--executar`: BOOL; opcional; padrão `False`. 

### `sisbom sisdo imprimir`
Baixar o PDF oficial da OS sem abrir navegador.
- `--os-id`: INT; obrigatório. 
- `--numero`: STRING; obrigatório. 
- `--status`: Choice(['digitadas', 'publicadas', 'fechadas', 'canceladas', 'finalizadas']); opcional; padrão `digitadas`. 
- `--destino`: <click.types.Path object at 0x105e09910>; obrigatório. 

### `sisbom sisdo inserir`
Inserir militar por matrícula em uma OS digitada com vaga.
- `--os-id`: INT; obrigatório. ID interno da OS.
- `--numero`: STRING; obrigatório. Número impresso, conferido junto ao ID.
- `--matricula`: STRING; obrigatório. 
- `--nome`: STRING; obrigatório. Nome de guerra esperado para conferir a matrícula.
- `--funcao`: STRING; opcional. Motorista, tipo da OS, CMTE da OS ou CMTE da GU.
- `--executar`: BOOL; opcional; padrão `False`. Enviar inclusão; sem esta opção, apenas validar.

### `sisbom sisdo listar`
Consultar OSs visíveis na unidade do acesso atual.
- `--status`: Choice(['digitadas', 'publicadas', 'fechadas', 'canceladas', 'finalizadas']); opcional; padrão `digitadas`. 
- `--json`: BOOL; opcional; padrão `False`. 

### `sisbom sisdo reduzir-vagas`
Reduzir o total removendo somente linhas atualmente vazias.
- `--os-id`: INT; obrigatório. 
- `--numero`: STRING; obrigatório. 
- `--total`: INT; obrigatório. Total final, incluindo os militares já inseridos.
- `--executar`: BOOL; opcional; padrão `False`. 

### `sisbom sisdo remover`
Remover militar pela matrícula, com justificativa obrigatória.
- `--os-id`: INT; obrigatório. 
- `--numero`: STRING; obrigatório. 
- `--matricula`: STRING; obrigatório. 
- `--nome`: STRING; obrigatório. 
- `--justificativa`: STRING; obrigatório. 
- `--executar`: BOOL; opcional; padrão `False`. 

### `sisbom sisdo voluntariado-inscrever`
Inscrever o próprio usuário, sem retirar quartéis atuais; conferir após POST.
- `--competencia`: STRING; obrigatório. AAAA-MM; deve coincidir com ciclo aberto do próprio perfil.
- `--quartel`: STRING; obrigatório. Adicionar quartel, preservando seleções existentes; repetível.
- `--diario`: <click.types.Path object at 0x105e05350>; opcional. Diário privado por usuário; obrigatório com --executar.
- `--esperar-hash`: STRING; opcional. Hash da prévia; recusar perfil diferente.
- `--executar`: BOOL; opcional; padrão `False`. Enviar a própria inscrição aditiva; padrão apenas prévia.

### `sisbom sisdo voluntariado-perfil`
Consultar ciclo e inscrições atuais do próprio usuário.

### `sisbom sisdo voluntariado-prever`
Prévia sem POST; preservar inscrições existentes por padrão.
- `--competencia`: STRING; obrigatório. 
- `--quartel`: STRING; obrigatório. 
- `--modo`: Choice(['adicionar', 'remover', 'substituir']); opcional; padrão `adicionar`. 
- `--permitir-remocao`: BOOL; opcional; padrão `False`. Permitir somente a PRÉVIA de remoções explícitas.

### `sisbom sisdo voluntarios`
Consultar inscrições mensais sem gerar lista definitiva.
- `--competencia`: STRING; obrigatório. AAAA-MM; nunca inferida da data atual.
- `--quartel`: STRING; obrigatório. assu, apodi, pau-dos-ferros, mossoro ou ID; repetível.
- `--json`: BOOL; opcional; padrão `False`. Saída JSON (também padrão).

### `sisbom viaturas`
Listar viaturas.
- `--json`: BOOL; opcional; padrão `False`. 
