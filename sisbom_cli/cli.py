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


# --- Maré ---


@cli.command("mare")
@click.option("--local", default="areia-branca", help="Localidade (slug tabuademares)")
@click.option("--json", "as_json", is_flag=True)
def mare_cmd(local: str, as_json: bool) -> None:
    """Tábua de marés do dia (via tabuademares.com)."""
    with SISBOMClient() as client:
        result = client.mare(location=local)

    if as_json:
        _emit(result, True)
        return

    console.print(f"\n🌊 [bold]Marés — {result.get('date', 'hoje')}[/bold]")
    console.print(f"📍 {local.replace('-', ' ').title()}\n")

    for t in result.get("tides", []):
        icon = "🔵" if t["type"] == "preia-mar" else "🟤"
        height = t.get("height", "")
        console.print(f"  {icon} {t['time']}  {t['type'].upper()}  {height}")

    if result.get("sunrise"):
        console.print(f"\n  🌅 Nascer: {result['sunrise']}  🌇 Pôr: {result.get('sunset', '?')}")

    if result.get("coeficients"):
        console.print(f"  📊 Coeficientes: {', '.join(result['coeficients'])}")

    console.print()


@cli.command("mare-sisbom")
@click.option("--date", default=None, help="Data (YYYY-MM-DD, default: hoje)")
@click.option("--json", "as_json", is_flag=True)
def mare_sisbom_cmd(date: str | None, as_json: bool) -> None:
    """Tábua de marés do SISBOM (Natal/RN)."""
    with SISBOMClient() as client:
        result = client.mare_sisbom(date=date)

    if as_json:
        _emit(result, True)
        return

    console.print(f"\n🌊 [bold]Marés SISBOM — {result.get('date', 'hoje')}[/bold]")
    console.print(f"📍 {result.get('location', 'Natal/RN')}\n")

    for h in result.get("heights", []):
        height_val = h.get("height", 0)
        icon = "🔵" if height_val > 1.0 else "🟤"
        tide_type = "PREIA-MAR" if height_val > 1.0 else "BAIXA-MAR"
        console.print(f"  {icon} {h['time']}  {tide_type}  {height_val}m")

    console.print()


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


# --- E-Funcional ---


@cli.command("efuncional")
@click.option("--matricula", default=None, help="Matrícula do militar (default: usuário logado)")
@click.option("--dest", default=None, help="Diretório destino do PDF")
@click.option("--list", "list_only", is_flag=True, help="Listar emissões sem exportar")
@click.option("--json", "as_json", is_flag=True)
def efuncional_cmd(matricula: str | None, dest: str | None, list_only: bool, as_json: bool) -> None:
    """Exportar e-Funcional como PDF."""
    with SISBOMClient() as client:
        client.login()

        if list_only:
            emissions = client.efuncional_list(str_matricula=matricula)
            if as_json:
                _emit(emissions, True)
                return
            if not emissions:
                click.echo("Nenhuma emissão encontrada.")
                return
            table = Table(title="Emissões e-Funcional")
            table.add_column("ID")
            table.add_column("Posto/Grad")
            table.add_column("Nome Guerra")
            table.add_column("Matrícula")
            table.add_column("Ativa")
            for e in emissions:
                table.add_row(
                    e.get("_id", ""),
                    e.get("str_patente", ""),
                    e.get("str_nomeguerra", ""),
                    e.get("str_matricula", ""),
                    "✅" if e.get("active") else "❌",
                )
            console.print(table)
            return

        result = client.efuncional(str_matricula=matricula, dest_dir=dest)

    if as_json:
        _emit(result, True)
        return

    click.echo(f"✅ E-Funcional exportada!")
    click.echo(f"   📄 {result['path']} ({result['size']:,} bytes)")
    click.echo(f"   👤 {result['patente']} {result['nome']} — Mat. {result['matricula']}")
    click.echo(f"   🔑 Verificação: {result['verify']} | CRC: {result['crc']}")


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


