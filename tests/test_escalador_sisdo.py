"""Synthetic schedules: grouping, swaps, additions and reconciliation."""

from __future__ import annotations

from copy import deepcopy
import unittest

from sisbom_cli.escalador_sisdo import apply, build_plan, check


MODEL = {
    "quartel_id": "apodi", "unidade_lancamento": "UNIDADE TESTE",
    "campos": {"st_cidade": "Apodi", "st_local": "LOCAL TESTE", "st_localapresentacao": "LOCAL TESTE",
               "st_responsavel": "RESPONSAVEL TESTE", "cod_unidademarcacao[]": ["[1]"], "dt_liberacao": "",
               "hr_liberacao": "", "nu_graduados": "0", "nu_motoristas": "0", "st_obs": ""},
    "tipos_diaria": {"Operacional": {"tipo_os": "Reforço de Guarnição"},
                     "Motorista": {"tipo_os": "Reforço de Guarnição", "funcao": "Motorista"},
                     "AMA 18h": {"tipo_os": "Operação AMA"}, "Verão": {"tipo_os": "Operação Verão"}}
}


def service(n: int, kind: str = "Operacional", hour: int = 10, quantity: int = 4) -> dict:
    return {"id": f"servico-{n}", "data": "2026-10-30", "quartel_id": "apodi", "tipo": "diaria",
            "vigente_na_agenda": True, "tipo_diaria": kind, "quantidade_do": quantity,
            "inicio": f"2026-10-30T{hour:02}:00:00.000Z", "fim": "2026-10-31T10:00:00.000Z",
            "militar": {"id": f"militar-{n}", "matricula": str(n) * 7, "nome_guerra": f"TESTE{n}"}}


def schedule(services: list[dict]) -> dict:
    return {"schema_version": "1.0", "timezone": "America/Fortaleza", "data": "2026-10-30", "guarnicoes": [{
        "data_servico": "2026-10-30", "quartel_id": "apodi", "estado": "sugestao", "revisao_necessaria": False,
        "conflitos": [], "sem_funcao": [], "grupos": [{"funcoes": [{"em_servico_previsto": False, "servicos": services}]}]}]}


def order(group: dict) -> dict:
    f = group["campos"]
    return {"id": 99, "numero": "123", "unidade_lancamento": "UNIDADE TESTE", "situacao": "digitadas",
            "campos": {k: v for k, v in f.items() if k != "nu_efetivo"},
            "dados": {"Data Início": "30/10/2026 07:00", "Data Término": "31/10/2026 07:00", "Cidade": "Apodi",
                      "Tipo Operação": "Reforço de Guarnição", "Qtd de Vagas": "0", "Status": "Digitado"},
            "militares": [{"matricula": m["matricula"], "nome": m["nome"] + " (" + m["funcao"] + ")",
                            "posto": "SD", "registro_id": i + 500} for i, m in enumerate(group["militares"])], "vagas_vazias": []}


def state(group: dict) -> dict:
    return {"vinculos": {group["chave"]: {"id": 99, "numero": "123", "campos": group["campos"]}}}


class FakeSISDO:
    def __init__(self, current: dict, preserve_slot: bool = True) -> None:
        self.current = deepcopy(current)
        self.preserve_slot = preserve_slot
        self.calls = []

    def list_orders(self, status: str = "digitadas") -> list[dict]:
        return [deepcopy(self.current)] if status == "digitadas" else []

    def lookup(self, mat: str, name: str) -> str:
        return name

    def _vacancies(self, count: int) -> None:
        self.current["vagas_vazias"] = [{"id": 800 + i, "url": f"https://sisdo.cbm.rn.gov.br/sisdo/99/op/{800+i}/vaga/excluir"} for i in range(count)]
        self.current["dados"]["Qtd de Vagas"] = str(count)

    def remove(self, op: int, number: str, mat: str, name: str, reason: str, **kwargs) -> None:
        self.calls.append(("remove", mat))
        self.current["militares"] = [m for m in self.current["militares"] if m["matricula"] != mat]
        if self.preserve_slot:
            self._vacancies(len(self.current["vagas_vazias"]) + 1)

    def add_vacancies(self, op: int, number: str, count: int, **kwargs) -> None:
        self.calls.append(("add_vacancies", count))
        self._vacancies(len(self.current["vagas_vazias"]) + count)

    def insert(self, op: int, number: str, mat: str, name: str, *, funcao: str, **kwargs) -> None:
        self.calls.append(("insert", mat))
        self._vacancies(len(self.current["vagas_vazias"]) - 1)
        self.current["militares"].append({"matricula": mat, "nome": name + " (" + funcao + ")", "posto": "SD", "registro_id": 900})

    def reduce_vacancies(self, op: int, number: str, total: int, **kwargs) -> None:
        self.calls.append(("reduce", total))
        self._vacancies(total - len(self.current["militares"]))


