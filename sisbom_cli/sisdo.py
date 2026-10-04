"""SISDO HTML forms over HTTPX; no browser or persisted SISDO cookies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from .client import SISBOMClient

BASE_URL = "https://sisdo.cbm.rn.gov.br"
STATUSES = ("digitadas", "publicadas", "fechadas", "canceladas", "finalizadas")
CREATE_FIELDS = {
    "dt_inicio", "hr_inicio", "dt_termino", "hr_termino", "st_cidade",
    "st_local", "st_localapresentacao", "dt_apresentacao", "st_responsavel",
    "cod_unidademarcacao[]", "st_tipooperacao", "dt_liberacao", "hr_liberacao",
    "nu_efetivo", "nu_graduados", "nu_motoristas", "nu_diarias", "st_obs",
}


class _AuthenticationError(RuntimeError):
    """Explicit redirect to login; never a reason to repeat a write."""


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", html)).split())


def matricula_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _operation_kind(value: str) -> str:
    value = value.casefold()
    if "ama" in value:
        return "ama"
    if "guarni" in value or value.strip() in ("ref. gu", "ref gu"):
        return "reforco-gu"
    return value


@dataclass
class Form:
    action: str
    method: str
    values: dict[str, Any] = field(default_factory=dict, repr=False)
    controls: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)
    options: dict[str, list[tuple[str, str]]] = field(default_factory=dict)


class _Forms(HTMLParser):
    """Track forms independently of the site's malformed modal/div nesting."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[Form] = []
        self.current: Form | None = None
        self.select: str | None = None
        self.option: dict[str, str] | None = None
        self.option_text: list[str] = []
        self.textarea: str | None = None
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "form":
            self.current = Form(a.get("action", ""), a.get("method", "get").lower())
            self.forms.append(self.current)
        if not self.current:
            return
        name = a.get("name")
        if tag in ("input", "select", "textarea") and name and "disabled" not in a:
            self.current.controls[name] = a
            if tag == "input":
                if a.get("type") not in ("submit", "button", "checkbox", "radio") or "checked" in a:
                    self.current.values[name] = a.get("value", "")
            elif tag == "select":
                self.select = name
                self.current.options[name] = []
                self.current.values[name] = [] if "multiple" in a else ""
            else:
                self.textarea = name
                self.current.values[name] = ""
        if tag == "option" and self.select:
            self.option = a
            self.option_text = []

    def handle_data(self, data: str) -> None:
        if self.option is not None:
            self.option_text.append(data)
        if self.current and self.textarea:
            self.current.values[self.textarea] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self.current and self.select and self.option is not None:
            label = " ".join("".join(self.option_text).split())
            value = self.option.get("value", label)
            self.current.options[self.select].append((value, label))
            if "selected" in self.option:
                if isinstance(self.current.values[self.select], list):
                    self.current.values[self.select].append(value)
                else:
                    self.current.values[self.select] = value
            self.option = None
        elif tag == "select":
            if self.current and self.select:
                value = self.current.values[self.select]
                options = self.current.options[self.select]
                if value == "" and options:
                    self.current.values[self.select] = options[0][0]
            self.select = None
        elif tag == "textarea":
            self.textarea = None
        elif tag == "form":
            self.current = None


def _form(html: str, path: str) -> Form:
    matches = [f for f in _Forms(html).forms if urlsplit(f.action).path == path]
    if len(matches) != 1 or matches[0].method != "post":
        raise RuntimeError(f"Formulário POST indisponível ou ambíguo: {path}")
    return matches[0]