# --- Mapa de Força ---

PATENTE_ORDER = {
    1: "Cel", 2: "TC", 3: "Maj", 4: "Cap",
    5: "1º Ten", 6: "2º Ten", 7: "Asp",
    11: "ST", 12: "1º SGT", 13: "2º SGT", 14: "3º SGT",
    16: "CB", 17: "SD",
}


def _do_icon(val: bool | None) -> str:
    if val is True:
        return "✅"
    if val is False:
        return "🚫"
    return "❌"


def _funcao_label(f: str | None) -> str:
    labels = {
        "CMT_GU": "Cmt Gu",
        "COND_VTR": "Motorista",
        "AUX": "Auxiliar",
        "OP": "Operador",
    }
    return labels.get(f or "", f or "—")


@cli.command("mapa-forca")
@click.option("--lotacao", default="PABM_3GBM_APODI", help="Código da lotação")
@click.option("--date", "data", default=None, help="Data (YYYY-MM-DD), default=hoje")
@click.option("--json", "as_json", is_flag=True)
def mapa_forca_cmd(lotacao: str, data: str | None, as_json: bool) -> None:
    """Mapa de Força — efetivo real de serviço."""
    from datetime import date as dt_date

    if not data:
        data = dt_date.today().isoformat()

    with SISBOMClient() as client:
        client.login()
        militares = client.mapa_forca_militares(data, lotacao)
        guarnicoes = client.mapa_forca_guarnicoes(date=data, lotacao=lotacao)

    if as_json:
        _emit({"date": data, "lotacao": lotacao, "militares": militares, "guarnicoes": guarnicoes}, True)
        return

    if not militares and not guarnicoes:
        click.echo(f"⚠️  Sem dados para {lotacao} em {data}")
        return

    console.print(f"\n[bold]🗺️  Mapa de Força — {lotacao} — {data}[/bold]\n")

    # Fiscal / Adjunto
    fiscais = [m for m in militares if "FISCAL" in (m.get("atividade") or "").upper()]
    if fiscais:
        t = Table(title="🏢 Fiscal / Adjunto", show_header=True)
        t.add_column("Militar")
        t.add_column("Matrícula")
        t.add_column("DO")
        for f in fiscais:
            t.add_row(f["str_nomecurto"], f["str_matricula"], _do_icon(f.get("bo_diaria")))
        console.print(t)
        console.print()

    # Guarnições por atividade
    for gu in guarnicoes:
        ativ = gu.get("atividade", "—")
        prefixo = gu.get("prefixo", "—")
        title = f"🚒 {ativ} — {prefixo}"

        t = Table(title=title, show_header=True)
        t.add_column("Função")
        t.add_column("Militar")
        t.add_column("Matrícula")
        t.add_column("DO")

        for membro in gu.get("guarnicao", []):
            t.add_row(
                _funcao_label(membro.get("str_funcao")),
                membro.get("str_nomecurto", "—"),
                membro.get("str_matricula", "—"),
                _do_icon(membro.get("bo_diaria")),
            )
        console.print(t)
        console.print()

    # Militares sem guarnição (extra/individual)
    gu_mats = set()
    for gu in guarnicoes:
        for m in gu.get("guarnicao", []):
            gu_mats.add(m.get("str_matricula"))
    for f in fiscais:
        gu_mats.add(f.get("str_matricula"))

    extras = [m for m in militares if m.get("str_matricula") not in gu_mats]
    if extras:
        t = Table(title="📋 Outros (individuais)", show_header=True)
        t.add_column("Militar")
        t.add_column("Matrícula")
        t.add_column("Atividade")
        t.add_column("DO")
        for m in extras:
            t.add_row(
                m["str_nomecurto"],
                m["str_matricula"],
                m.get("atividade", "—"),
                _do_icon(m.get("bo_diaria")),
            )
        console.print(t)
        console.print()

    # Summary
    total = len(militares)
    total_do = sum(1 for m in militares if m.get("bo_diaria") is True)
    console.print(f"[dim]Total: {total} militares | {total_do} com DO[/dim]\n")


