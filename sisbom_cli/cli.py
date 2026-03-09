"""SISBOM CLI — Command-line interface."""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.table import Table

from .client import SISBOMClient

console = Console()


def _emit(data: object, as_json: bool) -> None:
    """Output data as JSON."""
    click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))


@click.group()
def cli() -> None:
    """SISBOM CLI — acesso ao SISBOM via GraphQL."""


# --- Auth ---


@cli.command("login")
@click.option("--json", "as_json", is_flag=True)
def login_cmd(as_json: bool) -> None:
    """Login no SISBOM e obter token JWT."""
    with SISBOMClient() as client:
        result = client.login()
    if as_json:
        _emit(result, True)
        return
    if result.get("ok"):
        cached = " (cache)" if result.get("cached") else ""
        click.echo(f"✅ Login OK{cached}")
        if result.get("user"):
            click.echo(f"   CPF: {result['user'].get('str_cpf', 'N/A')}")
    else:
        click.echo(f"❌ {result.get('message', 'Erro')}")


@cli.command("me")
@click.option("--json", "as_json", is_flag=True)
def me_cmd(as_json: bool) -> None:
    """Dados do usuário logado."""
    with SISBOMClient() as client:
        client.login()
        result = client.me()
    if as_json:
        _emit(result, True)
        return
    if result:
        for k, v in result.items():
            click.echo(f"  {k}: {v}")
    else:
        click.echo("❌ Não autenticado")


# --- Efetivo ---


@cli.command("efetivo")
@click.option("--lotacao", default=None, help="Filtrar por lotação")
@click.option("--json", "as_json", is_flag=True)
def efetivo_cmd(lotacao: str | None, as_json: bool) -> None:
    """Listar efetivo militar."""
    with SISBOMClient() as client:
        client.login()
        if lotacao:
            result = client.militares(lotacao=lotacao)
        else:
            result = client.efetivo()

    if as_json:
        _emit(result, True)
        return

    table = Table(title=f"Efetivo ({len(result)} militares)")
    table.add_column("Matrícula")
    table.add_column("Patente")
    table.add_column("Nome")
    table.add_column("Lotação")

    for m in result:
        mat = m.get("str_matricula", "")
        pat = str(m.get("_patente", ""))
        nome = m.get("str_nomecurto", "")
        # MilitarEfetivo uses lotacao.N1/N2/N3; militares uses _lotacao string
        lot_obj = m.get("lotacao") or {}
        lot = lot_obj.get("N3") or lot_obj.get("N2") or lot_obj.get("N1") or m.get("_lotacao", "")
        table.add_row(mat, pat, nome, lot)

    console.print(table)


@cli.command("militar")
@click.argument("query")
@click.option("--json", "as_json", is_flag=True)
def militar_cmd(query: str, as_json: bool) -> None:
    """Consultar militar por matrícula ou CPF."""
    with SISBOMClient() as client:
        client.login()

        # Detect if query is CPF (11 digits) or matrícula
        digits = "".join(c for c in query if c.isdigit())
        if len(digits) == 11:
            result = client.militar(cpf=digits)
        else:
            result = client.militar(matricula=query)

    if as_json:
        _emit(result, True)
        return

    if not result:
        click.echo(f"❌ Militar não encontrado: {query}")
        return

    for k, v in result.items():
        if isinstance(v, dict):
            v = ", ".join(f"{sk}: {sv}" for sk, sv in v.items() if sv)
        click.echo(f"  {k}: {v}")


@cli.command("aniversariantes")
@click.argument("mes")
@click.option("--dia", default=None)
@click.option("--json", "as_json", is_flag=True)
def aniversariantes_cmd(mes: str, dia: str | None, as_json: bool) -> None:
    """Listar aniversariantes do mês."""
    with SISBOMClient() as client:
        client.login()
        result = client.aniversariantes(
            ano="",  # Empty = current year
            mes=mes.zfill(2),
            dia=dia,
        )

    if as_json:
        _emit(result, True)
        return

    table = Table(title=f"Aniversariantes — Mês {mes}")
    table.add_column("Data")
    table.add_column("Patente")
    table.add_column("Nome")
    table.add_column("Lotação")

    for m in result:
        dt = m.get("dt_nascimento", "")[:10]
        pat = (m.get("_patente") or {}).get("str_patente", "")
        nome = m.get("str_nomecurto", "")
        lot = (m.get("_lotacao") or {}).get("str_lotacao", "")
        table.add_row(dt, pat, nome, lot)

    console.print(table)


# --- Lotações ---


@cli.command("lotacoes")
@click.option("--json", "as_json", is_flag=True)
def lotacoes_cmd(as_json: bool) -> None:
    """Listar lotações disponíveis."""
    with SISBOMClient() as client:
        client.login()
        result = client.lotacoes()

    if as_json:
        _emit(result, True)
        return

    table = Table(title=f"Lotações ({len(result)})")
    table.add_column("Sigla")
    table.add_column("Nome")
    table.add_column("Nível")
    table.add_column("Op.")

    for l in result:
        table.add_row(
            l.get("str_sigla", ""),
            l.get("str_nome") or l.get("str_sigla_extenso", ""),
            l.get("nivel", ""),
            "✅" if l.get("operacional") else "",
        )

    console.print(table)


