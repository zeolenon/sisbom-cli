"""Browserless SISDO commands."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ..sisdo import SISDOClient, STATUSES
from .escalador_sisdo import escala_cmd
from .voluntariado import register as register_voluntariado


@click.group()
def sisdo() -> None:
    """Ordens de serviço do SISDO via HTTPX e SSO do SISBOM."""


@sisdo.command("listar")
@click.option("--status", type=click.Choice(STATUSES), default="digitadas")
@click.option("--json", "as_json", is_flag=True)
def listar(status: str, as_json: bool) -> None:
    """Consultar OSs visíveis na unidade do acesso atual."""
    try:
        with SISDOClient() as client:
            orders = client.list_orders(status)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(orders, ensure_ascii=False, indent=2))
        return
    table = Table(title=f"OSs {status}")
    for label in ("ID", "Número", "Início", "Cidade", "Tipo", "Efetivo"):
        table.add_column(label)
    for o in orders:
        table.add_row(str(o["id"]), o["numero"], o["dados"].get("Data Início", ""),
                      o["dados"].get("Cidade", ""), o["dados"].get("Tipo Operação", ""), str(len(o["militares"])))
    Console().print(table)


@sisdo.command("criar")
@click.option("--arquivo", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--executar", is_flag=True, help="Enviar criação; sem esta opção, apenas validar.")
def criar(arquivo: Path, executar: bool) -> None:
    """Criar uma OS digitada com campos explícitos de um JSON."""
    try:
        fields = json.loads(arquivo.read_text())
        if not isinstance(fields, dict):
            raise ValueError("O arquivo deve conter um objeto JSON.")
        with SISDOClient() as client:
            result = client.create(fields) if executar else client.prepare_create(fields)[1]
    except (OSError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps({"executado": executar, "resultado": result}, ensure_ascii=False, indent=2))


@sisdo.command("inserir")
@click.option("--os-id", type=int, required=True, help="ID interno da OS.")
@click.option("--numero", required=True, help="Número impresso, conferido junto ao ID.")
@click.option("--matricula", required=True)
@click.option("--nome", required=True, help="Nome de guerra esperado para conferir a matrícula.")
@click.option("--funcao", help="Motorista, tipo da OS, CMTE da OS ou CMTE da GU.")
@click.option("--executar", is_flag=True, help="Enviar inclusão; sem esta opção, apenas validar.")
def inserir(os_id: int, numero: str, matricula: str, nome: str, funcao: str | None, executar: bool) -> None:
    """Inserir militar por matrícula em uma OS digitada com vaga."""
    try:
        with SISDOClient() as client:
            result = client.insert(os_id, numero, matricula, nome, executar=executar, funcao=funcao)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps({"executado": executar, "resultado": result}, ensure_ascii=False, indent=2))


@sisdo.command("funcao")
@click.option("--os-id", type=int, required=True)
@click.option("--numero", required=True)
@click.option("--matricula", required=True)
@click.option("--nome", required=True)
@click.option("--funcao", required=True)
@click.option("--executar", is_flag=True)
def funcao_cmd(os_id: int, numero: str, matricula: str, nome: str, funcao: str, executar: bool) -> None:
    """Definir uma função disponível no formulário da vaga ocupada."""
    try:
        with SISDOClient() as client:
            result = client.set_function(os_id, numero, matricula, nome, funcao, executar=executar)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps({"executado": executar, "resultado": result}, ensure_ascii=False, indent=2))


@sisdo.command("imprimir")
@click.option("--os-id", type=int, required=True)
@click.option("--numero", required=True)
@click.option("--status", type=click.Choice(STATUSES), default="digitadas")
@click.option("--destino", type=click.Path(dir_okay=False, path_type=Path), required=True)
def imprimir(os_id: int, numero: str, status: str, destino: Path) -> None:
    """Baixar o PDF oficial da OS sem abrir navegador."""
    try:
        if destino.exists():
            raise ValueError("Destino já existe; escolha outro arquivo.")
        with SISDOClient() as client:
            pdf = client.print_pdf(os_id, numero, status=status)
        with destino.open("xb") as output:
            destino.chmod(0o600)
            output.write(pdf)
    except (OSError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(str(destino.resolve()))


@sisdo.command("remover")
@click.option("--os-id", type=int, required=True)
@click.option("--numero", required=True)
@click.option("--matricula", required=True)
@click.option("--nome", required=True)
@click.option("--justificativa", required=True)
@click.option("--executar", is_flag=True)
def remover(os_id: int, numero: str, matricula: str, nome: str, justificativa: str, executar: bool) -> None:
    """Remover militar pela matrícula, com justificativa obrigatória."""
    try:
        with SISDOClient() as client:
            result = client.remove(os_id, numero, matricula, nome, justificativa, executar=executar)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps({"executado": executar, "resultado": result}, ensure_ascii=False, indent=2))


@sisdo.command("acrescentar-vagas")
@click.option("--os-id", type=int, required=True)
@click.option("--numero", required=True)
@click.option("--quantidade", type=int, required=True)
@click.option("--executar", is_flag=True)
def acrescentar(os_id: int, numero: str, quantidade: int, executar: bool) -> None:
    """Acrescentar vagas para inclusões adicionais."""
    try:
        with SISDOClient() as client:
            result = client.add_vacancies(os_id, numero, quantidade, executar=executar)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps({"executado": executar, "resultado": result}, ensure_ascii=False, indent=2))


@sisdo.command("reduzir-vagas")
@click.option("--os-id", type=int, required=True)
@click.option("--numero", required=True)
@click.option("--total", type=int, required=True, help="Total final, incluindo os militares já inseridos.")
@click.option("--executar", is_flag=True)
def reduzir(os_id: int, numero: str, total: int, executar: bool) -> None:
    """Reduzir o total removendo somente linhas atualmente vazias."""
    try:
        with SISDOClient() as client:
            result = client.reduce_vacancies(os_id, numero, total, executar=executar)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps({"executado": executar, "resultado": result}, ensure_ascii=False, indent=2))


sisdo.add_command(escala_cmd)

register_voluntariado(sisdo)
