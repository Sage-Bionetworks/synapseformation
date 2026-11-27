"""Turn a synapseformation template into a Pulumi program.

Template format::

    version: 1
    name: "My study"
    resources:
      <logical_name>:
        type: team | project | folder | acl | schema_organization | json_schema
              | schema_binding | file_based_metadata_task
              | record_based_metadata_task
        import: syn123        # optional: adopt an existing team/project/folder
                              # (or organization, by name)
        protect: true         # optional: refuse to delete
        properties: {...}

References use ``<type>.<logical_name>`` (``folder.raw_data``). Entity
references may also be an existing Synapse ID (``syn123``), schema
references may be a registered schema URI, organization references may be
an existing organization name, and principals may be a numeric principal
ID or ``PUBLIC`` / ``AUTHENTICATED_USERS``.
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import pulumi
from synapseclient.models import ViewTypeMask

from .providers import (
    FileBasedMetadataTask,
    RecordBasedMetadataTask,
    SynapseAcl,
    SynapseFolder,
    SynapseJsonSchema,
    SynapseProject,
    SynapseSchemaBinding,
    SynapseSchemaOrganization,
    SynapseTeam,
    without_schema_id,
)

ENTITY_TYPES = {"project", "folder"}
TASK_TYPES = {"file_based_metadata_task", "record_based_metadata_task"}
ADOPTABLE_TYPES = {"team", "project", "folder", "schema_organization"}
REQUIRED_PROPERTIES = {
    "team": ["name"],
    "project": ["name"],
    "folder": ["name", "parent"],
    "acl": ["resource", "grants"],
    "schema_organization": ["name"],
    "json_schema": ["organization", "name", "version"],
    "schema_binding": ["resource", "schema"],
    "file_based_metadata_task": ["folder", "curation_task_name", "instructions"],
    "record_based_metadata_task": [
        "folder",
        "record_set_name",
        "record_set_description",
        "curation_task_name",
        "upsert_keys",
        "instructions",
        "schema",
    ],
}
RESOURCE_TYPES = set(REQUIRED_PROPERTIES)
WELL_KNOWN_PRINCIPALS = {"AUTHENTICATED_USERS": 273948, "PUBLIC": 273949}
AUTHORIZATION_MODES = {"SESSION_OWNER", "SOURCE_BENEFACTOR"}
SYNAPSE_ID = re.compile(r"^syn\d+$")
SCHEMA_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
SCHEMA_REF_PREFIX = "json_schema."
ORG_REF_PREFIX = "schema_organization."
ORG_NAME_PART = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
#: Stack output recording which Synapse (production or staging) a stack manages.
ENVIRONMENT_OUTPUT = "_synapse_environment"


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
    # json_schema only: the schema document, loaded from ``path`` or ``schema``.
    schema_body: Optional[dict] = None


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


def _schema_ref(schema: Any, where: str) -> Optional[str]:
    """``json_schema.<name>`` or a literal schema URI (returns None)."""
    text = str(schema)
    if text.startswith(SCHEMA_REF_PREFIX):
        return _parse_ref(text, {"json_schema"}, where)
    if not text or text.isspace():
        raise TemplateError(f"{where}: schema must be json_schema.<name> or a URI")
    return None


def _org_ref(organization: Any, where: str) -> Optional[str]:
    """``schema_organization.<name>`` or an existing organization name (None)."""
    text = str(organization)
    if text.startswith(ORG_REF_PREFIX):
        return _parse_ref(text, {"schema_organization"}, where)
    return None


def _check_org_name(name: Any, where: str) -> None:
    """Synapse's rules for organization names."""
    text = str(name)
    if (
        not 6 <= len(text) <= 250
        or "sagebionetworks" in text.lower()
        or not all(ORG_NAME_PART.match(part) for part in text.split("."))
    ):
        raise TemplateError(
            f"{where}: invalid organization name '{text}'; use 6 to 250 "
            "characters in dot-separated parts that start with a letter and "
            "contain only letters and digits (and not 'sagebionetworks')"
        )


