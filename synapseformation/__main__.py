"""synapseformation command line client"""

from __future__ import annotations

import functools
import os
import re
import shutil
import sys
from pathlib import Path

import click

from . import __version__
from .engine import TemplateError, build_program
from .utils import read_config

PROJECT_NAME = "synapseformation"


def default_stack_name(template_path: str) -> str:
    """One stack per template file, e.g. ``treat_ad.yaml`` -> ``treat_ad``."""
    stem = Path(template_path).stem
    return re.sub(r"[^A-Za-z0-9_.-]", "-", stem) or "default"


def default_backend_url() -> str:
    """Local state under ./.synapseformation unless PULUMI_BACKEND_URL is set."""
    if os.environ.get("PULUMI_BACKEND_URL"):
        return os.environ["PULUMI_BACKEND_URL"]
    path = Path.cwd() / ".synapseformation"
    return f"file://{path.as_posix()}"


def get_stack(template_path: str, stack_name: str | None, backend_url: str | None):
    """Create or select the Pulumi stack for a template."""
    from pulumi import automation as auto

    if shutil.which("pulumi") is None:
        raise click.ClickException(
            "The Pulumi CLI is required: https://www.pulumi.com/docs/install/"
        )
    try:
        program = build_program(read_config(template_path))
    except TemplateError as error:
        raise click.ClickException(f"Invalid template: {error}") from error

    backend_url = backend_url or default_backend_url()
    env_vars = {"PULUMI_SKIP_UPDATE_CHECK": "true"}
    secrets_provider = None
    if backend_url.startswith("file://"):
        Path(backend_url[len("file://"):]).mkdir(parents=True, exist_ok=True)
        secrets_provider = "passphrase"
        # The template holds no secrets; an empty passphrase avoids a prompt.
        if not (
            os.environ.get("PULUMI_CONFIG_PASSPHRASE")
            or os.environ.get("PULUMI_CONFIG_PASSPHRASE_FILE")
        ):
            env_vars["PULUMI_CONFIG_PASSPHRASE"] = ""

    project_settings = auto.ProjectSettings(
        name=PROJECT_NAME,
        runtime="python",
        backend=auto.ProjectBackend(url=backend_url),
    )
    return auto.create_or_select_stack(
        stack_name=stack_name or default_stack_name(template_path),
        project_name=PROJECT_NAME,
        program=program,
        opts=auto.LocalWorkspaceOptions(
            project_settings=project_settings,
            secrets_provider=secrets_provider,
            env_vars=env_vars,
        ),
    )


def stack_options(func):
    """Options shared by every command."""

    @click.argument("template_path", type=click.Path(exists=True, dir_okay=False))
    @click.option(
        "--stack",
        "stack_name",
        help="Stack name. Defaults to the template file name.",
    )
    @click.option(
        "--backend-url",
        help="Pulumi state backend, e.g. s3://bucket/prefix. Defaults to "
        "$PULUMI_BACKEND_URL or file://./.synapseformation",
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def engine_errors(func):
    """Show Pulumi failures as a short message rather than a traceback."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from pulumi import automation as auto

        try:
            return func(*args, **kwargs)
        except auto.CommandError as error:
            raise click.ClickException(
                "Pulumi reported errors; see the output above."
            ) from error

    return wrapper


def _confirm(message: str, yes: bool) -> None:
    if not yes and not click.confirm(message):
        click.echo("Cancelled.")
        sys.exit(1)


@click.group()
@click.version_option(
    __version__, "-V", "--version", message="%(prog)s, version %(version)s"
)
def cli():
    """Manage Synapse resources from a YAML or JSON template.

    State, planning, drift detection and dependency ordering are handled by
    the Pulumi engine. Synapse credentials come from SYNAPSE_AUTH_TOKEN or
    ~/.synapseConfig.
    """


@cli.command()
@stack_options
@engine_errors
@click.option("--diff", is_flag=True, help="Show property-level differences.")
@click.option(
    "--refresh/--no-refresh",
    default=True,
    help="Read current Synapse state first so drift shows up in the plan.",
)
def plan(template_path, stack_name, backend_url, diff, refresh):
    """Show what apply would change."""
    stack = get_stack(template_path, stack_name, backend_url)
    stack.preview(on_output=click.echo, diff=diff, refresh=refresh)


@cli.command()
@stack_options
@engine_errors
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--diff", is_flag=True, help="Show property-level differences.")
@click.option(
    "--refresh/--no-refresh",
    default=True,
    help="Read current Synapse state first and reconcile any drift.",
)
def apply(template_path, stack_name, backend_url, yes, diff, refresh):
    """Create, update and delete Synapse resources to match the template."""
    stack = get_stack(template_path, stack_name, backend_url)
    if not yes:
        stack.preview(on_output=click.echo, diff=diff, refresh=refresh)
        _confirm("Apply these changes?", yes)
    stack.up(on_output=click.echo, diff=diff, refresh=refresh)


@cli.command()
@stack_options
@engine_errors
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
def destroy(template_path, stack_name, backend_url, yes):
    """Delete every Synapse resource managed by this stack."""
    stack = get_stack(template_path, stack_name, backend_url)
    _confirm(f"Delete all resources in stack '{stack.name}'?", yes)
    stack.destroy(on_output=click.echo)


@cli.command()
@stack_options
@engine_errors
def refresh(template_path, stack_name, backend_url):
    """Update the state to match what is currently in Synapse."""
    stack = get_stack(template_path, stack_name, backend_url)
    stack.refresh(on_output=click.echo)


@cli.command()
@stack_options
@engine_errors
def output(template_path, stack_name, backend_url):
    """Print the Synapse ID of each managed resource."""
    stack = get_stack(template_path, stack_name, backend_url)
    for name, value in sorted(stack.outputs().items()):
        click.echo(f"{name}: {value.value}")


if __name__ == "__main__":
    cli()