class EscaladorSISDOTests(unittest.TestCase):
    def test_three_operations_and_future_ama_are_grouped_correctly(self) -> None:
        plan = build_plan(schedule([service(1, "Motorista"), service(2), service(3, "AMA 18h", 16, 3), service(4, "Verão")]), MODEL)
        groups = {g["campos"]["st_tipooperacao"]: g for g in plan["grupos"]}
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups["Reforço de Guarnição"]["campos"]["nu_efetivo"], "2")
        self.assertEqual(groups["Operação AMA"]["campos"]["hr_inicio"], "13:00")
        self.assertEqual(groups["Operação AMA"]["campos"]["nu_diarias"], "3")

    def test_ordinary_previous_day_and_duplicate_position_do_not_add_people(self) -> None:
        ordinary, yesterday = service(2), service(3)
        ordinary["tipo"] = "ordinario"
        yesterday["data"] = "2026-10-29"
        plan = build_plan(schedule([service(1), service(1), ordinary, yesterday]), MODEL)
        self.assertEqual(len(plan["grupos"][0]["militares"]), 1)

    def test_unknown_type_is_not_silently_a_reinforcement(self) -> None:
        with self.assertRaisesRegex(ValueError, "regra explícita"):
            build_plan(schedule([service(1, "DESCONHECIDO")]), MODEL)

    def test_swap_is_one_removal_and_one_addition_without_structural_edits(self) -> None:
        before = build_plan(schedule([service(1), service(2)]), MODEL)
        after = build_plan(schedule([service(1), service(3)]), MODEL)
        report = check(after, state(before["grupos"][0]), [order(before["grupos"][0])])
        diff = report["ordens"][0]
        self.assertEqual([m["matricula"] for m in diff["remover"]], ["2222222"])
        self.assertEqual([m["matricula"] for m in diff["incluir"]], ["3333333"])
        self.assertEqual(diff["total_atual"], diff["total_desejado"])
        self.assertFalse(report["bloqueios"])

    def test_last_minute_addition_increases_target_count(self) -> None:
        before = build_plan(schedule([service(1)]), MODEL)
        after = build_plan(schedule([service(1), service(2)]), MODEL)
        report = check(after, state(before["grupos"][0]), [order(before["grupos"][0])])
        self.assertEqual(report["ordens"][0]["total_desejado"], 2)
        self.assertEqual(len(report["ordens"][0]["incluir"]), 1)

    def test_preview_hash_detects_a_manual_sisdo_change_with_same_source(self) -> None:
        plan = build_plan(schedule([service(1)]), MODEL)
        current = order(plan["grupos"][0]); journal = state(plan["grupos"][0])
        first = check(plan, journal, [current])
        current["militares"].append({"matricula": "2222222", "nome": "TESTE2 (Reforço de Guarnição)", "posto": "SD", "registro_id": 600})
        second = check(plan, journal, [current])
        self.assertEqual(first["hash_escala"], second["hash_escala"])
        self.assertNotEqual(first["hash_conferencia"], second["hash_conferencia"])

    def test_existing_order_is_never_silently_adopted(self) -> None:
        plan = build_plan(schedule([service(1)]), MODEL)
        report = check(plan, {"vinculos": {}}, [order(plan["grupos"][0])])
        self.assertTrue(report["bloqueios"])

    def test_structural_changes_and_published_orders_block_corrections(self) -> None:
        plan = build_plan(schedule([service(1)]), MODEL)
        current = order(plan["grupos"][0])
        current["campos"]["hr_inicio"] = "08:00"
        self.assertTrue(check(plan, state(plan["grupos"][0]), [current])["bloqueios"])
        current = order(plan["grupos"][0]); current["situacao"] = "publicadas"
        self.assertTrue(check(plan, state(plan["grupos"][0]), [current])["bloqueios"])

    def test_swap_applies_once_with_both_possible_server_slot_behaviors(self) -> None:
        before = build_plan(schedule([service(1), service(2)]), MODEL)
        after = build_plan(schedule([service(1), service(3)]), MODEL)
        for preserve in (True, False):
            with self.subTest(preserve_slot=preserve):
                journal = state(before["grupos"][0])
                client = FakeSISDO(order(before["grupos"][0]), preserve)
                report = check(after, journal, client.list_orders())
                final = apply(client, after, journal, report, "Permuta autorizada de teste", lambda s: None)
                self.assertFalse(final["alteracoes"])
                self.assertEqual([call for call in client.calls if call[0] == "remove"], [("remove", "2222222")])
                self.assertEqual([call for call in client.calls if call[0] == "insert"], [("insert", "3333333")])

    def test_removal_requires_reason_before_any_mutation(self) -> None:
        before = build_plan(schedule([service(1), service(2)]), MODEL)
        after = build_plan(schedule([service(1)]), MODEL)
        journal = state(before["grupos"][0]); client = FakeSISDO(order(before["grupos"][0]))
        with self.assertRaisesRegex(ValueError, "justificativa"):
            apply(client, after, journal, check(after, journal, client.list_orders()), "", lambda s: None)
        self.assertFalse(client.calls)

    def test_last_removed_soldier_keeps_one_empty_slot_and_the_order(self) -> None:
        before = build_plan(schedule([service(1)]), MODEL)
        after = build_plan(schedule([]), MODEL)
        journal = state(before["grupos"][0]); client = FakeSISDO(order(before["grupos"][0]))
        final = apply(client, after, journal, check(after, journal, client.list_orders()), "Retirada autorizada de teste", lambda s: None)
        self.assertFalse(final["alteracoes"])
        self.assertEqual(client.current["militares"], [])
        self.assertEqual(len(client.current["vagas_vazias"]), 1)


if __name__ == "__main__":
    unittest.main()
