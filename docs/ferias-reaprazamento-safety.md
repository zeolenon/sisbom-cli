# Férias: melhorias recomendadas para `ferias-reaprazar`

Este documento registra pontos encontrados durante um fluxo real de parcelamento/reprogramação de férias no SISBOM. O caminho correspondente na interface web era:

1. `3º GBM`
2. `Reprogramação de férias`
3. `8ª turma`
4. `Página 2`
5. localizar o militar e clicar no calendário para alterar as datas

## Dificuldades encontradas

- O CLI não possui um comando de leitura/consulta de férias equivalente ao caminho da UI. Hoje o operador precisa usar `ferias-reaprazar --dry-run` para descobrir se o militar aparece em determinado exercício/turma.
- O parâmetro `--exercicio` não é óbvio para o usuário final: uma turma exibida na UI como 8ª turma de 2026 pode pertencer ao exercício administrativo 2025.
- Quando `--exercicio` é omitido, o CLI tenta o último exercício disponível. Isso pode levar a uma busca no exercício errado e mensagem pouco acionável (`Militar não encontrado nos critérios fornecidos`).
- A mutation de reaprazamento substitui todos os períodos do registro de férias do exercício. Isso é destrutivo e precisa de confirmação explícita antes da execução.
- A opção `--json` no comando de reaprazamento atualmente faz o comando retornar o payload sem executar, porque cai no mesmo ramo de `dry_run`. Isso é surpreendente: `--json` deveria controlar apenas o formato da saída, não o modo de execução.
- O dry-run em `--json` ainda inclui texto Rich antes/depois do JSON, dificultando consumo automatizado.
- Não há trava de segurança para impedir alterar as próprias férias do usuário logado por engano.
- Não há parâmetros de validação de contexto, como período original esperado, turma esperada, lotação esperada ou matrícula/nome esperado exibidos antes do commit.
- O CLI não gera comprovante visual ou relatório pronto para anexar ao SEI; foi necessário montar uma evidência manual a partir da saída do comando.

## Sugestões de melhoria

### 1. Separar consulta de alteração

Adicionar comandos de leitura sem efeito colateral, por exemplo:

```bash
sisbom ferias-listar --lotacao 3GBM --exercicio 2025 --turma 8 --page 2
sisbom ferias-militar --matricula 2433192 --exercicio 2025
```

Saída esperada: militar, matrícula, exercício, turma, lotação, períodos atuais, períodos ativos/inativos e IDs internos.

### 2. Exigir confirmação explícita para alteração

Mudar `ferias-reaprazar` para executar apenas com `--confirm`:

```bash
sisbom ferias-reaprazar ... --dry-run
sisbom ferias-reaprazar ... --confirm
```

Sem `--confirm`, o comando deve exibir o plano e abortar.

### 3. Trava contra autoalteração

Se a matrícula alvo for a do usuário autenticado (`sisbom me`), abortar por padrão:

```text
Erro: matrícula alvo pertence ao usuário logado. Use --allow-self somente se tiver certeza e competência para isso.
```

### 4. Validação do período original

Adicionar parâmetros opcionais de segurança:

```bash
--expected-original "03/08/2026-01/09/2026"
--expected-turma 8
--expected-lotacao 3GBM
--expected-nome "SD Matos"
```

Se o registro encontrado não bater com esses valores, abortar.

### 5. Corrigir semântica de `--json`

- `--json` deve controlar apenas o formato.
- `--dry-run` deve controlar se executa ou não.
- `--dry-run --json` deve imprimir JSON puro, sem prefixos Rich.
- `--confirm --json` deve executar e retornar JSON puro com resultado e registro atualizado.

### 6. Melhorar mensagens quando o exercício estiver errado

Quando a matrícula não for encontrada no exercício informado, o CLI poderia sugerir exercícios/turmas onde a matrícula existe:

```text
Militar não encontrado no exercício 2026.
Encontrado em:
- exercício 2025, turma 8, 03/08/2026 a 01/09/2026
- exercício 2024, turma 4, 07/04/2025 a 06/05/2025
```

### 7. Gerar comprovante para SEI

Adicionar uma opção de exportação:

```bash
--comprovante /tmp/reaprazamento-matos.png
--comprovante-md /tmp/reaprazamento-matos.md
```

O comprovante deve destacar os períodos ativos novos e incluir matrícula, exercício, turma, justificativa e horário da execução.

## Caso de teste recomendado

Fluxo de parcelamento do SD Matos:

- matrícula: `2433192`
- exercício administrativo: `2025`
- turma: `8`
- período original: `03/08/2026 a 01/09/2026`
- novos períodos:
  - `03/08/2026 a 12/08/2026` — 10 dias
  - `09/09/2026 a 18/09/2026` — 10 dias
  - `12/10/2026 a 21/10/2026` — 10 dias
- processo SEI: `08810116.000731/2026-17`

Total: 30 dias.