def _grant_deps(grants: Any, where: str) -> list[str]:
    """Validate a list of grants and return the teams it references."""
    if not isinstance(grants, list):
        raise TemplateError(f"{where}.grants: must be a list")
    deps = []
    for i, grant in enumerate(grants):
        gwhere = f"{where}.grants[{i}]"
        if (
            not isinstance(grant, dict)
            or "principal" not in grant
            or "access_type" not in grant
        ):
            raise TemplateError(f"{gwhere}: needs principal and access_type")
        ref = _principal_ref(grant["principal"], gwhere)
        if ref:
            deps.append(ref)
    return deps


def view_type_mask(value: Any, where: str = "view_type_mask") -> int:
    """Turn ``FILE``, ``[FILE, FOLDER]`` or an integer into a view type mask."""
    if isinstance(value, bool):
        raise TemplateError(f"{where}: expected a view type name, list or integer")
    if isinstance(value, int):
        return value
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not names:
        raise TemplateError(f"{where}: expected a view type name, list or integer")
    mask = 0
    for name in names:
        try:
            mask |= ViewTypeMask[str(name).upper()].value
        except KeyError:
            valid = ", ".join(m.name for m in ViewTypeMask)
            raise TemplateError(
                f"{where}: unknown view type '{name}'; expected one of {valid}"
            ) from None
    return mask


def _string_list(value: Any, where: str, allow_empty: bool = True) -> list[str]:
    if (
        not isinstance(value, list)
        or not all(isinstance(v, str) and v for v in value)
        or (not allow_empty and not value)
    ):
        qualifier = "" if allow_empty else "non-empty "
        raise TemplateError(f"{where}: must be a {qualifier}list of names")
    return value


def _load_schema_body(props: dict, base_dir: Path, where: str) -> dict:
    if ("path" in props) == ("schema" in props):
        raise TemplateError(f"{where}: give exactly one of 'path' or 'schema'")
    if "schema" in props:
        body = props["schema"]
    else:
        path = Path(props["path"])
        if not path.is_absolute():
            path = base_dir / path
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise TemplateError(f"{where}: schema file '{path}' not found") from None
        except json.JSONDecodeError as error:
            raise TemplateError(
                f"{where}: schema file '{path}' is not valid JSON: {error}"
            ) from None
    if not isinstance(body, dict):
        raise TemplateError(f"{where}: the schema must be a JSON object")
    return without_schema_id(body)


def _check_task(rtype: str, props: dict, where: str) -> None:
    mode = props.get("authorization_mode")
    if mode is not None and str(mode).upper() not in AUTHORIZATION_MODES:
        raise TemplateError(
            f"{where}: authorization_mode must be one of "
            f"{', '.join(sorted(AUTHORIZATION_MODES))}"
        )
    if props.get("column_order") is not None:
        _string_list(props["column_order"], f"{where}.column_order")
    if rtype == "file_based_metadata_task":
        if "view_type_mask" in props:
            view_type_mask(props["view_type_mask"], f"{where}.view_type_mask")
    else:
        _string_list(props["upsert_keys"], f"{where}.upsert_keys", allow_empty=False)


