"""synapseformation command line client"""
import click
import synapseclient

from .__version__ import __version__

from .client import apply_config, plan_config

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
    synapseformation is a tool to manage Synapse resources via configuration files.
    """
    pass


@cli.command()
@click.option("--template_path", help="Template path", type=click.Path())
def apply(template_path):
    """Creates Synapse Resources given a yaml or json"""
    my_agent = "synapseformation/0.0.0"
    syn = synapseclient.Synapse(user_agent=my_agent)
    syn.login()
    apply_config(config_path=template_path)


@cli.command()
@click.option("--template_path", help="Template path", type=click.Path())
def plan(template_path):
    """Creates Synapse Resources given a yaml or json"""
    my_agent = "synapseformation/0.0.0"
    syn = synapseclient.Synapse(user_agent=my_agent)
    syn.login()
    changes = plan_config(config_path=template_path)
    update = 0
    create = 0
    delete = 0
    for change in changes["changes"]:
        print(change)
        if change["action"] == "update":
            update += 1
        elif change["action"] == "create":
            create += 1
        else:
            delete += 1
    print(f"There are {create} creations, {update} updates, and {delete} deletions")
    print(changes["drift"])


if __name__ == "__main__":
    cli()