def parse_orders(html: str) -> list[dict[str, Any]]:
    forms = _Forms(html).forms
    orders = []
    headings = list(re.finditer(r'<div\b[^>]*\bid="heading(\d+)"[^>]*>', html))
    for i, heading in enumerate(headings):
        op = heading.group(1)
        segment = html[heading.start():headings[i + 1].start() if i + 1 < len(headings) else len(html)]
        title = re.search(r'OP nº\s*(\d+).*?Unidade Lançamento:\s*(.*?)</span>', segment, re.S)
        if not title:
            raise RuntimeError("Cabeçalho de OS não reconhecido; consulta interrompida.")
        labels = dict((_text(k).rstrip(":"), _text(v)) for k, v in re.findall(
            r'<label\b[^>]*>(.*?)</label>\s*<p\b[^>]*>(.*?)</p>', segment.split("<table", 1)[0], re.S))
        edit = next((f for f in forms if urlsplit(f.action).path == f"/sisdo/{op}/op/editar"), None)
        fields = {}
        if edit:
            for name, value in edit.values.items():
                if name == "_token":
                    continue
                fields[re.sub(rf"{op}(?=\[\]|$)", "", name)] = value
        table = re.search(r'<table\b.*?</table>', segment, re.S)
        personnel = []
        vacant_slots = []
        if table:
            for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', table.group(), re.S):
                cells = [_text(c) for c in re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S)]
                if len(cells) >= 4 and matricula_digits(cells[1]):
                    member = {"matricula": cells[1], "posto": cells[2], "nome": cells[3]}
                    record = re.search(r'modalFuncao(\d+)', row)
                    if record:
                        member["registro_id"] = int(record.group(1))
                    personnel.append(member)
                elif len(cells) >= 4 and not cells[1]:
                    for link in re.findall(r'<a\b[^>]*href="([^"]+)"', row):
                        path = urlsplit(unescape(link)).path
                        slot = re.fullmatch(rf"/sisdo/{op}/op/(\d+)/vaga/excluir", path)
                        if slot:
                            vacant_slots.append({"id": int(slot.group(1)), "url": unescape(link)})
        orders.append({"id": int(op), "numero": title.group(1), "unidade_lancamento": _text(title.group(2)),
                       "dados": labels, "campos": fields, "militares": personnel, "vagas_vazias": vacant_slots})
    return orders