def parse_template(config: dict, base_dir: Optional[Path] = None) -> list[ResourceSpec]:
    """Validate a template and return its resources in dependency order.

    ``base_dir`` is where relative ``json_schema`` paths are looked up,
    normally the template's directory.
    """
    base_dir = Path(base_dir or ".")
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
        if body.get("import") and rtype not in ADOPTABLE_TYPES:
            raise TemplateError(f"{where}: 'import' is not supported for {rtype}")
        if (
            body.get("import")
            and rtype == "schema_organization"
            and body["import"] != props["name"]
        ):
            raise TemplateError(
                f"{where}: 'import' must be the organization name, '{props['name']}'"
            )
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
            spec.depends_on = deps + _grant_deps(props["grants"], where)
        elif rtype == "schema_organization":
            _check_org_name(props["name"], where)
            spec.depends_on = _grant_deps(props.get("grants") or [], where)
        elif rtype == "json_schema":
            if (
                not SCHEMA_VERSION.match(str(props["version"]))
                or str(props["version"]) == "0.0.0"
            ):
                raise TemplateError(
                    f"{where}: version must look like 1.0.0 (0.0.1 or higher)"
                )
            spec.schema_body = _load_schema_body(props, base_dir, where)
            org = _org_ref(props["organization"], where)
            if org is None:
                _check_org_name(props["organization"], where)
            spec.depends_on = _optional([org])
        elif rtype == "schema_binding":
            deps = _deps([props["resource"]], ENTITY_TYPES, where)
            spec.depends_on = deps + _optional([_schema_ref(props["schema"], where)])
        elif rtype in TASK_TYPES:
            _check_task(rtype, props, where)
            deps = _deps([props["folder"]], ENTITY_TYPES, where)
            if props.get("schema") is not None:
                deps.append(_schema_ref(props["schema"], where))
            if props.get("assignee") is not None:
                deps.append(_principal_ref(props["assignee"], f"{where}.assignee"))
            spec.depends_on = _optional(deps)
        specs[name] = spec

    for spec in specs.values():
        for dep in spec.depends_on:
            if dep not in specs:
                raise TemplateError(
                    f"resources.{spec.logical_name}: references unknown resource "
                    f"'{dep}'"
                )
    _check_ref_types(specs)
    return _topological_order(specs)


def _deps(refs: list[str], allowed: set[str], where: str) -> list[str]:
    return [n for n in (_parse_ref(r, allowed, where) for r in refs) if n]


def _optional(names: list[Optional[str]]) -> list[str]:
    return [n for n in names if n]


def _check_ref_types(specs: dict[str, ResourceSpec]) -> None:
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

    def check_schema(ref: Any, where: str) -> None:
        if ref is not None and str(ref).startswith(SCHEMA_REF_PREFIX):
            check(ref, where)

    for spec in specs.values():
        where = f"resources.{spec.logical_name}"
        props = spec.properties
        if spec.type == "folder":
            check(props["parent"], where)
        elif spec.type in ("acl", "schema_organization"):
            if spec.type == "acl":
                check(props["resource"], where)
            for grant in props.get("grants") or []:
                check(grant["principal"], where)
        elif spec.type == "json_schema":
            if str(props["organization"]).startswith(ORG_REF_PREFIX):
                check(props["organization"], where)
        elif spec.type == "schema_binding":
            check(props["resource"], where)
            check_schema(props["schema"], where)
        elif spec.type in TASK_TYPES:
            check(props["folder"], where)
            check_schema(props.get("schema"), where)
            if props.get("assignee") is not None:
                check(props["assignee"], where)


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


