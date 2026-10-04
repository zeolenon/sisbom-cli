"""Isolated SISDO commands; register via register(sisdo) after coordination."""
import json
import click
from ..voluntariado import VoluntariadoClient, plan_profile


def _run(action):
    try:
        with VoluntariadoClient() as client:
            result = action(client)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


@click.command('voluntarios')
@click.option('--competencia', required=True, help='AAAA-MM; nunca inferida da data atual.')
@click.option('--quartel', multiple=True, required=True, help='assu, apodi, pau-dos-ferros, mossoro ou ID; repetível.')
@click.option('--json', 'as_json', is_flag=True, help='Saída JSON (também padrão).')
def voluntarios(competencia, quartel, as_json):
    """Consultar inscrições mensais sem gerar lista definitiva."""
    _run(lambda client: client.list_volunteers(competencia, quartel))


@click.command('voluntariado-perfil')
def perfil():
    """Consultar ciclo e inscrições atuais do próprio usuário."""
    _run(lambda client: client.profile())


@click.command('voluntariado-prever')
@click.option('--competencia', required=True)
@click.option('--quartel', multiple=True, required=True)
@click.option('--modo', type=click.Choice(['adicionar','remover','substituir']), default='adicionar', show_default=True)
@click.option('--permitir-remocao', is_flag=True, help='Permitir somente a PRÉVIA de remoções explícitas.')
def prever(competencia, quartel, modo, permitir_remocao):
    """Prévia sem POST; preservar inscrições existentes por padrão."""
    from ..voluntariado import QUARTEIS
    _run(lambda client: plan_profile(client.profile(), competencia,
         [QUARTEIS.get(u,u) for u in quartel], modo, permitir_remocao))


@click.command('voluntariado-inscrever')
@click.option('--competencia', required=True, help='AAAA-MM; deve coincidir com ciclo aberto do próprio perfil.')
@click.option('--quartel', multiple=True, required=True, help='Adicionar quartel, preservando seleções existentes; repetível.')
@click.option('--diario', type=click.Path(dir_okay=False), help='Diário privado por usuário; obrigatório com --executar.')
@click.option('--esperar-hash', help='Hash da prévia; recusar perfil diferente.')
@click.option('--executar', is_flag=True, help='Enviar a própria inscrição aditiva; padrão apenas prévia.')
def inscrever(competencia, quartel, diario, esperar_hash, executar):
    """Inscrever o próprio usuário, sem retirar quartéis atuais; conferir após POST."""
    _run(lambda client: client.enroll(competencia, quartel, execute=executar,
                                     expected_hash=esperar_hash, journal=diario))


def register(group):
    for command in (voluntarios, perfil, prever, inscrever): group.add_command(command)


@click.group()
def standalone():
    """Comandos isolados, enquanto integração ao grupo sisdo é coordenada."""
register(standalone)
if __name__ == '__main__': standalone()
