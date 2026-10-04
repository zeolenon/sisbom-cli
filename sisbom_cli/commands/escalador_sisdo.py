"""One-shot preview/apply command; usable by an ordinary server-side job."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

import click

from ..escalador_sisdo import apply, bind, check, fingerprint, query_plan, read_orders
from ..sisdo import SISDOClient


def save_state(path: Path, state: dict) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        json.dump(state, output, ensure_ascii=False, indent=2)
    temporary.chmod(0o600)
    temporary.replace(path)


@click.command("escala")
@click.option("--data", required=True, help="Data de início, YYYY-MM-DD, no fuso de Fortaleza.")
@click.option("--modelo", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--estado", type=click.Path(dir_okay=False, path_type=Path), required=True, help="Registro privado de vínculos com OSs.")
@click.option("--consulta-script", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=Path.home() / ".hermes/profiles/minimaxm3/skills/escalador-3bbm-consultas/scripts/consultar.py")
@click.option("--vincular-os", multiple=True, help="Vincular explicitamente OS existente: ID:NUMERO.")
@click.option("--esperar-hash", help="Recusar execução se a escala mudou desde a prévia.")
@click.option("--esperar-conferencia", help="Recusar execução se o estado SISDO/diferenças mudou desde a prévia.")
@click.option("--justificativa", default="", help="Obrigatória se a correção retirar militares.")
@click.option("--executar", is_flag=True, help="Aplicar inclusões/retiradas e ajustar vagas; padrão apenas confere.")
def escala_cmd(data: str, modelo: Path, estado: Path, consulta_script: Path, vincular_os: tuple[str, ...],
               esperar_hash: str | None, esperar_conferencia: str | None, justificativa: str, executar: bool) -> None:
    """Transportar/conferir diárias do Escalador em OSs digitadas do SISDO."""
    locked = False
    lock = Path(str(estado) + ".lock")
    try:
        model = json.loads(modelo.read_text())
        estado.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError("Já existe uma execução ou um lock pendente para este estado; confira o processo antes de repetir.") from None
        with os.fdopen(descriptor, "w") as output:
            output.write(str(os.getpid()))
        locked = True
        state = json.loads(estado.read_text()) if estado.exists() else {
            "schema_version": "1.0", "data": data, "quartel_id": model["quartel_id"],
            "hash_modelo": fingerprint(model), "vinculos": {}}
        if (state.get("schema_version") != "1.0" or state.get("data") != data
                or state.get("quartel_id") != model["quartel_id"] or state.get("hash_modelo") != fingerprint(model)):
            raise ValueError("Estado pertence a outra data, quartel ou modelo.")
        plan = query_plan(consulta_script, data, model)
        if esperar_hash and esperar_hash != plan["hash_escala"]:
            raise ValueError("Escala mudou desde a prévia; confira novamente.")
        with SISDOClient() as client:
            orders = read_orders(client)
            for item in vincular_os:
                parts = item.split(":")
                if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                    raise ValueError("Vínculo deve usar ID:NUMERO.")
                bind(plan, state, orders, int(parts[0]), parts[1])
            if vincular_os:
                save_state(estado, state)
            report = check(plan, state, orders)
            if esperar_conferencia and esperar_conferencia != report["hash_conferencia"]:
                raise ValueError("SISDO ou diferenças mudaram desde a prévia; confira novamente.")
            if executar:
                fresh = query_plan(consulta_script, data, model)
                if fresh["hash_escala"] != plan["hash_escala"]:
                    raise RuntimeError("Escala mudou durante a conferência; nenhuma correção enviada.")
                report = apply(client, fresh, state, report, justificativa, lambda value: save_state(estado, value))
                latest = query_plan(consulta_script, data, model)
                if latest["hash_escala"] != fresh["hash_escala"]:
                    # Report the new differences without silently applying another correction.
                    plan = latest
                    report = check(latest, state, read_orders(client))
        output = {"executado": executar, "estado_escala": plan["estado_escala"], "fonte_gerada_em": plan["fonte_gerada_em"],
                  "conferencia": report}
        click.echo(json.dumps(output, ensure_ascii=False, indent=2))
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        raise click.ClickException(str(exc)) from None
    finally:
        if locked:
            lock.unlink()
