"""Turn a synapseformation template into a Pulumi program.

Template format (unchanged from earlier versions)::

    version: 1
    name: "My study"
    resources:
      <logical_name>:
        type: team | project | folder | acl
        import: syn123        # optional: adopt an existing team/project/folder
        protect: true         # optional: refuse to delete
        properties: {...}

References use ``<type>.<logical_name>`` (``folder.raw_data``). Entity
references may also be an existing Synapse ID (``syn123``), and ACL
principals may be a numeric principal ID or ``PUBLIC`` /
``AUTHENTICATED_USERS``.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pulumi

from .providers import SynapseAcl, SynapseFolder, SynapseProject, SynapseTeam

RESOURCE_TYPES = {"team", "project", "folder", "acl"}
ENTITY_TYPES = {"project", "folder"}
REQUIRED_PROPERTIES = {
    "team": ["name"],
    "project": ["name"],
    "folder": ["name", "parent"],
    "acl": ["resource", "grants"],
}
WELL_KNOWN_PRINCIPALS = {"AUTHENTICATED_USERS": 273948, "PUBLIC": 273949}
SYNAPSE_ID = re.compile(r"^syn\d+$")


class TemplateError(ValueError):
    """Raised when a template is invalid."""


@dataclass
class ResourceSpec:
    logical_name: str
    type: str
    properties: dict
    import_id: Optional[str] = None
    protect: bool = False
    depends_on: list[str] = field(default_factory=list)


def _parse_ref(ref: str, allowed_types: set[str], where: str) -> Optional[str]:
    """Return the logical name a ``type.name`` reference points to.

    Returns None for literal Synapse IDs.
    """
    if SYNAPSE_ID.match(str(ref)):
        return None
    parts = str(ref).split(".")
    if len(parts) != 2 or parts[0] not in allowed_types:
        allowed = ", ".join(sorted(allowed_types))
        raise TemplateError(
            f"{where}: invalid reference '{ref}'; expected <{allowed}>.<name> "
            "or a Synapse ID"
        )
    return parts[1]


def _principal_ref(principal: Any, where: str) -> Optional[str]:
    if isinstance(principal, int) or str(principal).isdigit():
        return None
    if str(principal).upper() in WELL_KNOWN_PRINCIPALS:
        return None
    return _parse_ref(principal, {"team"}, where)


def parse_template(config: dict) -> list[ResourceSpec]:
    """Validate a template and return its resources in dependency order."""
    resources = (config or {}).get("resources")
    if not isinstance(resources, dict) or not resources:
        raise TemplateError("template must define a non-empty 'resources' mapping")

    specs: dict[str, ResourceSpec] = {}
    for name, body in resources.items():
        where = f"resources.{name}"
        if not isinstance(body, dict):
            raise TemplateError(f"{where}: must be a mapping")
        rtype = body.get("type")
        if rtype not in RESOURCE_TYPES:
            raise TemplateError(
                f"{where}: unknown type '{rtype}'; expected one of "
                f"{', '.join(sorted(RESOURCE_TYPES))}"
            )
        props = body.get("properties") or {}
        missing = [k for k in REQUIRED_PROPERTIES[rtype] if k not in props]
        if missing:
            raise TemplateError(f"{where}: missing properties {missing}")
        if body.get("import") and rtype == "acl":
            raise TemplateError(f"{where}: 'import' is not supported for acl")
        spec = ResourceSpec(
            logical_name=name,
            type=rtype,
            properties=props,
            import_id=body.get("import"),
            protect=bool(body.get("protect", False)),
        )
        if rtype == "folder":
            spec.depends_on = _deps([props["parent"]], ENTITY_TYPES, where)
        elif rtype == "acl":
            deps = _deps([props["resource"]], ENTITY_TYPES, where)
            for i, grant in enumerate(props["grants"]):
                gwhere = f"{where}.grants[{i}]"
                if "principal" not in grant or "access_type" not in grant:
                    raise TemplateError(f"{gwhere}: needs principal and access_type")
                ref = _principal_ref(grant["principal"], gwhere)
                if ref:
                    deps.append(ref)
            spec.depends_on = deps
        specs[name] = spec

    for spec in specs.values():
        for dep in spec.depends_on:
            if dep not in specs:
                raise TemplateError(
                    f"resources.{spec.logical_name}: references unknown resource "
                    f"'{dep}'"
                )
    _check_ref_types(specs, resources)
    return _topological_order(specs)


def _deps(refs: list[str], allowed: set[str], where: str) -> list[str]:
    return [n for n in (_parse_ref(r, allowed, where) for r in refs) if n]


def _check_ref_types(specs: dict[str, ResourceSpec], raw: dict) -> None:
    """Make sure ``folder.x`` really points at a folder, and so on."""
    def check(ref: Any, where: str) -> None:
        text = str(ref)
        if SYNAPSE_ID.match(text) or "." not in text:
            return
        rtype, name = text.split(".", 1)
        if name in specs and specs[name].type != rtype:
            raise TemplateError(
                f"{where}: '{text}' refers to a {specs[name].type}, not a {rtype}"
            )

    for spec in specs.values():
        where = f"resources.{spec.logical_name}"
        if spec.type == "folder":
            check(spec.properties["parent"], where)
        elif spec.type == "acl":
            check(spec.properties["resource"], where)
            for grant in spec.properties["grants"]:
                check(grant["principal"], where)


def _topological_order(specs: dict[str, ResourceSpec]) -> list[ResourceSpec]:
    in_degree = {name: 0 for name in specs}
    children: dict[str, list[str]] = {name: [] for name in specs}
    for spec in specs.values():
        for dep in set(spec.depends_on):
            children[dep].append(spec.logical_name)
            in_degree[spec.logical_name] += 1
    queue = deque(name for name in specs if in_degree[name] == 0)
    order = []
    while queue:
        name = queue.popleft()
        order.append(specs[name])
        for child in children[name]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    if len(order) != len(specs):
        cycle = sorted(n for n, d in in_degree.items() if d > 0)
        raise TemplateError(f"dependency cycle between resources: {cycle}")
    return order


def build_program(config: dict) -> Callable[[], None]:
    """Return a Pulumi program function for the template."""
    specs = parse_template(config)

    def program() -> dict[str, pulumi.CustomResource]:
        created: dict[str, pulumi.CustomResource] = {}

        def entity_id(ref: str) -> pulumi.Input[str]:
            if SYNAPSE_ID.match(str(ref)):
                return str(ref)
            return created[str(ref).split(".")[1]].id

        def principal_id(principal: Any) -> pulumi.Input[int]:
            if isinstance(principal, int) or str(principal).isdigit():
                return int(principal)
            if str(principal).upper() in WELL_KNOWN_PRINCIPALS:
                return WELL_KNOWN_PRINCIPALS[str(principal).upper()]
            return created[str(principal).split(".")[1]].id.apply(int)

        for spec in specs:
            props = spec.properties
            opts = pulumi.ResourceOptions(protect=spec.protect)
            if spec.type == "team":
                resource = SynapseTeam(
                    spec.logical_name,
                    name=props["name"],
                    description=props.get("description"),
                    can_public_join=bool(props.get("can_public_join", False)),
                    adopt_id=spec.import_id,
                    opts=opts,
                )
            elif spec.type == "project":
                resource = SynapseProject(
                    spec.logical_name,
                    name=props["name"],
                    description=props.get("description"),
                    adopt_id=spec.import_id,
                    opts=opts,
                )
            elif spec.type == "folder":
                resource = SynapseFolder(
                    spec.logical_name,
                    name=props["name"],
                    parent_id=entity_id(props["parent"]),
                    description=props.get("description"),
                    adopt_id=spec.import_id,
                    opts=opts,
                )
            else:
                resource = SynapseAcl(
                    spec.logical_name,
                    entity_id=entity_id(props["resource"]),
                    grants=[
                        {
                            "principal_id": principal_id(g["principal"]),
                            "access_type": list(g["access_type"]),
                        }
                        for g in props["grants"]
                    ],
                    opts=opts,
                )
            created[spec.logical_name] = resource
            pulumi.export(spec.logical_name, resource.id)
        return created

    return program