class SISDOClient:
    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(timeout=30, follow_redirects=False)
        self._authenticated = http is not None  # Injected transport for offline checks.

    def __enter__(self) -> SISDOClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = urljoin(BASE_URL, path)
        if urlsplit(url).scheme != "https" or urlsplit(url).netloc != urlsplit(BASE_URL).netloc:
            raise RuntimeError("Destino HTTP fora do SISDO.")
        if method == "POST":
            # Laravel's redirect-back uses the same Referer as the native forms.
            kwargs.setdefault("headers", {"Referer": BASE_URL + "/sisdo/op/listar/digitadas"})
        try:
            response = self._http.request(method, url, **kwargs)
            for _ in range(5):
                if not response.is_redirect:
                    break
                target = urljoin(str(response.url), response.headers["location"])
                parsed = urlsplit(target)
                if parsed.scheme == "https" and parsed.netloc == urlsplit(BASE_URL).netloc and parsed.path == "/login":
                    raise _AuthenticationError("Acesso SISDO redirecionou para login; consulte o estado se houve envio.")
                # Never follow a redirect to a mutating GET or replay a POST.
                safe = ("/home", *(f"/sisdo/op/listar/{s}" for s in STATUSES))
                if parsed.netloc != urlsplit(BASE_URL).netloc or parsed.scheme != "https" or parsed.path not in safe:
                    raise RuntimeError("Redirecionamento inesperado do SISDO; consulte o estado antes de repetir.")
                if response.status_code not in (301, 302, 303):
                    raise RuntimeError("Redirecionamento exigiria repetir a operação; envio interrompido.")
                response = self._http.get(target)
        except httpx.HTTPError:
            raise RuntimeError("Falha HTTP no SISDO; se houve envio, consulte o estado antes de repetir.") from None
        if response.status_code != 200:
            raise RuntimeError(f"SISDO respondeu HTTP {response.status_code}; consulte o estado antes de repetir.")
        return response

    def connect(self) -> None:
        if self._authenticated:
            return
        with SISBOMClient(api_url="https://sisbom.cbm.rn.gov.br/api") as sisbom:
            for attempt in range(3):
                data = sisbom._gql("""mutation CreateSsoTicket($target: String) {
                    CreateSsoTicket(target: $target) { token }
                }""", variables={"target": "sisdo"})
                ticket = (data.get("CreateSsoTicket") or {}).get("token")
                if not ticket:
                    raise RuntimeError("SISBOM não forneceu ticket de acesso ao SISDO.")
                self._http.cookies.clear()
                try:
                    response = self._request("GET", "/", params={"ticket": ticket})
                except _AuthenticationError:
                    # Only retry the initial SSO exchange, before any form submission.
                    if attempt == 2:
                        raise
                    continue
                if response.url.path != "/home" or "sisdo_session" not in self._http.cookies:
                    raise RuntimeError("Sessão SISDO não confirmada.")
                self._authenticated = True
                return

    def page(self, status: str = "digitadas") -> str:
        if status not in STATUSES:
            raise ValueError("Situação de OS inválida.")
        self.connect()
        return self._request("GET", f"/sisdo/op/listar/{status}").text

    def list_orders(self, status: str = "digitadas") -> list[dict[str, Any]]:
        return parse_orders(self.page(status))

    def lookup(self, matricula: str, expected_name: str) -> str:
        self.connect()
        digits = matricula_digits(matricula)
        if not re.fullmatch(r"\d{7}", digits):
            raise ValueError("Informe uma matrícula de sete dígitos.")
        name = self._request("GET", "/getpolicialrelatorio", params={"st_matricula_efetivo": digits}).text.strip()
        if not name or "<" in name or expected_name.casefold() not in name.casefold():
            raise RuntimeError("Matrícula não confirmou o nome esperado no SISDO.")
        return name

    def prepare_create(self, fields: dict[str, Any]) -> tuple[Form, dict[str, Any]]:
        html = self.page()
        form = _form(html, "/sisdo/op/criar")
        if set(form.controls) != CREATE_FIELDS | {"_token"} or not form.values.get("_token"):
            raise RuntimeError("Contrato do formulário de criação mudou.")
        if set(fields) != CREATE_FIELDS:
            raise ValueError("O JSON deve conter exatamente os campos do formulário de criação.")
        for name, control in form.controls.items():
            if name == "_token":
                continue
            value = fields[name]
            if "required" in control and not str(value):
                raise ValueError(f"Campo obrigatório: {name}")
            if name in form.options:
                values = value if isinstance(value, list) else [value]
                if not values or any(v not in dict(form.options[name]) for v in values):
                    raise ValueError(f"Seleção inválida: {name}")
            if control.get("type") == "number":
                if not str(value).isdigit() or int(value) < int(control.get("min", 0)) or int(value) > int(control.get("max", 10000)):
                    raise ValueError(f"Quantidade inválida: {name}")
            if control.get("type") in ("date", "time") and value:
                fmt = "%Y-%m-%d" if control["type"] == "date" else "%H:%M"
                if datetime.strptime(str(value), fmt).strftime(fmt) != value:
                    raise ValueError(f"Formato inválido: {name}")
            if "maxlength" in control and len(str(value)) > int(control["maxlength"]):
                raise ValueError(f"Campo excede limite: {name}")
        start = datetime.fromisoformat(f"{fields['dt_inicio']}T{fields['hr_inicio']}")
        end = datetime.fromisoformat(f"{fields['dt_termino']}T{fields['hr_termino']}")
        if start >= end:
            raise ValueError("Término deve ser posterior ao início.")
        if fields["dt_liberacao"] or fields["hr_liberacao"]:
            raise ValueError("Este comando cria OS digitada com publicação manual.")
        if int(fields["nu_graduados"]) + int(fields["nu_motoristas"]) > int(fields["nu_efetivo"]):
            raise ValueError("Vagas reservadas excedem o efetivo.")
        units = next((f.options["cod_unidade_filtro"] for f in _Forms(html).forms if "cod_unidade_filtro" in f.options), [])
        if len([u for u in units if u[0]]) != 1:
            raise RuntimeError("Unidade de lançamento não pôde ser determinada sem ambiguidade.")
        for status in STATUSES:
            orders = parse_orders(html) if status == "digitadas" else self.list_orders(status)
            for order in orders:
                display_start = start.strftime("%d/%m/%Y %H:%M")
                if (order["dados"].get("Data Início") == display_start
                        and order["dados"].get("Cidade") == fields["st_cidade"]
                        and _operation_kind(order["dados"].get("Tipo Operação", "")) == _operation_kind(fields["st_tipooperacao"])):
                    raise RuntimeError(f"Já existe OS correspondente: {order['numero']} ({status}); nenhuma alteração feita.")
        return form, {"unidade_lancamento": next(label for value, label in units if value), "campos": fields}

    def create(self, fields: dict[str, Any]) -> dict[str, Any]:
        form, prepared = self.prepare_create(fields)
        before = {o["id"] for o in self.list_orders()}
        self._request("POST", form.action, data={**fields, "_token": form.values["_token"]})
        after = self.list_orders()
        matches = [o for o in after if o["id"] not in before and all(o["campos"].get(k) == str(v)
                   for k, v in fields.items() if k not in ("nu_efetivo", "cod_unidademarcacao[]"))]
        if len(matches) != 1:
            raise RuntimeError("Criação enviada, mas a nova OS não foi confirmada; consulte antes de repetir.")
        order = matches[0]
        if (order["unidade_lancamento"] != prepared["unidade_lancamento"]
                or order["militares"] or order["dados"].get("Qtd de Vagas") != str(fields["nu_efetivo"])
                or order["campos"].get("cod_unidademarcacao[]") != fields["cod_unidademarcacao[]"]):
            raise RuntimeError(f"OS {order['numero']} criada, porém com dados inesperados; confira antes de prosseguir.")
        return order

    def insert(self, op: int, numero: str, matricula: str, expected_name: str,
               *, executar: bool = False, funcao: str | None = None) -> dict[str, Any]:
        """Insert by matrícula only after checking both internal and printed IDs."""
        html = self.page()
        order = next((o for o in parse_orders(html) if o["id"] == op and o["numero"] == numero), None)
        if not order or order["dados"].get("Status") != "Digitado":
            raise RuntimeError("ID/número não correspondem a uma OS digitada visível.")
        digits = matricula_digits(matricula)
        if any(matricula_digits(m["matricula"]) == digits for m in order["militares"]):
            raise RuntimeError("Matrícula já está na OS; nenhuma inclusão enviada.")
        vacancies = int(order["dados"]["Qtd de Vagas"])
        if vacancies < 1:
            raise RuntimeError("OS sem vagas disponíveis.")
        path = f"/sisdo/{op}/op/inserirefetivo"
        form = _form(html, path)
        matricula_field, name_field = f"st_matricula_efetivo{op}", f"st_policial_efetivo{op}"
        if set(form.controls) != {matricula_field, name_field, "_token"} or not form.values.get("_token"):
            raise RuntimeError("Contrato de inclusão de efetivo mudou.")
        if funcao is not None and funcao not in ("Motorista", order["dados"]["Tipo Operação"], "CMTE da OS", "CMTE da GU"):
            raise ValueError("Função de efetivo inválida para esta OS.")
        name = self.lookup(digits, expected_name)
        if not executar:
            return {"id": op, "numero": numero, "matricula": digits, "nome": name,
                    "funcao": funcao, "vagas_disponiveis": vacancies}
        self._request("POST", form.action, data={"_token": form.values["_token"],
                      matricula_field: digits, name_field: name})
        after_html = self.page()
        after = next((o for o in parse_orders(after_html) if o["id"] == op and o["numero"] == numero), None)
        members = [m for m in (after or {}).get("militares", []) if matricula_digits(m["matricula"]) == digits]
        if (not after or len(members) != 1 or expected_name.casefold() not in members[0]["nome"].casefold()
                or after["campos"] != order["campos"]
                or any(m not in after["militares"] for m in order["militares"])
                or len(after["militares"]) != len(order["militares"]) + 1
                or int(after["dados"]["Qtd de Vagas"]) != vacancies - 1):
            raise RuntimeError("Inclusão enviada, mas o resultado não foi confirmado; consulte antes de repetir.")
        member = members[0]
        if funcao and not member["nome"].endswith(f"({funcao})"):
            return self.set_function(op, numero, matricula, expected_name, funcao, executar=True)
        return after

    def set_function(self, op: int, numero: str, matricula: str, expected_name: str,
                     funcao: str, *, executar: bool = False) -> dict[str, Any]:
        html = self.page()
        order = next((o for o in parse_orders(html) if o["id"] == op and o["numero"] == numero), None)
        if not order or order["dados"].get("Status") != "Digitado":
            raise RuntimeError("ID/número não correspondem a uma OS digitada visível.")
        digits = matricula_digits(matricula)
        members = [m for m in order["militares"] if matricula_digits(m["matricula"]) == digits]
        if len(members) != 1 or expected_name.casefold() not in members[0]["nome"].casefold():
            raise RuntimeError("Militar não identificado sem ambiguidade na OS.")
        member = members[0]
        record = member.get("registro_id")
        if record is None:
            raise RuntimeError("Registro de função não identificado.")
        form = _form(html, f"/sisdo/{op}/op/{record}/efetivo/funcao")
        if (set(form.controls) != {"st_funcao", "_token"}
                or funcao not in dict(form.options.get("st_funcao", [])) or not form.values.get("_token")):
            raise RuntimeError("Função não disponível ou contrato do formulário mudou.")
        if not executar:
            return {"id": op, "numero": numero, "matricula": digits, "nome": member["nome"], "funcao": funcao}
        if member["nome"].endswith(f"({funcao})"):
            return order
        self._request("POST", form.action, data={"_token": form.values["_token"], "st_funcao": funcao})
        final = next((o for o in self.list_orders() if o["id"] == op and o["numero"] == numero), None)
        final_member = next((m for m in (final or {}).get("militares", []) if matricula_digits(m["matricula"]) == digits), None)
        if not final_member or not final_member["nome"].endswith(f"({funcao})"):
            raise RuntimeError("Alteração de função enviada, mas não confirmada; consulte antes de repetir.")
        others = [m for m in order["militares"] if m is not member]
        if (final["campos"] != order["campos"] or final["dados"] != order["dados"]
                or len(final["militares"]) != len(order["militares"])
                or any(m not in final["militares"] for m in others)):
            raise RuntimeError("Dados inesperados após alterar função; confira a OS.")
        return final

    def _digitada(self, html: str, op: int, numero: str) -> dict[str, Any]:
        order = next((o for o in parse_orders(html) if o["id"] == op and o["numero"] == numero), None)
        if not order or order["dados"].get("Status") != "Digitado":
            raise RuntimeError("ID/número não correspondem a uma OS digitada visível.")
        return order

    def print_pdf(self, op: int, numero: str, *, status: str = "digitadas") -> bytes:
        html = self.page(status)
        if not any(o["id"] == op and o["numero"] == numero for o in parse_orders(html)):
            raise RuntimeError("OS não identificada nesta listagem.")
        path = f"/sisdo/{op}/op/impressao"
        links = [unescape(url) for url in re.findall(r'<a\b[^>]*href="([^"]+)"', html)
                 if urlsplit(unescape(url)).path == path]
        if len(links) != 1:
            raise RuntimeError("Link de impressão não identificado sem ambiguidade.")
        response = self._request("GET", links[0])
        if not response.content.startswith(b"%PDF-") or response.headers.get("content-type", "").split(";", 1)[0] != "application/pdf":
            raise RuntimeError("Impressão não devolveu PDF válido.")
        return response.content

    def remove(self, op: int, numero: str, matricula: str, expected_name: str,
               justificativa: str, *, executar: bool = False) -> dict[str, Any]:
        html = self.page()
        order = self._digitada(html, op, numero)
        digits = matricula_digits(matricula)
        members = [m for m in order["militares"] if matricula_digits(m["matricula"]) == digits]
        if len(members) != 1 or expected_name.casefold() not in members[0]["nome"].casefold():
            raise RuntimeError("Militar não identificado sem ambiguidade na OS.")
        record = members[0].get("registro_id")
        if record is None:
            raise RuntimeError("Registro de efetivo não identificado.")
        form = _form(html, f"/sisdo/{op}/op/{record}/efetivo/excluir")
        if set(form.controls) != {"justificativa", "_token"} or not form.values.get("_token"):
            raise RuntimeError("Contrato de remoção mudou.")
        if not justificativa.strip() or len(justificativa) > int(form.controls["justificativa"].get("maxlength", 1000)):
            raise ValueError("Informe uma justificativa não vazia, dentro do limite do formulário.")
        if not executar:
            return {"id": op, "numero": numero, "matricula": digits, "nome": members[0]["nome"],
                    "registro_id": record, "justificativa": justificativa, "rota": urlsplit(form.action).path}
        self._request("POST", form.action, data={"_token": form.values["_token"], "justificativa": justificativa})
        after = self._digitada(self.page(), op, numero)
        others = [m for m in order["militares"] if m is not members[0]]
        if (after["campos"] != order["campos"] or after["militares"] != others
                or any(matricula_digits(m["matricula"]) == digits for m in after["militares"])
                or int(after["dados"]["Qtd de Vagas"]) != len(after["vagas_vazias"])
                or len(after["vagas_vazias"]) not in (len(order["vagas_vazias"]), len(order["vagas_vazias"]) + 1)):
            raise RuntimeError("Remoção enviada, mas não confirmada; consulte antes de repetir.")
        return after

    def add_vacancies(self, op: int, numero: str, count: int, *, executar: bool = False) -> dict[str, Any]:
        html = self.page()
        order = self._digitada(html, op, numero)
        form = _form(html, f"/sisdo/{op}/op/maisvagas")
        name = f"st_vagas{op}"
        if set(form.controls) != {name, "_token"} or not form.values.get("_token"):
            raise RuntimeError("Contrato de acréscimo de vagas mudou.")
        control = form.controls[name]
        if count < int(control.get("min", 1)) or count > int(control.get("max", 100)):
            raise ValueError("Acréscimo fora do limite do formulário.")
        if not executar:
            return {"id": op, "numero": numero, "acrescentar": count}
        self._request("POST", form.action, data={"_token": form.values["_token"], name: str(count)})
        after = self._digitada(self.page(), op, numero)
        if (after["campos"] != order["campos"] or after["militares"] != order["militares"]
                or int(after["dados"]["Qtd de Vagas"]) != int(order["dados"]["Qtd de Vagas"]) + count
                or len(after["vagas_vazias"]) != len(order["vagas_vazias"]) + count):
            raise RuntimeError("Acréscimo enviado, mas não confirmado; consulte antes de repetir.")
        return after

    def reduce_vacancies(self, op: int, numero: str, total: int, *, executar: bool = False) -> dict[str, Any]:
        order = self._digitada(self.page(), op, numero)
        if int(order["dados"]["Qtd de Vagas"]) != len(order["vagas_vazias"]):
            raise RuntimeError("Quantidade de vagas vazias diverge da listagem; redução interrompida.")
        if any(int(order["campos"].get(k, 0)) for k in ("nu_graduados", "nu_motoristas")):
            raise RuntimeError("Redução com vagas reservadas requer análise da categoria de cada vaga.")
        occupied = len(order["militares"])
        current = occupied + len(order["vagas_vazias"])
        if total < max(1, occupied) or total > current:
            raise ValueError("Total deve preservar os militares ocupantes e ser de pelo menos uma vaga.")
        if not executar:
            return {"id": op, "numero": numero, "total_atual": current, "total_desejado": total,
                    "remover_vagas_vazias": current - total}
        while current > total:
            # Read again before each mutating GET: yesterday's empty slot may be occupied now.
            fresh = self._digitada(self.page(), op, numero)
            if fresh != order or not fresh["vagas_vazias"]:
                raise RuntimeError("OS mudou durante redução; confira antes de continuar.")
            slot = fresh["vagas_vazias"][-1]
            self._request("GET", slot["url"], headers={"Referer": BASE_URL + "/sisdo/op/listar/digitadas"})
            after = self._digitada(self.page(), op, numero)
            expected_slots = fresh["vagas_vazias"][:-1]
            if (after["campos"] != fresh["campos"] or after["militares"] != fresh["militares"]
                    or after["vagas_vazias"] != expected_slots
                    or int(after["dados"]["Qtd de Vagas"]) != len(expected_slots)):
                raise RuntimeError("Exclusão de vaga enviada, mas não confirmada; consulte antes de repetir.")
            order = after
            current -= 1
        return order
