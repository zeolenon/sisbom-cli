"""Browserless RI workflow. Auth is cache-only; mutations are never retried.

Mapped from the SISBOM gestor/service bundles on 2026-10-04. This first
release registers manuals only, pending curator review. It does not edit,
delete, approve, log in, refresh credentials or touch browser sessions.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import re
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import click
import httpx

from ..auth import load_token

API = "https://sisbom.cbm.rn.gov.br/api/graphql"
UPLOAD = "https://storage.cbm.rn.gov.br/uploads/index.php"
QUEUE = "https://sisbom.cbm.rn.gov.br/api/server_side/repositorio"
FIELDS = """_id tipo nome tema tema_ordem url ordem
data_legislacao tipo_legislacao status_legislacao data_manual
data_pop status_pop tipo_processo tipo_trabalho data_trabalho
tipo_original data_revogacao diretoria_id diretoria_nome setor_id setor_nome
responsavel data_envio status_doc obs_curador"""


def now():
    return datetime.now(timezone.utc).isoformat()


def normalized(value):
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def slug(value):
    return normalized(value).replace(" ", "-") or "geral"


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.chmod(0o600)
    temp.replace(path)


class RepositoryClient:
    def __init__(self, transport=None):
        self.http = httpx.Client(timeout=60, follow_redirects=False,
                                 headers={"Accept": "application/json"}, transport=transport)
        self.token = None

    def close(self):
        self.http.close()

    def require_cached_auth(self):
        self.token = load_token()
        if not self.token:
            raise RuntimeError("Sessão canônica ausente/expirada. Restabeleça a autenticação do SISBOM CLI; nenhum login/refresh ou upload foi tentado.")

    def headers(self):
        return {"Authorization": "Bearer " + self.token} if self.token else {}

    def gql(self, query, variables=None):
        try:
            response = self.http.post(API, json={"query": query, "variables": variables or {}}, headers=self.headers())
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            raise RuntimeError("Resposta HTTP/JSON não confirmada; sem repetição automática.") from None
        if body.get("errors"):
            # Do not echo server bodies: they may contain input or credentials.
            raise RuntimeError("GraphQL rejeitou a operação; sem renovação de sessão ou repetição.")
        return body.get("data", {})

    def records(self):
        rows = self.gql("query { Repositorio { " + FIELDS + " } }").get("Repositorio")
        if not isinstance(rows, list) or any(not r.get("_id") for r in rows):
            raise RuntimeError("Catálogo sem IDs válidos; cobertura não confirmada.")
        if len({r['_id'] for r in rows}) != len(rows):
            raise RuntimeError("IDs repetidos no catálogo; interrompido.")
        return rows

    def responsible(self):
        person = self.gql("query { me { str_nomecurto } }").get("me") or {}
        name = (person.get("str_nomecurto") or "").strip()
        if not name:
            raise RuntimeError("Nome curto do usuário autenticado não confirmado; não preencher responsável por inferência.")
        return name

    def queue(self, page_size=100):
        """DataTables route observed in gestor/curadoria; exhaust all pages."""
        self.require_cached_auth()
        pages, ids, start, total = [], set(), 0, None
        while True:
            try:
                response = self.http.get(QUEUE, params={"draw": len(pages) + 1, "start": start, "length": page_size, "search[value]": ""}, headers=self.headers())
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError):
                raise RuntimeError("Fila HTTP indisponível/não autorizada; sem login ou extração de cookies.") from None
            current_total = body.get("recordsTotal")
            if not isinstance(current_total, int) or body.get("recordsFiltered") != current_total:
                raise RuntimeError("Total/filtros da fila não confirmados.")
            if total is not None and total != current_total:
                raise RuntimeError("Fila mudou durante a coleta; snapshot não exaurido.")
            total = current_total
            rows = body.get("data")
            if not isinstance(rows, list) or len(rows) != min(page_size, total - start):
                raise RuntimeError("Página incompleta; não declarar exaustão.")
            page_ids = []
            for row in rows:
                value = row.get("_id") if isinstance(row, dict) else row[0] if isinstance(row, list) and row else None
                if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", value) or value in ids:
                    raise RuntimeError("ID da fila ausente/repetido; conferir contrato HTTP.")
                ids.add(value)
                page_ids.append(value)
            pages.append({"inicio": start, "quantidade": len(rows), "ids": page_ids})
            start += len(rows)
            if start == total:
                return {"coleta_utc": now(), "rota": QUEUE, "total": total, "paginas": pages, "exaurido": True}
            if not rows or start > total or len(pages) >= 10000:
                raise RuntimeError("Paginação inconsistente; interrompida.")

    def file_hash(self, url):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "storage.cbm.rn.gov.br":
            raise RuntimeError("Download de hash limitado ao storage oficial; conferir fonte externa separadamente.")
        try:
            response = self.http.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            raise RuntimeError("Não foi possível conferir o arquivo oficial.") from None
        if not response.content.startswith(b"%PDF-"):
            raise RuntimeError("Arquivo remoto não confirmou assinatura PDF.")
        return hashlib.sha256(response.content).hexdigest()


def validate_item(item, root):
    path = (Path(root) / item["arquivo_local"]).resolve()
    content = path.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    name = item.get("nome_proposto", "").strip()
    theme = item.get("tema", "").strip()
    if item.get("tipo") != "manual" or not name or not theme:
        raise RuntimeError("Primeira versão exige tipo manual, nome e tema explícitos.")
    if re.search(r"\b(bg|boletim|boletins)\b", normalized(name)):
        raise RuntimeError("Boletins Gerais excluídos deste lote.")
    if path.suffix.lower() != ".pdf" or not content.startswith(b"%PDF-"):
        raise RuntimeError("Manual deve ser PDF válido; extensão não basta.")
    if not content or len(content) > 12 * 1024 * 1024 or sha != item.get("sha256"):
        raise RuntimeError("Hash/tamanho do arquivo diverge do manifesto autorizado.")
    payload = {"tipo": "manual", "nome": name, "tema": theme, "status_doc": "pendente"}
    # Optional month omitted when unknown. A publication/upload date is not an edition date.
    if item.get("data_manual"):
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", item["data_manual"]):
            raise RuntimeError("data_manual deve ser mês explícito YYYY-MM, sem inferir da data de upload.")
        payload["data_manual"] = item["data_manual"]
    key = hashlib.sha256(json.dumps([item["id_fonte"], sha, payload], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return path, sha, payload, key


def check_catalog(rows, baseline, item, sha):
    known = {r["_id"]: r for r in baseline if r.get("source") == "Repositorio"}
    unknown = [r["_id"] for r in rows if r["_id"] not in known or r.get("url") != known[r["_id"]].get("url")]
    missing = set(known) - {r["_id"] for r in rows}
    if missing:
        raise RuntimeError("IDs do catálogo anterior não retornaram; conferir permissões/cobertura antes de enviar.")
    if unknown:
        raise RuntimeError("Catálogo mudou: atualizar hashes e revisão antes do envio. IDs novos/URL alterada: " + ", ".join(unknown))
    duplicates = [r for r in rows if known[r["_id"]].get("sha256") == sha
                  or (known[r["_id"]].get("text_sha256") and known[r["_id"]].get("text_sha256") == item.get("text_sha256"))
                  or normalized(r.get("nome")) == normalized(item["nome_proposto"])]
    if duplicates:
        raise RuntimeError("Correspondência já existe em algum status: " + ", ".join(r["_id"] for r in duplicates))
    return known


def reconcile(client, entry, rows):
    matches = [r for r in rows if r.get("url") == entry.get("url")
               and r.get("tipo") == entry["payload"]["tipo"]
               and normalized(r.get("nome")) == normalized(entry["payload"]["nome"])
               and r.get("tema") == entry["payload"]["tema"]]
    if len(matches) != 1:
        return {"confirmado": False, "matches": len(matches), "acao": "Reconciliar manualmente; nunca reenviar automaticamente."}
    row = matches[0]
    if row.get("status_doc") != "pendente" or client.file_hash(row["url"]) != entry["sha256"]:
        raise RuntimeError("ID encontrado, mas status/hash diverge; interrompido antes do próximo documento.")
    return {"confirmado": True, "id": row["_id"], "url": row["url"], "status_doc": row["status_doc"], "sha256": entry["sha256"]}


def register(client, item, root, baseline, journal, responsible):
    path, sha, payload, key = validate_item(item, root)
    state = json.loads(journal.read_text()) if journal.exists() else {"operacoes": {}}
    previous = state["operacoes"].get(key)
    if previous:
        if previous.get("fase") == "confirmado":
            result = reconcile(client, previous, client.records())
            if result["confirmado"]:
                return {"idempotente": True, **result}
        raise RuntimeError("Operação anterior não confirmada: use reconciliar. Upload/cadastro não serão repetidos.")
    # Every previously confirmed entry is merged into the baseline for next item.
    merged = baseline + [{"source": "Repositorio", "_id": e["resultado"]["id"], "url": e["url"], "sha256": e["sha256"]}
                         for e in state["operacoes"].values() if e.get("fase") == "confirmado"]
    check_catalog(client.records(), merged, item, sha)
    payload["responsavel"] = responsible
    entry = {"id_fonte": item["id_fonte"], "sha256": sha, "payload": payload, "fase": "upload_iniciado", "inicio_utc": now()}
    state["operacoes"][key] = entry
    write_json(journal, state)  # durable intent before the first side effect
    try:
        with path.open("rb") as file:
            response = client.http.post(UPLOAD, headers=client.headers(),
                                        data={"folder": "repositorio", "_id": "manual-" + slug(payload["tema"])},
                                        files={"arquivo": (path.name, file, "application/pdf")})
        response.raise_for_status()
        url = response.json().get("url")
        if not url:
            raise RuntimeError("Storage não retornou URL.")
        if client.file_hash(url) != sha:
            raise RuntimeError("Hash do arquivo armazenado diverge.")
        entry.update(url=url, fase="arquivo_confirmado")
        write_json(journal, state)
        payload["url"] = url
        entry["fase"] = "cadastro_iniciado"
        write_json(journal, state)
        # Never invoke approval/update/delete; pending is explicit in input.
        result = client.gql("mutation CreateRepositorio($input: RepositorioInput) { CreateRepositorio(input: $input) { status msg } }", {"input": payload})
        entry["retorno_status"] = result.get("CreateRepositorio", {}).get("status")
        # The API returns status/msg, not ID. Reconcile regardless of reported success.
        verified = reconcile(client, entry, client.records())
        entry["resultado"] = verified
        entry["fase"] = "confirmado" if verified["confirmado"] else "reconciliacao_necessaria"
        entry["fim_utc"] = now()
        write_json(journal, state)
        if not verified["confirmado"]:
            raise RuntimeError("Cadastro sem ID único confirmado; parar e reconciliar.")
        return verified
    except (httpx.HTTPError, ValueError, RuntimeError):
        entry["necessita_reconciliacao"] = True
        write_json(journal, state)
        raise RuntimeError("Envio não concluído/confirmado. Consulte o diário; não repita a mutação ou upload.") from None


@contextmanager
def locked(path):
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Outro processo usa este diário; interrompido.") from None
        yield


@click.group()
def repositorio():
    """Repositório Institucional HTTP; sem navegador ou renovação de login."""


@repositorio.command("listar")
@click.option("--dest", type=click.Path(path_type=Path), required=True)
def list_command(dest):
    """Catálogo público completo retornado por Repositorio (todos status)."""
    client = RepositoryClient()
    try:
        rows = client.records()
        report = {"coleta_utc": now(), "rota": API, "paginacao": "GraphQL Repositorio sem argumentos de paginação; não prova cobertura de tabelas privadas distintas", "total": len(rows), "registros": rows}
        write_json(dest, report)
        click.echo(json.dumps({"total": len(rows), "dest": str(dest)}, ensure_ascii=False))
    except RuntimeError as error:
        raise click.ClickException(str(error)) from None
    finally:
        client.close()


@repositorio.command("fila")
@click.option("--dest", type=click.Path(path_type=Path), required=True)
def queue_command(dest):
    """Exaurir tabela administrativa HTTP; cache válido, todos status, sem filtros."""
    client = RepositoryClient()
    try:
        result = client.queue()
        result["confronto_catalogo"] = sorted({x for p in result["paginas"] for x in p["ids"]} ^ {r["_id"] for r in client.records()})
        write_json(dest, result)
        click.echo(json.dumps({"total": result["total"], "paginas": [p["quantidade"] for p in result["paginas"]], "ids_divergentes": result["confronto_catalogo"]}, ensure_ascii=False))
    except RuntimeError as error:
        raise click.ClickException(str(error)) from None
    finally:
        client.close()


@repositorio.command("validar")
@click.argument("manifesto", type=click.Path(exists=True, path_type=Path))
@click.option("--raiz", type=click.Path(exists=True, path_type=Path), required=True)
def validate_command(manifesto, raiz):
    """Validação offline, sem login, rede, upload ou aprovação técnica."""
    try:
        items = json.loads(manifesto.read_text())["itens"]
        results = []
        for item in items:
            path, sha, payload, key = validate_item(item, raiz)
            results.append({"id_fonte": item["id_fonte"], "arquivo": str(path), "sha256": sha, "payload_sem_url": payload, "chave_idempotencia": key})
        click.echo(json.dumps({"validacao_tecnica": True, "envio_executado": False, "itens": results}, ensure_ascii=False, indent=2))
    except (RuntimeError, KeyError, OSError, ValueError) as error:
        raise click.ClickException(str(error)) from None


@repositorio.command("cadastrar")
@click.argument("manifesto", type=click.Path(exists=True, path_type=Path))
@click.option("--raiz", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--catalogo", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--diario", type=click.Path(path_type=Path), required=True)
@click.option("--responsavel", help="Opcional: deve coincidir com nome curto retornado por me; padrão automático.")
@click.option("--enviar", is_flag=True, required=True, help="Executar upload e cadastro pendente, com autorização do lote.")
def register_command(manifesto, raiz, catalogo, diario, responsavel, enviar):
    """Cadastrar manuais, um por vez; conferir ID/status/hash antes do próximo."""
    client = RepositoryClient()
    try:
        client.require_cached_auth()  # BEFORE any HTTP or upload
        if not enviar:
            raise RuntimeError("Envio precisa ser explícito.")
        actual_name = client.responsible()
        if responsavel and responsavel.strip() != actual_name:
            raise RuntimeError("Responsável diverge do usuário autenticado; interrompido.")
        items = json.loads(manifesto.read_text())["itens"]
        baseline = json.loads(catalogo.read_text())
        for item in items:
            validate_item(item, raiz)  # all local items pass before first write
        with locked(diario):
            for item in items:
                click.echo(json.dumps(register(client, item, raiz, baseline, diario, actual_name), ensure_ascii=False))
    except (RuntimeError, KeyError, OSError, ValueError) as error:
        raise click.ClickException(str(error)) from None
    finally:
        client.close()


@repositorio.command("reconciliar")
@click.argument("diario", type=click.Path(exists=True, path_type=Path))
def reconcile_command(diario):
    """Somente leitura HTTP. Confirmar IDs de envios anteriores; nunca reenviar."""
    client = RepositoryClient()
    try:
        state = json.loads(diario.read_text())
        rows = client.records()
        results = {k: reconcile(client, e, rows) if e.get("url") else {"confirmado": False, "acao": "URL não confirmada; conferir possível arquivo órfão, sem reenviar."}
                   for k, e in state["operacoes"].items()}
        click.echo(json.dumps(results, ensure_ascii=False, indent=2))
    except (RuntimeError, KeyError, OSError, ValueError) as error:
        raise click.ClickException(str(error)) from None
    finally:
        client.close()