@cli.command("mapa-forca-mensal")
@click.option("--lotacao", default="PABM_3GBM_APODI", help="Código da lotação")
@click.option("--mes", default=None, help="Mês (YYYY-MM), default=mês atual")
@click.option("--output", default=None, help="Salvar markdown em arquivo")
@click.option("--json", "as_json", is_flag=True)
def mapa_forca_mensal_cmd(lotacao: str, mes: str | None, output: str | None, as_json: bool) -> None:
    """Relatório mensal de DOs — controle de diárias."""
    import time
    from datetime import date as dt_date, timedelta
    from collections import defaultdict

    today = dt_date.today()
    if not mes:
        mes = today.strftime("%Y-%m")

    year, month = map(int, mes.split("-"))

    # Build day range
    start = dt_date(year, month, 1)
    if month == 12:
        end = dt_date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = dt_date(year, month + 1, 1) - timedelta(days=1)
    if end > today:
        end = today

    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)

    if not days:
        click.echo("⚠️  Sem dias para processar")
        return

    console.print(f"[bold]📊 Mapa de Força Mensal — {lotacao} — {mes}[/bold]")
    console.print(f"[dim]Processando {len(days)} dias...[/dim]")

    # Collect data: {matricula: {name, patente, days: {date: {do, atividade}}}}
    militares_data: dict[str, dict] = {}

    with SISBOMClient() as client:
        client.login()
        for i, day in enumerate(days):
            day_str = day.isoformat()
            try:
                mils = client.mapa_forca_militares(day_str, lotacao)
            except Exception as e:
                console.print(f"[yellow]⚠️  {day_str}: {e}[/yellow]")
                mils = []

            for m in mils:
                mat = m.get("str_matricula", "?")
                if mat not in militares_data:
                    militares_data[mat] = {
                        "nome": m.get("str_nomecurto", "?"),
                        "patente": m.get("_patente"),
                        "days": {},
                    }
                militares_data[mat]["days"][day_str] = {
                    "do": m.get("bo_diaria"),
                    "atividade": m.get("atividade", "—"),
                }

            if i < len(days) - 1:
                time.sleep(0.3)

            # Progress
            if (i + 1) % 5 == 0 or i == len(days) - 1:
                console.print(f"  [{i + 1}/{len(days)}] {day_str}", style="dim")

    if not militares_data:
        click.echo("⚠️  Sem dados no período")
        return

    # Sort by patente then name
    sorted_mats = sorted(
        militares_data.items(),
        key=lambda x: (x[1].get("patente") or 99, x[1]["nome"]),
    )

    if as_json:
        out = {
            "mes": mes,
            "lotacao": lotacao,
            "dias": [d.isoformat() for d in days],
            "militares": {},
        }
        for mat, info in sorted_mats:
            total_do = sum(1 for d in info["days"].values() if d["do"] is True)
            out["militares"][mat] = {
                "nome": info["nome"],
                "patente": info["patente"],
                "total_do": total_do,
                "dias": info["days"],
            }
        _emit(out, True)
        return

    # Build markdown table
    day_headers = [d.strftime("%d") for d in days]
    lines = []
    lines.append(f"# Mapa de Força Mensal — {lotacao} — {mes}\n")
    lines.append(f"| Militar | Mat. | Total DO | {' | '.join(day_headers)} |")
    lines.append(f"|---------|------|----------|{'|'.join(['---'] * len(days))}|")

    for mat, info in sorted_mats:
        total_do = sum(1 for d in info["days"].values() if d["do"] is True)
        day_cells = []
        for day in days:
            ds = day.isoformat()
            if ds in info["days"]:
                day_cells.append("✅" if info["days"][ds]["do"] is True else "—")
            else:
                day_cells.append("")
        lines.append(f"| {info['nome']} | {mat} | {total_do} | {' | '.join(day_cells)} |")

    md = "\n".join(lines)

    if output:
        import os
        out_path = os.path.expanduser(output)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w") as f:
            f.write(md)
        console.print(f"\n✅ Salvo em: {out_path}")
    else:
        console.print()
        click.echo(md)

    # Rich summary table
    console.print(f"\n[bold]Resumo — {len(militares_data)} militares[/bold]\n")
    t = Table(show_header=True)
    t.add_column("Militar")
    t.add_column("Matrícula")
    t.add_column("Total DO", justify="center")
    t.add_column("% DO", justify="center")

    for mat, info in sorted_mats:
        total_do = sum(1 for d in info["days"].values() if d["do"] is True)
        total_present = len(info["days"])
        pct = f"{(total_do / total_present * 100):.0f}%" if total_present else "—"
        t.add_row(info["nome"], mat, str(total_do), pct)
    console.print(t)


