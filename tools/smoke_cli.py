"""Exercise every registered --help without network, credentials or mutations."""
from importlib.metadata import version
import click
from click.testing import CliRunner
from sisbom_cli.cli import cli

def walk(command, path):
    result = CliRunner().invoke(cli, path + ['--help'])
    if result.exit_code:
        raise RuntimeError('Help failed: ' + ' '.join(path))
    count = 1
    if isinstance(command, click.Group):
        ctx = click.Context(command)
        for name in command.list_commands(ctx):
            count += walk(command.get_command(ctx, name), path + [name])
    return count

print({'version': version('sisbom-cli'), 'help_commands_checked': walk(cli, [])})
