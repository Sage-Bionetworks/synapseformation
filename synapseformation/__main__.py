"""synapseformation command line client"""
import click
import synapseclient

from . import __version__
from .client import apply_config, plan_config, destroy_resources
from .utils import read_config


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
    synapseformation is a tool to manage Synapse resources via yaml. Similar to cloudformation is for AWS.
    """
    pass


@cli.command()
@click.argument("template_path", type=click.Path(exists=True))
def apply(template_path):
    """Creates Synapse Resources given a yaml or json"""
    my_agent = "synapseformation/0.0.0"
    syn = synapseclient.Synapse(user_agent=my_agent)
    syn.login()
    config = read_config(template_path=template_path)
    apply_config(config=config)


@cli.command()
@click.argument("template_path", type=click.Path(exists=True))
def plan(template_path):
    """Show the changes to Synapse resources by comparing the TEMPLATE_FILE.yaml with any existing state file"""
    my_agent = "synapseformation/0.0.0"
    syn = synapseclient.Synapse(user_agent=my_agent)
    syn.login()
    config = read_config(template_path=template_path)
    changes = plan_config(config=config, syn=syn)
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
    for drifts in changes["drift"]:
        print(drifts)
    print(f"There are {len(changes['drift'])} drifts detected")


@cli.command()
def destroy():
    """Shows the potential changes to Synapse resources by comparing the template with the state file"""
    my_agent = "synapseformation/0.0.0"
    syn = synapseclient.Synapse(user_agent=my_agent)
    syn.login()
    destroy_resources(syn=syn)


if __name__ == "__main__":
    cli()