@cli.command("mapa-forca-export")
@click.option("--lotacao", default="PABM_3GBM_APODI", help="Código da lotação")
@click.option("--mes", default=None, help="Mês (YYYY-MM), default=mês atual")
@click.option("--format", "fmt", type=click.Choice(["csv", "md"]), default="csv")
@click.option("--output", default=None, help="Salvar em arquivo")
def mapa_forca_export_cmd(lotacao: str, mes: str | None, fmt: str, output: str | None) -> None:
    """Export DO mensal para preenchimento no Rota."""
    import time
    from datetime import date as dt_date, timedelta
    from collections import defaultdict

    today = dt_date.today()
    if not mes:
        mes = today.strftime("%Y-%m")

    year, month = map(int, mes.split("-"))
    start = dt_date(year, month, 1)
    if month == 12:
        end = dt_date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = dt_date(year, month + 1, 1) - timedelta(days=1)
    if end > today:
        end = today

    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)

    console.print(f"[bold]📤 Export Rota — {lotacao} — {mes}[/bold]")
    console.print(f"[dim]{len(days)} dias...[/dim]")

    militares_data: dict[str, dict] = {}

    with SISBOMClient() as client:
        client.login()
        for i, day in enumerate(days):
            day_str = day.isoformat()
            try:
                mils = client.mapa_forca_militares(day_str, lotacao)
            except Exception:
                mils = []

            for m in mils:
                mat = m.get("str_matricula", "?")
                if mat not in militares_data:
                    militares_data[mat] = {"nome": m.get("str_nomecurto", "?"), "do_dates": []}
                if m.get("bo_diaria") is True:
                    militares_data[mat]["do_dates"].append(day_str)

            if i < len(days) - 1:
                time.sleep(0.3)

    if not militares_data:
        click.echo("⚠️  Sem dados")
        return

    sorted_mats = sorted(militares_data.items(), key=lambda x: x[1]["nome"])

    if fmt == "csv":
        lines = ["Matricula,Nome,Total_DO,Datas_DO"]
        for mat, info in sorted_mats:
            dates_str = ";".join(info["do_dates"])
            lines.append(f'{mat},{info["nome"]},{len(info["do_dates"])},"{dates_str}"')
    else:
        lines = [
            f"# Export Rota — {lotacao} — {mes}\n",
            "| Matrícula | Nome | Total DO | Datas DO |",
            "|-----------|------|----------|----------|",
        ]
        for mat, info in sorted_mats:
            dates_str = ", ".join(d[-5:] for d in info["do_dates"])  # MM-DD
            lines.append(f"| {mat} | {info['nome']} | {len(info['do_dates'])} | {dates_str} |")

    content = "\n".join(lines)

    if output:
        import os
        out_path = os.path.expanduser(output)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w") as f:
            f.write(content)
        console.print(f"\n✅ Salvo em: {out_path}")
    else:
        click.echo(content)


# --- Férias Reaprazamento ---


