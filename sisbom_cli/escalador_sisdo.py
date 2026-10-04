"""Deterministic Escalador → SISDO planning and roster reconciliation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .sisdo import CREATE_FIELDS, SISDOClient, STATUSES, matricula_digits

TZ = ZoneInfo("America/Fortaleza")
GENERATED_FIELDS = {"dt_inicio", "hr_inicio", "dt_termino", "hr_termino", "dt_apresentacao", "nu_efetivo", "nu_diarias", "st_tipooperacao"}


def fingerprint(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def group_key(fields: dict[str, Any]) -> str:
    return fingerprint({k: v for k, v in fields.items() if k != "nu_efetivo"})[:24]


def build_plan(data: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema_version") != "1.0" or data.get("timezone") != "America/Fortaleza":
        raise ValueError("Contrato/fuso do Escalador não reconhecido.")
    template = model["campos"]
    if set(template) != CREATE_FIELDS - GENERATED_FIELDS:
        raise ValueError("Modelo deve conter exatamente os campos comuns de criação.")
    if any(template[k] != "" for k in ("dt_liberacao", "hr_liberacao")):
        raise ValueError("A integração mantém publicação manual.")
    if any(int(template[k]) != 0 for k in ("nu_graduados", "nu_motoristas")):
        raise ValueError("Reconciliação automática está limitada a modelos sem vagas reservadas.")
    records = [g for g in data.get("guarnicoes", []) if g.get("data_servico") == data["data"] and g.get("quartel_id") == model["quartel_id"]]
    if len(records) != 1:
        raise ValueError("Guarnição da data/quartel não identificada sem ambiguidade.")
    record = records[0]
    if record.get("revisao_necessaria") or record.get("conflitos"):
        raise ValueError("Escalador indica revisão ou conflitos; resolva antes de transportar a escala.")
    services = [s for group in record.get("grupos", []) for function in group.get("funcoes", []) for s in function.get("servicos", [])]
    services += record.get("sem_funcao", [])
    unique: dict[str, dict[str, Any]] = {}
    for service in services:
        if service.get("tipo") != "diaria" or service.get("data") != data["data"] or service.get("quartel_id") != model["quartel_id"]:
            continue
        if service.get("vigente_na_agenda") is not True:
            continue
        sid = service["id"]
        if sid in unique and unique[sid] != service:
            raise ValueError("Serviço duplicado com dados conflitantes.")
        unique[sid] = service
    groups: dict[str, dict[str, Any]] = {}
    source_ids = []
    rules = {k.casefold(): v for k, v in model["tipos_diaria"].items()}
    for service in unique.values():
        military = service["militar"]
        mat = matricula_digits(military.get("matricula") or "")
        name = military.get("nome_guerra")
        if len(mat) != 7 or not name:
            raise ValueError("Serviço sem matrícula ou nome de guerra confirmado.")
        rule = rules.get((service.get("tipo_diaria") or "").casefold())
        if not rule:
            raise ValueError(f"Tipo de diária sem regra explícita no modelo: {service.get('tipo_diaria')}")
        start, end = (datetime.fromisoformat(service[k].replace("Z", "+00:00")) for k in ("inicio", "fim"))
        if not start.tzinfo or not end.tzinfo or end <= start:
            raise ValueError("Serviço sem período válido com fuso.")
        start, end = start.astimezone(TZ), end.astimezone(TZ)
        if start.strftime("%Y-%m-%d") != data["data"] or start.second or end.second:
            raise ValueError("Início do serviço diverge da data ou tem precisão não suportada.")
        quantity = service.get("quantidade_do")
        if not isinstance(quantity, int) or not 1 <= quantity <= 4:
            raise ValueError("Quantidade de DO não suportada pelo formulário SISDO.")
        fields = {**template, "dt_inicio": start.strftime("%Y-%m-%d"), "hr_inicio": start.strftime("%H:%M"),
                  "dt_termino": end.strftime("%Y-%m-%d"), "hr_termino": end.strftime("%H:%M"),
                  "dt_apresentacao": start.strftime("%H:%M"), "nu_diarias": str(quantity),
                  "st_tipooperacao": rule["tipo_os"]}
        key = group_key(fields)
        group = groups.setdefault(key, {"chave": key, "campos": fields, "militares": []})
        if any(m["matricula"] == mat for m in group["militares"]):
            raise ValueError("Militar possui duas diárias na mesma OS; confira a origem.")
        group["militares"].append({"id_escalador": military["id"], "matricula": mat, "nome": name,
                                  "funcao": rule.get("funcao") or rule["tipo_os"]})
        source_ids.append(service["id"])
    result = sorted(groups.values(), key=lambda g: (g["campos"]["hr_inicio"], g["campos"]["st_tipooperacao"]))
    for group in result:
        group["militares"].sort(key=lambda m: m["matricula"])
        group["campos"]["nu_efetivo"] = str(len(group["militares"]))
    return {"data": data["data"], "quartel_id": model["quartel_id"], "unidade_lancamento": model["unidade_lancamento"],
            "fonte_gerada_em": data.get("gerado_em"), "estado_escala": record.get("estado"),
            "hash_escala": fingerprint(result), "grupos": result, "ids_servicos": sorted(source_ids)}


def query_plan(script: Path, date: str, model: dict[str, Any]) -> dict[str, Any]:
    datetime.strptime(date, "%Y-%m-%d")
    spec = importlib.util.spec_from_file_location("escalador_consultas_sisdo", script)
    if not spec or not spec.loader:
        raise ValueError("Cliente de consultas do Hermes não encontrado.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    params = {"data": date, "instante": date + "T07:00:00-03:00", "quartel_id": model["quartel_id"]}
    try:
        # The existing client consults /capacidades before every API execution.
        data = module.consultar("guarnicoes", params)
        general = module.consultar("servico", params)
    except module.FalhaConsulta as exc:
        raise RuntimeError(str(exc)) from None
    plan = build_plan(data, model)
    general_ids = sorted(s["id"] for s in general.get("servicos", []) if s.get("tipo") == "diaria"
                         and s.get("data") == date and s.get("quartel_id") == model["quartel_id"])
    if general_ids != plan["ids_servicos"]:
        raise RuntimeError("Listagem geral e guarnições divergem sobre as diárias; transporte interrompido.")
    return plan


def read_orders(client: SISDOClient) -> list[dict[str, Any]]:
    return [{**order, "situacao": status} for status in STATUSES for order in client.list_orders(status)]


def identify(fields: dict[str, Any], order: dict[str, Any]) -> bool:
    start = datetime.fromisoformat(fields["dt_inicio"] + "T" + fields["hr_inicio"]).strftime("%d/%m/%Y %H:%M")
    end = datetime.fromisoformat(fields["dt_termino"] + "T" + fields["hr_termino"]).strftime("%d/%m/%Y %H:%M")
    d = order["dados"]
    return (d.get("Data Início") == start and d.get("Data Término") == end
            and d.get("Cidade") == fields["st_cidade"] and d.get("Tipo Operação") == fields["st_tipooperacao"])


def check(plan: dict[str, Any], state: dict[str, Any], orders: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {g["chave"]: g for g in plan["grupos"]}
    # A disappeared group represents removal of its final soldier, not deletion of the OS.
    for key, binding in state["vinculos"].items():
        groups.setdefault(key, {"chave": key, "campos": binding["campos"], "militares": []})
    diffs, blocks = [], []
    for key, group in groups.items():
        fields = group["campos"]
        binding = state["vinculos"].get(key)
        if not binding:
            candidates = [o for o in orders if identify(fields, o)]
            if candidates:
                blocks.append(f"OS existente sem vínculo explícito para {fields['st_tipooperacao']}: " + ", ".join(o["numero"] for o in candidates))
                continue
            diffs.append({"chave": key, "acao": "criar", "campos": fields, "incluir": group["militares"], "remover": [], "funcoes": []})
            continue
        matches = [o for o in orders if o["id"] == binding["id"] and o["numero"] == binding["numero"]]
        if len(matches) != 1:
            blocks.append(f"OS vinculada não encontrada sem ambiguidade: {binding['numero']}")
            continue
        order = matches[0]
        mismatches = [k for k, v in fields.items() if k != "nu_efetivo" and order["campos"].get(k) != v]
        if order["situacao"] != "digitadas" or mismatches or order["unidade_lancamento"] != plan["unidade_lancamento"]:
            blocks.append(f"OS {order['numero']} fora do modelo ou não digitada: " + ", ".join(mismatches))
            continue
        if int(order["dados"]["Qtd de Vagas"]) != len(order["vagas_vazias"]):
            blocks.append(f"OS {order['numero']} tem contagem de vagas divergente.")
            continue
        current = {matricula_digits(m["matricula"]): m for m in order["militares"]}
        wanted = {m["matricula"]: m for m in group["militares"]}
        removals = [{"matricula": mat, "nome": m["nome"].rsplit(" (", 1)[0]} for mat, m in current.items() if mat not in wanted]
        additions = [m for mat, m in wanted.items() if mat not in current]
        functions = [m for mat, m in wanted.items() if mat in current and not current[mat]["nome"].endswith(f"({m['funcao']})")]
        # Preserve an empty digitada with one free slot instead of silently cancelling it.
        desired_total = max(1, len(wanted))
        total_now = len(current) + len(order["vagas_vazias"])
        diffs.append({"chave": key, "acao": "conferir", "id": order["id"], "numero": order["numero"],
                      "campos": fields, "incluir": additions, "remover": removals, "funcoes": functions,
                      "total_atual": total_now, "total_desejado": desired_total,
                      "militares_desejados": group["militares"], "snapshot": fingerprint(order)})
    changed = any(d["acao"] == "criar" or d["incluir"] or d["remover"] or d["funcoes"]
                  or d.get("total_atual") != d.get("total_desejado") for d in diffs)
    report = {"data": plan["data"], "quartel_id": plan["quartel_id"], "hash_escala": plan["hash_escala"],
              "alteracoes": bool(changed), "bloqueios": blocks, "ordens": diffs}
    report["hash_conferencia"] = fingerprint(report)
    return report


def bind(plan: dict[str, Any], state: dict[str, Any], orders: list[dict[str, Any]], op: int, numero: str) -> None:
    order = next((o for o in orders if o["id"] == op and o["numero"] == numero), None)
    if not order or order["unidade_lancamento"] != plan["unidade_lancamento"]:
        raise ValueError("OS indicada para vínculo não pertence ao acesso/modelo esperado.")
    groups = [g for g in plan["grupos"] if identify(g["campos"], order)]
    if len(groups) != 1:
        raise ValueError("OS não corresponde a um único grupo da escala.")
    group = groups[0]
    old = state["vinculos"].get(group["chave"])
    if old and (old["id"] != op or old["numero"] != numero):
        raise ValueError("Grupo já está vinculado a outra OS.")
    state["vinculos"][group["chave"]] = {"id": op, "numero": numero, "campos": group["campos"]}


def apply(client: SISDOClient, plan: dict[str, Any], state: dict[str, Any], report: dict[str, Any],
          justificativa: str, save: Any) -> dict[str, Any]:
    if report["bloqueios"]:
        raise RuntimeError("Há bloqueios na conferência; nenhuma correção enviada.")
    if any(d["remover"] for d in report["ordens"]) and not justificativa.strip():
        raise ValueError("Correções com retirada exigem justificativa explícita.")
    # Validate every matrícula that will be added before the first mutation.
    for diff in report["ordens"]:
        if diff["acao"] == "criar":
            prepared = client.prepare_create(diff["campos"])[1]
            if prepared["unidade_lancamento"] != plan["unidade_lancamento"]:
                raise RuntimeError("Acesso SISDO usa outra unidade; nenhuma criação enviada.")
        for military in diff["incluir"]:
            client.lookup(military["matricula"], military["nome"])
    for diff in report["ordens"]:
        key = diff["chave"]
        if diff["acao"] == "criar":
            order = client.create(diff["campos"])
            if order["unidade_lancamento"] != plan["unidade_lancamento"]:
                raise RuntimeError("Nova OS tem unidade inesperada; confira antes de continuar.")
            state["vinculos"][key] = {"id": order["id"], "numero": order["numero"], "campos": diff["campos"]}
            save(state)  # Store the OS identity before any personnel insertion.
        else:
            order = next((o for o in read_orders(client) if o["id"] == diff["id"] and o["numero"] == diff["numero"]), None)
            if not order or fingerprint(order) != diff["snapshot"]:
                raise RuntimeError("OS mudou após a prévia; refaça a conferência.")
        op, number = order["id"], order["numero"]
        for military in diff["remover"]:
            client.remove(op, number, military["matricula"], military["nome"], justificativa, executar=True)
        order = next(o for o in client.list_orders() if o["id"] == op and o["numero"] == number)
        missing_slots = len(diff["incluir"]) - int(order["dados"]["Qtd de Vagas"])
        if missing_slots > 0:
            client.add_vacancies(op, number, missing_slots, executar=True)
        for military in diff["incluir"]:
            client.insert(op, number, military["matricula"], military["nome"], funcao=military["funcao"], executar=True)
        for military in diff["funcoes"]:
            client.set_function(op, number, military["matricula"], military["nome"], military["funcao"], executar=True)
        target = max(1, len(diff.get("militares_desejados", diff["incluir"])))
        client.reduce_vacancies(op, number, target, executar=True)
        state["vinculos"][key]["campos"] = diff["campos"]
        save(state)
    final = check(plan, state, read_orders(client))
    if final["bloqueios"] or final["alteracoes"]:
        raise RuntimeError("Conferência final ainda mostra diferenças; consulte o estado antes de continuar.")
    state["ultima_escala_aplicada"] = plan["hash_escala"]
    save(state)
    return final