def build_program(
    config: dict,
    base_dir: Optional[Path] = None,
    environment: str = "production",
) -> Callable[[], dict[str, pulumi.Resource]]:
    """Return a Pulumi program function for the template.

    ``environment`` (``production`` or ``staging``) is saved as a stack
    output so the CLI can refuse to point a stack at the other Synapse.
    """
    specs = parse_template(config, base_dir)

    def program() -> dict[str, pulumi.Resource]:
        created: dict[str, pulumi.Resource] = {}
        pulumi.export(ENVIRONMENT_OUTPUT, environment)

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

        def schema_uri(ref: Any) -> Optional[pulumi.Input[str]]:
            if ref is None:
                return None
            if str(ref).startswith(SCHEMA_REF_PREFIX):
                return created[str(ref)[len(SCHEMA_REF_PREFIX) :]].id
            return str(ref)

        def grants(raw: list[dict]) -> list[dict]:
            return [
                {
                    "principal_id": principal_id(g["principal"]),
                    "access_type": list(g["access_type"]),
                }
                for g in raw or []
            ]

        def organization(ref: Any) -> pulumi.Input[str]:
            if str(ref).startswith(ORG_REF_PREFIX):
                return created[str(ref)[len(ORG_REF_PREFIX) :]].id
            return str(ref)

        def assignee(principal: Any) -> Optional[pulumi.Input[str]]:
            if principal is None:
                return None
            return pulumi.Output.from_input(principal_id(principal)).apply(str)

        def authorization_mode(props: dict) -> Optional[str]:
            mode = props.get("authorization_mode")
            return str(mode).upper() if mode is not None else None

        for spec in specs:
            props = spec.properties
            logical = spec.logical_name
            opts = pulumi.ResourceOptions(protect=spec.protect)
            if spec.type == "team":
                resource = SynapseTeam(
                    logical,
                    name=props["name"],
                    description=props.get("description"),
                    can_public_join=bool(props.get("can_public_join", False)),
                    adopt_id=spec.import_id,
                    opts=opts,
                )
            elif spec.type == "project":
                resource = SynapseProject(
                    logical,
                    name=props["name"],
                    description=props.get("description"),
                    adopt_id=spec.import_id,
                    opts=opts,
                )
            elif spec.type == "folder":
                resource = SynapseFolder(
                    logical,
                    name=props["name"],
                    parent_id=entity_id(props["parent"]),
                    description=props.get("description"),
                    adopt_id=spec.import_id,
                    opts=opts,
                )
            elif spec.type == "acl":
                resource = SynapseAcl(
                    logical,
                    entity_id=entity_id(props["resource"]),
                    grants=grants(props["grants"]),
                    opts=opts,
                )
            elif spec.type == "schema_organization":
                resource = SynapseSchemaOrganization(
                    logical,
                    name=props["name"],
                    grants=grants(props.get("grants")),
                    adopt=bool(spec.import_id),
                    opts=opts,
                )
            elif spec.type == "json_schema":
                resource = SynapseJsonSchema(
                    logical,
                    organization=organization(props["organization"]),
                    name=props["name"],
                    version=str(props["version"]),
                    body=spec.schema_body,
                    opts=opts,
                )
            elif spec.type == "schema_binding":
                resource = SynapseSchemaBinding(
                    logical,
                    entity_id=entity_id(props["resource"]),
                    schema_uri=schema_uri(props["schema"]),
                    enable_derived_annotations=bool(
                        props.get("enable_derived_annotations", False)
                    ),
                    opts=opts,
                )
            elif spec.type == "file_based_metadata_task":
                resource = FileBasedMetadataTask(
                    logical,
                    folder_id=entity_id(props["folder"]),
                    curation_task_name=props["curation_task_name"],
                    instructions=props["instructions"],
                    schema_uri=schema_uri(props.get("schema")),
                    enable_derived_annotations=bool(
                        props.get("enable_derived_annotations", False)
                    ),
                    entity_view_name=props.get("entity_view_name", "JSON Schema view"),
                    view_type_mask=view_type_mask(props.get("view_type_mask", "FILE")),
                    column_order=props.get("column_order"),
                    assignee_principal_id=assignee(props.get("assignee")),
                    authorization_mode=authorization_mode(props),
                    opts=opts,
                )
            else:
                resource = RecordBasedMetadataTask(
                    logical,
                    folder_id=entity_id(props["folder"]),
                    record_set_name=props["record_set_name"],
                    record_set_description=props["record_set_description"],
                    curation_task_name=props["curation_task_name"],
                    upsert_keys=list(props["upsert_keys"]),
                    instructions=props["instructions"],
                    schema_uri=schema_uri(props["schema"]),
                    bind_schema_to_record_set=bool(
                        props.get("bind_schema_to_record_set", True)
                    ),
                    enable_derived_annotations=bool(
                        props.get("enable_derived_annotations", False)
                    ),
                    assignee_principal_id=assignee(props.get("assignee")),
                    authorization_mode=authorization_mode(props),
                    column_order=props.get("column_order"),
                    opts=opts,
                )
            created[logical] = resource
            if isinstance(resource, pulumi.ComponentResource):
                pulumi.export(logical, resource.outputs)
            else:
                pulumi.export(logical, resource.id)
        return created

    return program