@cli.command("ferias-reaprazar")
@click.option("--matricula", default=None, help="Matrícula do militar (ex: 2241986)")
@click.option("--nome", default=None, help="Nome ou parte do nome (str_nomecurto)")
@click.option("--exercicio", default=None, help="Ano do exercício (ex: 2025, default: último disponível)")
@click.option("--lotacao", default=None, help="Filtro de lotação (ex: 1CAT, 3GBM)")
@click.option("--periodos", required=True, help='Novos períodos: "DD/MM/YYYY-DD/MM/YYYY,..." (múltiplos separados por vírgula)')
@click.option("--justificativa", required=True, help="Justificativa do reaprazamento")
@click.option("--dry-run", is_flag=True, help="Mostrar payload sem executar")
@click.option("--json", "as_json", is_flag=True, help="Saída em JSON")
def ferias_reaprazar_cmd(
    matricula: str | None,
    nome: str | None,
    exercicio: str | None,
    lotacao: str | None,
    periodos: str,
    justificativa: str,
    dry_run: bool,
    as_json: bool,
) -> None:
    """Reaprazar (reprogramar) férias de um militar."""
    import uuid
    from datetime import datetime, timezone, timedelta, date as dt_date

    # Validações iniciais
    if not matricula and not nome:
        raise click.UsageError("Informe --matricula ou --nome para identificar o militar.")
    if not justificativa.strip():
        raise click.UsageError("A --justificativa não pode ser vazia.")

    # Parsear períodos novos
    def parse_periodo(s: str) -> tuple[dt_date, dt_date]:
        parts = s.strip().split("-")
        if len(parts) != 2:
            raise click.UsageError(f"Formato inválido de período: '{s}'. Use DD/MM/YYYY-DD/MM/YYYY")
        try:
            inicio = datetime.strptime(parts[0].strip(), "%d/%m/%Y").date()
            fim = datetime.strptime(parts[1].strip(), "%d/%m/%Y").date()
        except ValueError as e:
            raise click.UsageError(f"Data inválida em '{s}': {e}")
        if fim < inicio:
            raise click.UsageError(f"dt_fim ({fim}) é anterior a dt_inicio ({inicio}) em '{s}'")
        return inicio, fim

    novos_periodos_parsed: list[tuple[dt_date, dt_date]] = []
    for chunk in periodos.split(","):
        novos_periodos_parsed.append(parse_periodo(chunk))

    with SISBOMClient() as client:
        client.login()

        # Buscar exercícios disponíveis
        exercicios = client.ferias_exercicios()
        if not exercicios:
            click.echo("❌ Nenhum exercício de férias encontrado.")
            return

        exercicio_ids = [e["_id"] for e in exercicios]

        # Escolher exercício
        if exercicio:
            str_ano = str(exercicio)
        else:
            # Último exercício disponível (maior _id que coincide com ano)
            anos = sorted(exercicio_ids, reverse=True)
            str_ano = anos[0]

        if str_ano not in exercicio_ids:
            click.echo(f"❌ Exercício '{str_ano}' não encontrado. Disponíveis: {', '.join(exercicio_ids)}")
            return

        # Buscar turmas do exercício
        turmas = client.ferias_turmas(str_ano)
        if not turmas:
            click.echo(f"❌ Nenhuma turma encontrada para exercício {str_ano}.")
            return

        # Para cada turma, buscar detalhe e encontrar o militar
        encontrado: dict | None = None
        turma_info: dict | None = None
        all_militares_found: list[dict] = []

        for turma in turmas:
            turma_id = turma["_id"]
            turma_num = turma.get("str_turmaferias", "")
            dt_inicio_turma = turma.get("dt_inicio", "")
            dt_fim_turma = turma.get("dt_fim", "")

            detalhe = client.ferias_turma_detalhe(
                turma_id=turma_id,
                str_ano=str_ano,
                turma_num=str(turma_num),
                dt_inicio=dt_inicio_turma,
                dt_fim=dt_fim_turma,
                lotacao=lotacao,
            )

            for item in detalhe:
                mil = item.get("militar", {})
                mil_nome = mil.get("str_nomecurto", "")
                mil_mat = mil.get("str_matricula", "")

                match = False
                if matricula:
                    # Normalizar matrícula removendo pontos/traços
                    mat_clean = "".join(c for c in (mil_mat or "") if c.isdigit())
                    query_clean = "".join(c for c in matricula if c.isdigit())
                    if mat_clean == query_clean or mil_mat == matricula:
                        match = True
                elif nome:
                    if nome.upper() in mil_nome.upper():
                        match = True

                if match:
                    all_militares_found.append({"item": item, "turma": turma})

        if not all_militares_found:
            click.echo(f"❌ Militar não encontrado nos critérios fornecidos.")
            if lotacao:
                click.echo(f"   Filtro de lotação: {lotacao}")
            click.echo(f"   Exercício: {str_ano}")
            return

        if len(all_militares_found) > 1:
            click.echo(f"⚠️  Múltiplos militares encontrados ({len(all_militares_found)}). Especifique mais:")
            for m in all_militares_found:
                mil = m["item"].get("militar", {})
                t = m["turma"]
                click.echo(f"   {mil.get('str_nomecurto')} ({mil.get('str_matricula')}) — Turma {t.get('str_turmaferias')} {t.get('dt_inicio')} → {t.get('dt_fim')}")
            return

        encontrado = all_militares_found[0]["item"]
        turma_info = all_militares_found[0]["turma"]

        # Identificar período original ativo
        periods_raw = encontrado.get("periods", [])
        periodo_original = next(
            (p for p in periods_raw if p.get("active") is True and not p.get("_reaprazados")),
            None,
        )
        # Fallback: primeiro período ativo
        if not periodo_original:
            periodo_original = next((p for p in periods_raw if p.get("active") is True), None)

        if not periodo_original:
            click.echo("❌ Nenhum período ativo encontrado para este militar.")
            return

        dias_original = periodo_original.get("int_dias", 0)
        dias_novos = sum((fim - ini).days + 1 for ini, fim in novos_periodos_parsed)

        # Validação: soma dos dias deve ser igual ao original
        if dias_novos != dias_original:
            click.echo(
                f"❌ Soma dos dias dos novos períodos ({dias_novos}) "
                f"≠ dias do período original ({dias_original})."
            )
            click.echo(f"   Os {dias_original} dias precisam ser distribuídos exatamente.")
            return

        # Obter ID do usuário logado
        me = client.me()
        meu_id = me.get("_id") if me else None

        # Montar timezone
        tz = timezone(timedelta(hours=-3))
        now_iso = datetime.now(tz).isoformat()

        # Construir lista de períodos do payload
        id_periodo_original = periodo_original["_id"]

        payload_periods: list[dict] = [
            {
                "_id": id_periodo_original,
                "created_at": periodo_original.get("created_at"),
                "active": False,
                "int_dias": dias_original,
                "dt_inicio": periodo_original["dt_inicio"],
                "dt_fim": periodo_original["dt_fim"],
            }
        ]

        for ini, fim in novos_periodos_parsed:
            periodo_id = str(uuid.uuid1())
            dias = (fim - ini).days + 1
            new_period: dict = {
                "_id": periodo_id,
                "created_at": now_iso,
                "active": True,
                "int_dias": dias,
                "dt_inicio": ini.isoformat(),
                "dt_fim": fim.isoformat(),
                "_reaprazado_por": meu_id,
                "_reaprazados": [id_periodo_original],
                "str_justificativa": justificativa,
            }
            payload_periods.append(new_period)

        ferias_militar_id = encontrado["_id"]
        mil = encontrado.get("militar", {})
        mil_nome = mil.get("str_nomecurto", "?")
        mil_mat = mil.get("str_matricula", "?")

        turma_num = turma_info.get("str_turmaferias", "?")
        turma_ini = turma_info.get("dt_inicio", "")[:10]
        turma_fim = turma_info.get("dt_fim", "")[:10]

        if dry_run or as_json:
            payload_out = {
                "input": {
                    "_id": ferias_militar_id,
                    "periods": payload_periods,
                }
            }
            if as_json or dry_run:
                if dry_run:
                    console.print(f"\n[bold yellow]🔍 DRY-RUN — payload que seria enviado:[/bold yellow]\n")
                click.echo(json.dumps(payload_out, ensure_ascii=False, indent=2, default=str))
                if dry_run:
                    console.print(f"\n[dim]Militar: {mil_nome} ({mil_mat}) | Exercício {str_ano} | Turma {turma_num}[/dim]")
                    console.print(f"[dim]Dias originais: {dias_original} | Dias novos: {dias_novos}[/dim]")
                return

        # Executar mutation
        result = client.ferias_reaprazar(ferias_militar_id, payload_periods)

        status = result.get("status", "")
        msg = result.get("msg", "")

        if status not in ("ok", "success", "200") and status:
            # Checar se veio erro
            if "err" in status.lower() or "fail" in status.lower():
                console.print(f"\n❌ Erro: {msg or status}")
                return

        # Re-consultar detalhe atualizado
        try:
            detalhe_novo = client.ferias_turma_detalhe(
                turma_id=turma_info["_id"],
                str_ano=str_ano,
                turma_num=str(turma_num),
                dt_inicio=turma_info.get("dt_inicio", ""),
                dt_fim=turma_info.get("dt_fim", ""),
                lotacao=lotacao,
            )
            # Encontrar o militar novamente
            item_novo = next(
                (
                    x for x in detalhe_novo
                    if x.get("_id") == ferias_militar_id
                ),
                None,
            )
            periods_final = item_novo.get("periods", []) if item_novo else payload_periods
        except Exception:
            periods_final = payload_periods

        # Exibir tabela rich com resultado
        def fmt_date(s: str | None) -> str:
            if not s:
                return "—"
            try:
                return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
            except ValueError:
                return s[:10]

        def fmt_turma_date(s: str | None) -> str:
            return fmt_date(s)

        ini_fmt = fmt_turma_date(turma_ini)
        fim_fmt = fmt_turma_date(turma_fim)

        console.print(f"\n[bold]Reaprazamento de Férias — {mil_nome} ({mil_mat})[/bold]")
        console.print(f"[dim]Exercício {str_ano} | Turma {turma_num} | {ini_fmt} — {fim_fmt}[/dim]\n")

        table = Table(show_header=True)
        table.add_column("Dias", justify="center")
        table.add_column("Início")
        table.add_column("Término")
        table.add_column("Status")
        table.add_column("Reprogramado Por")

        for p in sorted(periods_final, key=lambda x: x.get("dt_inicio", "")):
            ativo = p.get("active", True)
            status_str = "[green]ATIVO[/green]" if ativo else "[dim]INATIVO[/dim]"
            reprog_por = p.get("reaprazado_por") or p.get("_reaprazado_por")
            if isinstance(reprog_por, dict):
                reprog_str = reprog_por.get("str_nomecurto") or reprog_por.get("_id", "—")[:8] + "…"
            elif isinstance(reprog_por, str):
                reprog_str = reprog_por[:8] + "…" if reprog_por else "—"
            else:
                reprog_str = "—"
            table.add_row(
                str(p.get("int_dias", "?")),
                fmt_date(p.get("dt_inicio")),
                fmt_date(p.get("dt_fim")),
                status_str,
                reprog_str,
            )

        console.print(table)
        console.print(f"\n✅ Reaprazamento registrado com sucesso")
        if msg:
            console.print(f"   [dim]{msg}[/dim]")


if __name__ == "__main__":
    cli()
