"""synapseformation command line client"""
import click
import synapseclient

from .__version__ import __version__

from .client import apply_config

# from .utils import synapse_login


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
@click.option("--template_path", help="Template path", type=click.Path())
def apply(template_path):
    """Creates Synapse Resources given a yaml or json"""
    apply_config(config_path=template_path)


if __name__ == "__main__":
    cli()
