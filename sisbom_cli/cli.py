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


if __name__ == "__main__":
    cli()
