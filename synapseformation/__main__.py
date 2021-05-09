"""synapseformation command line client"""
import click
import synapseclient

from .client import create_synapse_resources
from .__version__ import __version__


def add_version(f):
    """Adds the version of the tool to the help heading.

    Args:
        f: function to decorate

    Returns:
        decorated function
    """
    doc = f.__doc__
    f.__doc__ = "Version: " + __version__ + "\n\n" + doc

    return f


@click.group()
@click.version_option(
    __version__, "-V", "--version", message="%(prog)s, version %(version)s"
)
# @click.pass_context
# @add_version
def cli():
    """
    Welcome to the synapseformation help page
    $ synapseformation --help
    """
    pass


@cli.command()
@click.option('--template_path', help='Template path', type=click.Path())
def create(template_path):
    """Creates Synapse Resources"""
    # syn = utils.synapse_login()
    # syn = synapseclient.login()
    create_synapse_resources(template_path)


if __name__ == "__main__":
    cli()