# --- Diárias ---


@cli.command("diarias")
@click.option("--json", "as_json", is_flag=True)
def diarias_cmd(as_json: bool) -> None:
    """Listar diárias."""
    with SISBOMClient() as client:
        client.login()
        result = client.diarias()

    if as_json:
        _emit(result, True)
        return

    table = Table(title=f"Diárias ({len(result)})")
    table.add_column("Militar")
    table.add_column("Destino")
    table.add_column("Início")
    table.add_column("Fim")
    table.add_column("Status")

    for d in result:
        mil = (d.get("_militar") or {}).get("str_nomecurto", "")
        table.add_row(
            mil,
            d.get("str_destino", ""),
            (d.get("dt_inicio") or "")[:10],
            (d.get("dt_fim") or "")[:10],
            d.get("str_status", ""),
        )

    console.print(table)


# --- Viaturas ---


@cli.command("viaturas")
@click.option("--json", "as_json", is_flag=True)
def viaturas_cmd(as_json: bool) -> None:
    """Listar viaturas."""
    with SISBOMClient() as client:
        client.login()
        result = client.viaturas()

    if as_json:
        _emit(result, True)
        return

    table = Table(title=f"Viaturas ({len(result)})")
    table.add_column("Prefixo")
    table.add_column("Placa")
    table.add_column("Modelo")
    table.add_column("Tipo")
    table.add_column("Op.")

    for v in result:
        table.add_row(
            v.get("prefixo", ""),
            v.get("placa", ""),
            v.get("modelo", ""),
            v.get("tipo_viatura", ""),
            "✅" if v.get("operante") == "1" else "❌",
        )

    console.print(table)


# --- BGs ---


@cli.command("bgs")
@click.option("--year", default=None, help="Ano (ex: 2026)")
@click.option("--num", default=None, help="Número do BG (ex: 040)")
@click.option("--limit", default=20, show_default=True, help="Limite de resultados")
@click.option("--json", "as_json", is_flag=True)
def bgs_cmd(year: str | None, num: str | None, limit: int, as_json: bool) -> None:
    """Listar Boletins Gerais disponíveis no SISBOM."""
    with SISBOMClient() as client:
        client.login()
        result = client.list_bgs(year=year, bg_num=num)

    if not year and not num:
        result = result[:limit]

    if as_json:
        _emit(result, True)
        return

    table = Table(title=f"Boletins Gerais ({len(result)})")
    table.add_column("Ano")
    table.add_column("BG")
    table.add_column("Data Ref")
    table.add_column("URL")

    for d in result:
        # Convert ms timestamp to date
        date_ref = d.get("date_ref", "")
        if date_ref and date_ref.isdigit():
            import datetime
            dt = datetime.datetime.fromtimestamp(int(date_ref) / 1000)
            date_ref = dt.strftime("%d/%m/%Y")
        url = d.get("url", "")[-50:]
        table.add_row(
            d.get("year", ""),
            d.get("bg_num", ""),
            date_ref,
            url,
        )

    console.print(table)


@cli.command("bg-download")
@click.argument("bg_num")
@click.option("--year", default=None, help="Ano (padrão: mais recente)")
@click.option("--dest", default=None, help="Diretório de destino")
@click.option("--json", "as_json", is_flag=True)
def bg_download_cmd(bg_num: str, year: str | None, dest: str | None, as_json: bool) -> None:
    """Baixar um BG pelo número."""
    with SISBOMClient() as client:
        client.login()
        bgs = client.list_bgs(year=year, bg_num=bg_num.zfill(3))

    if not bgs:
        click.echo(f"❌ BG {bg_num} não encontrado")
        return

    bg = bgs[0]
    with SISBOMClient() as client:
        client.login()
        path = client.download_bg(bg, dest_dir=dest)

    if as_json:
        _emit({"path": path, "bg": bg}, True)
        return

    click.echo(f"✅ BG {bg['bg_num']}/{bg['year']} → {path}")


# --- Raw Query ---


@cli.command("query")
@click.argument("graphql_query")
@click.option("--vars", "variables", default=None, help="JSON variables")
def query_cmd(graphql_query: str, variables: str | None) -> None:
    """Executar query GraphQL raw."""
    with SISBOMClient() as client:
        client.login()
        vars_dict = json.loads(variables) if variables else None
        result = client.raw_query(graphql_query, variables=vars_dict)
    _emit(result, True)


@cli.command("introspect")
@click.argument("type_name")
def introspect_cmd(type_name: str) -> None:
    """Introspect a GraphQL type."""
    with SISBOMClient() as client:
        client.login()
        result = client.introspect_type(type_name)

    if not result:
        click.echo(f"❌ Type '{type_name}' not found")
        return

    click.echo(f"Type: {result.get('name')} ({result.get('kind')})")
    for f in result.get("fields", []):
        ftype = f.get("type", {})
        tname = ftype.get("name") or (ftype.get("ofType") or {}).get("name", "?")
        click.echo(f"  {f['name']}: {tname}")


if __name__ == "__main__":
    cli()
