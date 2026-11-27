"""Pulumi dynamic providers for Synapse resources.

Each provider implements create/read/update/delete/diff with the
``synapseclient`` object models (``synapseclient.models``). Pulumi's engine
handles state, dependency ordering, previews, refresh (drift detection),
targeted deletes and import.

A few operations go below the models, to the ``synapseclient.api`` functions
the models themselves call:

- Team updates. ``Team`` has ``create``/``get``/``delete`` but no update, so
  renaming a team uses ``PUT /team``.
- ACLs. ``set_permissions()`` writes one principal per request, and on an
  entity that inherits its permissions it creates a local ACL holding only
  that principal, which drops everyone else (including the creator's admin
  access). ``AclProvider`` copies the inherited ACL down first and writes all
  grants in one request.
- Schema bindings and schema bodies. These endpoints take any entity ID or
  schema URI, so there is no need to load the right model class first.

Dynamic providers are serialized with dill and executed in a separate
process, so providers must not hold a logged-in client on ``self``. They get
one from :func:`get_client`, which logs in from ``SYNAPSE_AUTH_TOKEN`` or
``~/.synapseConfig``, against Synapse staging if ``SYNAPSEFORMATION_STAGING``
is set.
"""

from __future__ import annotations

import copy
import csv
import json
import os
import tempfile
from typing import Any, Optional

import pulumi
from pulumi.dynamic import (
    CheckFailure,
    CheckResult,
    CreateResult,
    DiffResult,
    ReadResult,
    Resource,
    ResourceProvider,
    UpdateResult,
)
from synapseclient import api as synapse_api
from synapseclient import operations
from synapseclient.core.async_utils import wrap_async_to_sync
from synapseclient.extensions.curator.utils import (
    project_id_from_entity_id,
    resolve_column_order_list,
)
from synapseclient.models import (
    CurationTask,
    EntityView,
    FileBasedMetadataTaskProperties,
    Folder,
    JSONSchema,
    Organization,
    Project,
    RecordBasedMetadataTaskProperties,
    RecordSet,
    Team,
)

PROJECT_TYPE = "org.sagebionetworks.repo.model.Project"
FOLDER_TYPE = "org.sagebionetworks.repo.model.Folder"

#: Set to ``1`` to send every request to Synapse staging instead of production.
STAGING_ENV_VAR = "SYNAPSEFORMATION_STAGING"

_CLIENT = None


def use_staging() -> bool:
    return os.environ.get(STAGING_ENV_VAR, "").lower() in {"1", "true", "yes"}


def get_client():
    """Return a logged-in Synapse client, created once per process."""
    global _CLIENT
    if _CLIENT is None:
        import synapseclient
        from synapseclient.client import STAGING_ENDPOINTS

        from . import __version__

        syn = synapseclient.Synapse(
            skip_checks=True,
            silent=True,
            user_agent=f"synapseformation/{__version__}",
            **(STAGING_ENDPOINTS if use_staging() else {}),
        )
        syn.login(silent=True)
        _CLIENT = syn
    return _CLIENT


def _run(coroutine):
    """Run one of the async ``synapseclient.api`` functions."""
    return wrap_async_to_sync(coroutine)


def _is_not_found(error: Exception) -> bool:
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None) == 404


def _changed(olds: dict, news: dict, keys: list[str]) -> list[str]:
    return [k for k in keys if olds.get(k) != news.get(k)]


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _inputs(outs: dict, keys: list[str]) -> dict:
    """The input properties to record after a refresh: ``keys`` from ``outs``."""
    return {k: outs.get(k) for k in keys}


# --------------------------------------------------------------------------
# Entities (projects and folders)
# --------------------------------------------------------------------------

ENTITY_KEYS = ["name", "description", "parent_id"]


def _entity_class(concrete_type: Optional[str]) -> type:
    return Project if concrete_type == PROJECT_TYPE else Folder


def _entity_outs(entity: Project | Folder) -> dict:
    is_project = isinstance(entity, Project)
    return {
        "concrete_type": PROJECT_TYPE if is_project else FOLDER_TYPE,
        "name": entity.name,
        "description": entity.description,
        # Synapse sets a parent on projects; it is not user-managed.
        "parent_id": None if is_project else entity.parent_id,
    }


class EntityProvider(ResourceProvider):
    """Manages a Synapse project or folder.

    If ``adopt_id`` is set, create takes over that existing entity and
    updates it to match the template instead of making a new one. (Pulumi's
    ``import`` resource option does not work with dynamic providers.)
    """

    def create(self, props: dict) -> CreateResult:
        syn = get_client()
        cls = _entity_class(props["concrete_type"])
        if props.get("adopt_id"):
            existing = operations.get(
                props["adopt_id"],
                file_options=operations.FileOptions(download_file=False),
                synapse_client=syn,
            )
            if not isinstance(existing, cls):
                raise ValueError(
                    f"{props['adopt_id']} is a {type(existing).__name__}, "
                    f"not a {cls.__name__}"
                )
            result = self.update(existing.id, {}, props)
            return CreateResult(id_=existing.id, outs=result.outs)
        entity = cls(
            name=props["name"],
            description=props.get("description"),
            # Fail on a name clash rather than silently taking over the
            # existing entity; use ``import`` for that.
            create_or_update=False,
        )
        if cls is Folder:
            entity.parent_id = props["parent_id"]
        entity = entity.store(synapse_client=syn)
        return CreateResult(id_=entity.id, outs=_entity_outs(entity))

    def read(self, id_: str, props: dict) -> ReadResult:
        syn = get_client()
        cls = _entity_class(props.get("concrete_type"))
        try:
            entity = cls(id=id_).get(synapse_client=syn)
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                return ReadResult(id_=None, outs={})
            raise
        outs = _entity_outs(entity)
        return ReadResult(id_=id_, outs=outs, inputs=outs)

    def diff(self, id_: str, olds: dict, news: dict) -> DiffResult:
        replaces = _changed(olds, news, ["concrete_type"])
        changes = _changed(olds, news, ENTITY_KEYS)
        return DiffResult(
            changes=bool(changes or replaces),
            replaces=replaces,
            delete_before_replace=bool(replaces),
        )

    def update(self, id_: str, olds: dict, news: dict) -> UpdateResult:
        syn = get_client()
        cls = _entity_class(news["concrete_type"])
        entity = cls(id=id_).get(synapse_client=syn)
        entity.name = news["name"]
        entity.description = news.get("description")
        if cls is Folder and news.get("parent_id"):
            entity.parent_id = news["parent_id"]
        entity = entity.store(synapse_client=syn)
        return UpdateResult(outs=_entity_outs(entity))

    def delete(self, id_: str, props: dict) -> None:
        syn = get_client()
        cls = _entity_class(props.get("concrete_type"))
        try:
            cls(id=id_).delete(synapse_client=syn)
        except Exception as error:  # noqa: BLE001
            # Already gone, e.g. trashed along with its parent project.
            if not _is_not_found(error):
                raise


class SynapseProject(Resource):
    """A Synapse project."""

    def __init__(
        self,
        resource_name: str,
        name: pulumi.Input[str],
        description: Optional[pulumi.Input[str]] = None,
        adopt_id: Optional[str] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            EntityProvider(),
            resource_name,
            {
                "concrete_type": PROJECT_TYPE,
                "name": name,
                "description": description,
                "parent_id": None,
                "adopt_id": adopt_id,
            },
            opts,
        )


class SynapseFolder(Resource):
    """A Synapse folder."""

    def __init__(
        self,
        resource_name: str,
        name: pulumi.Input[str],
        parent_id: pulumi.Input[str],
        description: Optional[pulumi.Input[str]] = None,
        adopt_id: Optional[str] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            EntityProvider(),
            resource_name,
            {
                "concrete_type": FOLDER_TYPE,
                "name": name,
                "description": description,
                "parent_id": parent_id,
                "adopt_id": adopt_id,
            },
            opts,
        )


# --------------------------------------------------------------------------
# Teams
# --------------------------------------------------------------------------

TEAM_KEYS = ["name", "description", "can_public_join"]


def _team_outs(team: Team) -> dict:
    return {
        "name": team.name,
        "description": team.description,
        "can_public_join": bool(team.can_public_join),
    }


class TeamProvider(ResourceProvider):
    """Manages a Synapse team. ``adopt_id`` works as for entities."""

    def create(self, props: dict) -> CreateResult:
        syn = get_client()
        if props.get("adopt_id"):
            team_id = str(props["adopt_id"])
            result = self.update(team_id, {}, props)
            return CreateResult(id_=team_id, outs=result.outs)
        team = Team(
            name=props["name"],
            description=props.get("description"),
            can_public_join=bool(props.get("can_public_join", False)),
        ).create(synapse_client=syn)
        return CreateResult(id_=str(team.id), outs=_team_outs(team))

    def read(self, id_: str, props: dict) -> ReadResult:
        syn = get_client()
        try:
            team = Team(id=int(id_)).get(synapse_client=syn)
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                return ReadResult(id_=None, outs={})
            raise
        outs = _team_outs(team)
        return ReadResult(id_=id_, outs=outs, inputs=outs)

    def diff(self, id_: str, olds: dict, news: dict) -> DiffResult:
        return DiffResult(changes=bool(_changed(olds, news, TEAM_KEYS)))

    def update(self, id_: str, olds: dict, news: dict) -> UpdateResult:
        # The Team model cannot update a team, so send the PUT ourselves.
        syn = get_client()
        team = syn.restGET(f"/team/{id_}")
        team["name"] = news["name"]
        team["description"] = news.get("description")
        team["canPublicJoin"] = bool(news.get("can_public_join", False))
        team = syn.restPUT("/team", body=json.dumps(team))
        return UpdateResult(outs=_team_outs(Team().fill_from_dict(team)))

    def delete(self, id_: str, props: dict) -> None:
        syn = get_client()
        try:
            Team(id=int(id_)).delete(synapse_client=syn)
        except Exception as error:  # noqa: BLE001
            if not _is_not_found(error):
                raise


class SynapseTeam(Resource):
    """A Synapse team."""

    def __init__(
        self,
        resource_name: str,
        name: pulumi.Input[str],
        description: Optional[pulumi.Input[str]] = None,
        can_public_join: bool = False,
        adopt_id: Optional[str] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            TeamProvider(),
            resource_name,
            {
                "name": name,
                "description": description,
                "can_public_join": can_public_join,
                "adopt_id": adopt_id,
            },
            opts,
        )


# --------------------------------------------------------------------------
# ACL grants
# --------------------------------------------------------------------------


def normalize_grants(grants: list[dict]) -> list[dict]:
    """Return grants with int principals and sorted, upper-cased access types."""
    normalized = {}
    for grant in grants or []:
        principal = int(grant["principal_id"])
        normalized[principal] = sorted({a.upper() for a in grant["access_type"]})
    return [
        {"principal_id": principal, "access_type": normalized[principal]}
        for principal in sorted(normalized)
    ]


def _normalize_input_grants(news: dict) -> dict:
    """Store grants in the normal form read() reports.

    Otherwise a refresh shows a change when only order or case differs.
    """
    try:
        return dict(news, grants=normalize_grants(news.get("grants")))
    except (TypeError, ValueError):
        return news  # a principal is not known yet during preview


def _benefactor_id(syn, entity_id: str) -> str:
    return _run(synapse_api.get_entity_benefactor(entity_id, synapse_client=syn)).id


def _get_local_acl(syn, entity_id: str) -> Optional[dict]:
    """Return the entity's own ACL, or None if it inherits from a benefactor."""
    if _benefactor_id(syn, entity_id) != entity_id:
        return None
    return _run(synapse_api.get_entity_acl(entity_id, synapse_client=syn))


def _apply_grants(acl: dict, grants: list[dict], remove: set[int]) -> dict:
    """Set ``grants`` on ``acl`` and drop principals in ``remove``."""
    managed = {g["principal_id"]: g["access_type"] for g in grants}
    entries = []
    for entry in acl.get("resourceAccess", []):
        principal = int(entry["principalId"])
        if principal in managed or principal in remove:
            continue
        entries.append(entry)
    for principal, access in managed.items():
        if access:
            entries.append({"principalId": principal, "accessType": access})
    acl["resourceAccess"] = entries
    return acl


class AclProvider(ResourceProvider):
    """Manages grants for specific principals on an entity's local ACL.

    Principals not listed in the template are left alone, so the creator's
    admin access is never removed. If this resource had to create the local
    ACL (the entity was inheriting), deleting it restores inheritance.
    """

    def check(self, olds: dict, news: dict) -> CheckResult:
        return CheckResult(_normalize_input_grants(news), [])

    def create(self, props: dict) -> CreateResult:
        syn = get_client()
        entity_id = props["entity_id"]
        grants = normalize_grants(props["grants"])
        acl = _get_local_acl(syn, entity_id)
        created_local_acl = acl is None
        if created_local_acl:
            benefactor = _benefactor_id(syn, entity_id)
            inherited = _run(synapse_api.get_entity_acl(benefactor, synapse_client=syn))
            acl = {"id": entity_id, "resourceAccess": inherited["resourceAccess"]}
            acl = _apply_grants(acl, grants, remove=set())
            _run(synapse_api.post_entity_acl(entity_id, acl, synapse_client=syn))
        else:
            acl = _apply_grants(acl, grants, remove=set())
            _run(synapse_api.put_entity_acl(entity_id, acl, synapse_client=syn))
        outs = {
            "entity_id": entity_id,
            "grants": grants,
            "created_local_acl": created_local_acl,
        }
        return CreateResult(id_=f"{entity_id}/acl", outs=outs)

    def read(self, id_: str, props: dict) -> ReadResult:
        syn = get_client()
        entity_id = props.get("entity_id") or id_.split("/")[0]
        managed = {g["principal_id"] for g in normalize_grants(props.get("grants"))}
        try:
            acl = _get_local_acl(syn, entity_id)
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                return ReadResult(id_=None, outs={})
            raise
        found = []
        for entry in (acl or {}).get("resourceAccess", []):
            principal = int(entry["principalId"])
            if not managed or principal in managed:
                found.append(
                    {"principal_id": principal, "access_type": entry["accessType"]}
                )
        outs = {
            "entity_id": entity_id,
            "grants": normalize_grants(found),
            "created_local_acl": props.get("created_local_acl", False),
        }
        inputs = {"entity_id": entity_id, "grants": outs["grants"]}
        return ReadResult(id_=id_, outs=outs, inputs=inputs)

    def diff(self, id_: str, olds: dict, news: dict) -> DiffResult:
        replaces = _changed(olds, news, ["entity_id"])
        grants_changed = normalize_grants(olds.get("grants")) != normalize_grants(
            news.get("grants")
        )
        return DiffResult(
            changes=bool(replaces or grants_changed),
            replaces=replaces,
            delete_before_replace=bool(replaces),
        )

    def update(self, id_: str, olds: dict, news: dict) -> UpdateResult:
        syn = get_client()
        entity_id = news["entity_id"]
        grants = normalize_grants(news["grants"])
        old_principals = {g["principal_id"] for g in normalize_grants(olds["grants"])}
        removed = old_principals - {g["principal_id"] for g in grants}
        created_local_acl = olds.get("created_local_acl", False)
        acl = _get_local_acl(syn, entity_id)
        if acl is None:
            # Local ACL was removed outside synapseformation; recreate it.
            result = self.create(news)
            return UpdateResult(outs=result.outs)
        acl = _apply_grants(acl, grants, remove=removed)
        _run(synapse_api.put_entity_acl(entity_id, acl, synapse_client=syn))
        return UpdateResult(
            outs={
                "entity_id": entity_id,
                "grants": grants,
                "created_local_acl": created_local_acl,
            }
        )

    def delete(self, id_: str, props: dict) -> None:
        syn = get_client()
        entity_id = props["entity_id"]
        try:
            acl = _get_local_acl(syn, entity_id)
            if acl is None:
                return
            if props.get("created_local_acl"):
                _run(synapse_api.delete_entity_acl(entity_id, synapse_client=syn))
                return
            managed = {g["principal_id"] for g in normalize_grants(props["grants"])}
            acl = _apply_grants(acl, [], remove=managed)
            _run(synapse_api.put_entity_acl(entity_id, acl, synapse_client=syn))
        except Exception as error:  # noqa: BLE001
            if not _is_not_found(error):
                raise


class SynapseAcl(Resource):
    """Grants for a set of principals on one entity."""

    def __init__(
        self,
        resource_name: str,
        entity_id: pulumi.Input[str],
        grants: pulumi.Input[list[dict[str, Any]]],
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            AclProvider(),
            resource_name,
            {"entity_id": entity_id, "grants": grants, "created_local_acl": None},
            opts,
        )


# --------------------------------------------------------------------------
# JSON schema organizations
# --------------------------------------------------------------------------


class SchemaOrganizationProvider(ResourceProvider):
    """Manages a JSON schema organization and grants on its ACL.

    The resource ID is the organization name, which Synapse cannot change, so
    a new name replaces the organization. As with ``acl`` resources, only the
    principals listed in ``grants`` are managed; the creator keeps their
    access. Synapse will not delete an organization that still has schemas.
    """

    def check(self, olds: dict, news: dict) -> CheckResult:
        return CheckResult(_normalize_input_grants(news), [])

    def create(self, props: dict) -> CreateResult:
        syn = get_client()
        org = Organization(name=props["name"])
        if props.get("adopt_id"):
            org = org.get(synapse_client=syn)
        else:
            org = org.store(synapse_client=syn)
        grants = normalize_grants(props.get("grants"))
        if grants:
            self._write_grants(org, grants, remove=set())
        return CreateResult(id_=org.name, outs=self._outs(org, grants))

    def read(self, id_: str, props: dict) -> ReadResult:
        syn = get_client()
        try:
            org = Organization(name=id_).get(synapse_client=syn)
            acl = org.get_acl(synapse_client=syn)
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                return ReadResult(id_=None, outs={})
            raise
        managed = {g["principal_id"] for g in normalize_grants(props.get("grants"))}
        found = [
            {"principal_id": int(e["principalId"]), "access_type": e["accessType"]}
            for e in acl.get("resourceAccess", [])
            if int(e["principalId"]) in managed
        ]
        outs = self._outs(org, normalize_grants(found))
        return ReadResult(id_=id_, outs=outs, inputs=_inputs(outs, ["name", "grants"]))

    def diff(self, id_: str, olds: dict, news: dict) -> DiffResult:
        replaces = _changed(olds, news, ["name"])
        grants_changed = normalize_grants(olds.get("grants")) != normalize_grants(
            news.get("grants")
        )
        return DiffResult(changes=bool(replaces or grants_changed), replaces=replaces)

    def update(self, id_: str, olds: dict, news: dict) -> UpdateResult:
        org = Organization(name=id_).get(synapse_client=get_client())
        grants = normalize_grants(news.get("grants"))
        old_principals = {
            g["principal_id"] for g in normalize_grants(olds.get("grants"))
        }
        removed = old_principals - {g["principal_id"] for g in grants}
        self._write_grants(org, grants, remove=removed)
        return UpdateResult(outs=self._outs(org, grants))

    def delete(self, id_: str, props: dict) -> None:
        try:
            Organization(name=id_).delete(synapse_client=get_client())
        except Exception as error:  # noqa: BLE001
            if not _is_not_found(error):
                raise

    @staticmethod
    def _write_grants(org: Organization, grants: list[dict], remove: set[int]) -> None:
        syn = get_client()
        acl = _apply_grants(org.get_acl(synapse_client=syn), grants, remove)
        _run(
            synapse_api.update_organization_acl(
                org.id, acl["resourceAccess"], acl["etag"], synapse_client=syn
            )
        )

    @staticmethod
    def _outs(org: Organization, grants: list[dict]) -> dict:
        return {"name": org.name, "organization_id": org.id, "grants": grants}


class SynapseSchemaOrganization(Resource):
    """A JSON schema organization. ``id`` is its name."""

    def __init__(
        self,
        resource_name: str,
        name: str,
        grants: Optional[pulumi.Input[list[dict[str, Any]]]] = None,
        adopt: bool = False,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            SchemaOrganizationProvider(),
            resource_name,
            {"name": name, "grants": grants or [], "adopt_id": name if adopt else None},
            opts,
        )


# --------------------------------------------------------------------------
# JSON schemas (curator: register_jsonschema)
# --------------------------------------------------------------------------

JSON_SCHEMA_KEYS = ["organization", "name", "version", "body"]


def schema_uri(organization: str, name: str, version: str) -> str:
    """The URI Synapse gives a registered schema version."""
    return f"{organization}-{name}-{version}"


def without_schema_id(body: Any) -> Any:
    """Drop the top-level ``$id``; Synapse sets it when a schema is registered."""
    if isinstance(body, dict):
        return {k: v for k, v in body.items() if k != "$id"}
    return body


def _canonical(body: Any) -> str:
    return json.dumps(without_schema_id(body), sort_keys=True)


class JsonSchemaProvider(ResourceProvider):
    """Registers one version of a JSON schema in a Synapse organization.

    Schema versions cannot be changed once registered, so changing the body
    requires a new ``version``. Bumping the version registers the new one
    and then deletes the old one. The resource ID is the schema URI, e.g.
    ``my.org-Biospecimen-1.0.0``.
    """

    def check(self, olds: dict, news: dict) -> CheckResult:
        failures = []
        same_version = olds and not _changed(
            olds, news, ["organization", "name", "version"]
        )
        if same_version and _canonical(olds.get("body")) != _canonical(
            news.get("body")
        ):
            failures.append(
                CheckFailure(
                    "version",
                    "the schema body changed, but a registered schema version "
                    "cannot change; bump the version to publish the new body",
                )
            )
        return CheckResult(news, failures)

    def create(self, props: dict) -> CreateResult:
        syn = get_client()
        JSONSchema(name=props["name"], organization_name=props["organization"]).store(
            # store() writes "$id" into the body it is given.
            schema_body=copy.deepcopy(props["body"]),
            version=props["version"],
            synapse_client=syn,
        )
        uri = schema_uri(props["organization"], props["name"], props["version"])
        return CreateResult(id_=uri, outs=self._outs(props))

    def read(self, id_: str, props: dict) -> ReadResult:
        syn = get_client()
        try:
            _run(synapse_api.get_json_schema_body(id_, synapse_client=syn))
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                return ReadResult(id_=None, outs={})
            raise
        # Synapse rewrites "$id" in the stored body, so keep the template's
        # body rather than reporting that as drift.
        outs = self._outs(props)
        return ReadResult(id_=id_, outs=outs, inputs=_inputs(outs, JSON_SCHEMA_KEYS))

    def diff(self, id_: str, olds: dict, news: dict) -> DiffResult:
        replaces = _changed(olds, news, ["organization", "name", "version"])
        if _canonical(olds.get("body")) != _canonical(news.get("body")):
            replaces.append("body")
        return DiffResult(changes=bool(replaces), replaces=replaces)

    def delete(self, id_: str, props: dict) -> None:
        syn = get_client()
        try:
            _run(synapse_api.delete_json_schema(id_, synapse_client=syn))
        except Exception as error:  # noqa: BLE001
            if not _is_not_found(error):
                raise

    @staticmethod
    def _outs(props: dict) -> dict:
        outs = {k: props.get(k) for k in JSON_SCHEMA_KEYS}
        outs["body"] = without_schema_id(outs["body"])
        outs["uri"] = schema_uri(props["organization"], props["name"], props["version"])
        return outs


class SynapseJsonSchema(Resource):
    """A registered JSON schema version. ``id`` is its URI."""

    def __init__(
        self,
        resource_name: str,
        organization: str,
        name: str,
        version: str,
        body: dict,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            JsonSchemaProvider(),
            resource_name,
            {
                "organization": organization,
                "name": name,
                "version": version,
                "body": body,
            },
            opts,
        )


# --------------------------------------------------------------------------
# Schema bindings (curator: bind_jsonschema)
# --------------------------------------------------------------------------


def _same_schema(declared: Optional[str], bound: Optional[str]) -> bool:
    """True if ``bound`` is ``declared``, or a version of an unversioned URI."""
    if not declared or not bound:
        return declared == bound
    return bound == declared or bound.startswith(f"{declared}-")


class SchemaBindingProvider(ResourceProvider):
    """Binds a JSON schema to a project, folder or record set."""

    def create(self, props: dict) -> CreateResult:
        self._bind(props)
        return CreateResult(id_=f"{props['entity_id']}/schema", outs=self._outs(props))

    def read(self, id_: str, props: dict) -> ReadResult:
        syn = get_client()
        entity_id = props.get("entity_id") or id_.split("/")[0]
        try:
            binding = _run(
                synapse_api.get_json_schema_from_entity(entity_id, synapse_client=syn)
            )
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                return ReadResult(id_=None, outs={})
            raise
        bound = binding["jsonSchemaVersionInfo"]["$id"]
        declared = props.get("schema_uri")
        outs = {
            "entity_id": entity_id,
            "schema_uri": declared if _same_schema(declared, bound) else bound,
            "enable_derived_annotations": bool(
                binding.get("enableDerivedAnnotations", False)
            ),
        }
        return ReadResult(id_=id_, outs=outs, inputs=outs)

    def diff(self, id_: str, olds: dict, news: dict) -> DiffResult:
        replaces = _changed(olds, news, ["entity_id"])
        changes = _changed(olds, news, ["schema_uri", "enable_derived_annotations"])
        return DiffResult(changes=bool(replaces or changes), replaces=replaces)

    def update(self, id_: str, olds: dict, news: dict) -> UpdateResult:
        self._bind(news)
        return UpdateResult(outs=self._outs(news))

    def delete(self, id_: str, props: dict) -> None:
        syn = get_client()
        try:
            _run(
                synapse_api.delete_json_schema_from_entity(
                    props["entity_id"], synapse_client=syn
                )
            )
        except Exception as error:  # noqa: BLE001
            if not _is_not_found(error):
                raise

    @staticmethod
    def _bind(props: dict) -> None:
        _run(
            synapse_api.bind_json_schema_to_entity(
                props["entity_id"],
                props["schema_uri"],
                enable_derived_annotations=bool(
                    props.get("enable_derived_annotations", False)
                ),
                synapse_client=get_client(),
            )
        )

    @staticmethod
    def _outs(props: dict) -> dict:
        return {
            "entity_id": props["entity_id"],
            "schema_uri": props["schema_uri"],
            "enable_derived_annotations": bool(
                props.get("enable_derived_annotations", False)
            ),
        }


class SynapseSchemaBinding(Resource):
    """A JSON schema bound to an entity."""

    def __init__(
        self,
        resource_name: str,
        entity_id: pulumi.Input[str],
        schema_uri: pulumi.Input[str],
        enable_derived_annotations: bool = False,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            SchemaBindingProvider(),
            resource_name,
            {
                "entity_id": entity_id,
                "schema_uri": schema_uri,
                "enable_derived_annotations": enable_derived_annotations,
            },
            opts,
        )


# --------------------------------------------------------------------------
# Record sets
# --------------------------------------------------------------------------

RECORD_SET_KEYS = ["name", "description", "parent_id", "upsert_keys"]


def record_set_columns(
    schema_body: dict, upsert_keys: list[str], column_order: Optional[list[str]]
) -> list[str]:
    """Columns for a new record set, as ``create_record_based_metadata_task``."""
    properties = list(schema_body.get("properties", {}))
    missing = [key for key in upsert_keys if key not in properties]
    if missing:
        raise ValueError(
            f"upsert_keys {missing} are not properties of the schema; upsert keys "
            "identify each row and must be columns defined in the schema"
        )
    return resolve_column_order_list(
        available_columns=properties,
        pinned_columns=list(upsert_keys),
        requested_columns=column_order,
    )


def _record_set_outs(record_set: RecordSet, props: dict) -> dict:
    return {
        "name": record_set.name,
        "description": record_set.description,
        "parent_id": record_set.parent_id,
        "upsert_keys": list(record_set.upsert_keys or []),
        # Only used to build the initial CSV; not read back from Synapse.
        "schema_uri": props.get("schema_uri"),
        "column_order": props.get("column_order"),
    }


class RecordSetProvider(ResourceProvider):
    """Manages a record set whose initial CSV has one column per schema property.

    The schema and column order only shape the empty CSV written at creation.
    After that the records belong to the curators, so changing either one
    does not rewrite or replace the record set.
    """

    def create(self, props: dict) -> CreateResult:
        syn = get_client()
        body = _run(
            synapse_api.get_json_schema_body(props["schema_uri"], synapse_client=syn)
        )
        columns = record_set_columns(
            body, props["upsert_keys"], props.get("column_order")
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "records.csv")
            with open(path, "w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(columns)
            record_set = RecordSet(
                name=props["name"],
                description=props.get("description"),
                parent_id=props["parent_id"],
                path=path,
                upsert_keys=list(props["upsert_keys"]),
                create_or_update=False,
            ).store(synapse_client=syn)
        return CreateResult(id_=record_set.id, outs=_record_set_outs(record_set, props))

    def read(self, id_: str, props: dict) -> ReadResult:
        try:
            record_set = self._get(id_)
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                return ReadResult(id_=None, outs={})
            raise
        outs = _record_set_outs(record_set, props)
        return ReadResult(id_=id_, outs=outs, inputs=dict(outs))

    def diff(self, id_: str, olds: dict, news: dict) -> DiffResult:
        return DiffResult(changes=bool(_changed(olds, news, RECORD_SET_KEYS)))

    def update(self, id_: str, olds: dict, news: dict) -> UpdateResult:
        record_set = self._get(id_)
        record_set.name = news["name"]
        record_set.description = news.get("description")
        record_set.parent_id = news["parent_id"]
        record_set.upsert_keys = list(news["upsert_keys"])
        # Editing metadata should not create a new version of the records.
        record_set.force_version = False
        record_set = record_set.store(synapse_client=get_client())
        return UpdateResult(outs=_record_set_outs(record_set, news))

    def delete(self, id_: str, props: dict) -> None:
        try:
            RecordSet(id=id_).delete(synapse_client=get_client())
        except Exception as error:  # noqa: BLE001
            if not _is_not_found(error):
                raise

    @staticmethod
    def _get(id_: str) -> RecordSet:
        return RecordSet(id=id_, download_file=False).get(synapse_client=get_client())


class SynapseRecordSet(Resource):
    """A record set seeded with the columns of a JSON schema."""

    def __init__(
        self,
        resource_name: str,
        name: pulumi.Input[str],
        parent_id: pulumi.Input[str],
        upsert_keys: list[str],
        schema_uri: pulumi.Input[str],
        description: Optional[pulumi.Input[str]] = None,
        column_order: Optional[list[str]] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            RecordSetProvider(),
            resource_name,
            {
                "name": name,
                "description": description,
                "parent_id": parent_id,
                "upsert_keys": upsert_keys,
                "schema_uri": schema_uri,
                "column_order": column_order,
            },
            opts,
        )


# --------------------------------------------------------------------------
# File views of a schema-bound folder
# --------------------------------------------------------------------------

SCHEMA_VIEW_REPLACE_KEYS = ["parent_id", "view_type_mask", "column_order", "schema_uri"]


def _schema_view_outs(view: EntityView, props: dict) -> dict:
    return {
        "name": view.name,
        "parent_id": view.parent_id,
        "view_type_mask": props.get("view_type_mask"),
        "column_order": props.get("column_order"),
        "schema_uri": props.get("schema_uri"),
    }


class SchemaViewProvider(ResourceProvider):
    """An entity view of a folder with one column per property of its schema.

    This is the view ``create_file_based_metadata_task`` builds. Its columns
    come from the schema bound to the folder when the view is created, so a
    new schema, view type or column order replaces the view. The view holds
    no data of its own; the annotations live on the files.
    """

    def create(self, props: dict) -> CreateResult:
        from synapseclient.extensions.curator.file_based_metadata_task import (
            _create_json_schema_entity_view,
        )

        view = _create_json_schema_entity_view(
            synapse_entity_id=props["parent_id"],
            entity_view_name=props["name"],
            view_type_mask=int(props["view_type_mask"]),
            column_order=props.get("column_order"),
            syn=get_client(),
        )
        return CreateResult(id_=view.id, outs=_schema_view_outs(view, props))

    def read(self, id_: str, props: dict) -> ReadResult:
        try:
            view = EntityView(id=id_).get(
                include_columns=False, synapse_client=get_client()
            )
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                return ReadResult(id_=None, outs={})
            raise
        outs = _schema_view_outs(view, props)
        return ReadResult(id_=id_, outs=outs, inputs=outs)

    def diff(self, id_: str, olds: dict, news: dict) -> DiffResult:
        replaces = _changed(olds, news, SCHEMA_VIEW_REPLACE_KEYS)
        changes = _changed(olds, news, ["name"])
        return DiffResult(
            changes=bool(replaces or changes),
            replaces=replaces,
            # The new view has the same name in the same folder.
            delete_before_replace=bool(replaces),
        )

    def update(self, id_: str, olds: dict, news: dict) -> UpdateResult:
        syn = get_client()
        # Load the columns too, so storing does not touch them.
        view = EntityView(id=id_).get(include_columns=True, synapse_client=syn)
        view.name = news["name"]
        view = view.store(synapse_client=syn)
        return UpdateResult(outs=_schema_view_outs(view, news))

    def delete(self, id_: str, props: dict) -> None:
        try:
            EntityView(id=id_).delete(synapse_client=get_client())
        except Exception as error:  # noqa: BLE001
            if not _is_not_found(error):
                raise


class SynapseSchemaView(Resource):
    """A file view whose columns come from the folder's bound JSON schema."""

    def __init__(
        self,
        resource_name: str,
        name: pulumi.Input[str],
        parent_id: pulumi.Input[str],
        view_type_mask: int = 1,
        column_order: Optional[list[str]] = None,
        schema_uri: Optional[pulumi.Input[str]] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            SchemaViewProvider(),
            resource_name,
            {
                "name": name,
                "parent_id": parent_id,
                "view_type_mask": view_type_mask,
                "column_order": column_order,
                "schema_uri": schema_uri,
            },
            opts,
        )


# --------------------------------------------------------------------------
# Curation tasks
# --------------------------------------------------------------------------

FILE_TASK = "file"
RECORD_TASK = "record"
TASK_REPLACE_KEYS = ["kind", "data_type", "folder_id"]
TASK_UPDATE_KEYS = [
    "instructions",
    "assignee_principal_id",
    "authorization_mode",
    "file_view_id",
    "record_set_id",
]


def _task_properties(props: dict):
    mode = props.get("authorization_mode")
    if props["kind"] == FILE_TASK:
        return FileBasedMetadataTaskProperties(
            upload_folder_id=props["folder_id"],
            file_view_id=props["file_view_id"],
            suggested_authorization_mode=mode,
        )
    return RecordBasedMetadataTaskProperties(
        record_set_id=props["record_set_id"],
        suggested_authorization_mode=mode,
    )


def _task_outs(task: CurationTask, props: dict) -> dict:
    task_props = task.task_properties
    outs = {
        "kind": props["kind"],
        "data_type": task.data_type,
        "project_id": task.project_id,
        "folder_id": props.get("folder_id"),
        "instructions": task.instructions,
        "assignee_principal_id": (
            str(task.assignee_principal_id) if task.assignee_principal_id else None
        ),
        "authorization_mode": _enum_value(
            getattr(task_props, "suggested_authorization_mode", None)
        ),
        "file_view_id": getattr(task_props, "file_view_id", None),
        "record_set_id": getattr(task_props, "record_set_id", None),
    }
    if isinstance(task_props, FileBasedMetadataTaskProperties):
        outs["folder_id"] = task_props.upload_folder_id
    return outs


class CurationTaskProvider(ResourceProvider):
    """Manages a file-based or record-based curation task.

    The task's project is worked out from ``folder_id``. Synapse allows one
    task per data type in a project, and ``CurationTask.store()`` reuses an
    existing task with the same data type, so a replacement deletes the old
    task first.
    """

    def create(self, props: dict) -> CreateResult:
        syn = get_client()
        task = CurationTask(
            data_type=props["data_type"],
            project_id=project_id_from_entity_id(
                props["folder_id"], synapse_client=syn
            ),
            instructions=props["instructions"],
            assignee_principal_id=props.get("assignee_principal_id"),
            task_properties=_task_properties(props),
        ).store(synapse_client=syn)
        return CreateResult(id_=str(task.task_id), outs=_task_outs(task, props))

    def read(self, id_: str, props: dict) -> ReadResult:
        try:
            task = CurationTask(task_id=int(id_)).get(synapse_client=get_client())
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                return ReadResult(id_=None, outs={})
            raise
        outs = _task_outs(task, props)
        inputs = {k: v for k, v in outs.items() if k != "project_id"}
        return ReadResult(id_=id_, outs=outs, inputs=inputs)

    def diff(self, id_: str, olds: dict, news: dict) -> DiffResult:
        replaces = _changed(olds, news, TASK_REPLACE_KEYS)
        changes = _changed(olds, news, TASK_UPDATE_KEYS)
        return DiffResult(
            changes=bool(replaces or changes),
            replaces=replaces,
            delete_before_replace=bool(replaces),
        )

    def update(self, id_: str, olds: dict, news: dict) -> UpdateResult:
        syn = get_client()
        task = CurationTask(task_id=int(id_)).get(synapse_client=syn)
        task.instructions = news["instructions"]
        task.assignee_principal_id = news.get("assignee_principal_id")
        task.task_properties = _task_properties(news)
        task = task.store(synapse_client=syn)
        return UpdateResult(outs=_task_outs(task, news))

    def delete(self, id_: str, props: dict) -> None:
        try:
            CurationTask(task_id=int(id_)).delete(
                delete_source=False, synapse_client=get_client()
            )
        except Exception as error:  # noqa: BLE001
            if not _is_not_found(error):
                raise


class SynapseCurationTask(Resource):
    """A curation task. ``kind`` is ``file`` or ``record``."""

    def __init__(
        self,
        resource_name: str,
        kind: str,
        data_type: str,
        instructions: str,
        folder_id: pulumi.Input[str],
        file_view_id: Optional[pulumi.Input[str]] = None,
        record_set_id: Optional[pulumi.Input[str]] = None,
        assignee_principal_id: Optional[pulumi.Input[str]] = None,
        authorization_mode: Optional[str] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            CurationTaskProvider(),
            resource_name,
            {
                "kind": kind,
                "data_type": data_type,
                "instructions": instructions,
                "folder_id": folder_id,
                "file_view_id": file_view_id,
                "record_set_id": record_set_id,
                "assignee_principal_id": assignee_principal_id,
                "authorization_mode": authorization_mode,
            },
            opts,
        )


# --------------------------------------------------------------------------
# Curator workflows, as components
# --------------------------------------------------------------------------


def _child_opts(parent: pulumi.Resource, depends_on=None) -> pulumi.ResourceOptions:
    return pulumi.ResourceOptions(parent=parent, depends_on=depends_on or [])


class FileBasedMetadataTask(pulumi.ComponentResource):
    """What ``create_file_based_metadata_task`` creates, managed by Pulumi.

    Optionally binds ``schema_uri`` to the folder, then creates a file view
    with one column per schema property and a file-based curation task.
    Without ``schema_uri`` the folder must already have a schema bound.
    """

    def __init__(
        self,
        resource_name: str,
        folder_id: pulumi.Input[str],
        curation_task_name: str,
        instructions: str,
        schema_uri: Optional[pulumi.Input[str]] = None,
        enable_derived_annotations: bool = False,
        entity_view_name: str = "JSON Schema view",
        view_type_mask: int = 1,
        column_order: Optional[list[str]] = None,
        assignee_principal_id: Optional[pulumi.Input[str]] = None,
        authorization_mode: Optional[str] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            "synapseformation:curator:FileBasedMetadataTask", resource_name, None, opts
        )
        view_deps = []
        self.schema_binding = None
        if schema_uri:
            self.schema_binding = SynapseSchemaBinding(
                f"{resource_name}-schema-binding",
                entity_id=folder_id,
                schema_uri=schema_uri,
                enable_derived_annotations=enable_derived_annotations,
                opts=_child_opts(self),
            )
            view_deps.append(self.schema_binding)
        self.entity_view = SynapseSchemaView(
            f"{resource_name}-view",
            name=entity_view_name,
            parent_id=folder_id,
            view_type_mask=view_type_mask,
            column_order=column_order,
            schema_uri=schema_uri,
            opts=_child_opts(self, view_deps),
        )
        self.curation_task = SynapseCurationTask(
            f"{resource_name}-task",
            kind=FILE_TASK,
            data_type=curation_task_name,
            instructions=instructions,
            folder_id=folder_id,
            file_view_id=self.entity_view.id,
            assignee_principal_id=assignee_principal_id,
            authorization_mode=authorization_mode,
            opts=_child_opts(self),
        )
        self.outputs = {
            "entity_view_id": self.entity_view.id,
            "curation_task_id": self.curation_task.id,
        }
        self.register_outputs(self.outputs)


class RecordBasedMetadataTask(pulumi.ComponentResource):
    """What ``create_record_based_metadata_task`` creates, managed by Pulumi.

    Creates a record set seeded with the schema's columns, binds the schema
    to it (unless ``bind_schema_to_record_set`` is false) and creates a
    record-based curation task. No Grid is created: curators open grid
    sessions from the task, and the curator extension stops creating one in
    synapseclient 5.
    """

    def __init__(
        self,
        resource_name: str,
        folder_id: pulumi.Input[str],
        record_set_name: str,
        record_set_description: str,
        curation_task_name: str,
        upsert_keys: list[str],
        instructions: str,
        schema_uri: pulumi.Input[str],
        bind_schema_to_record_set: bool = True,
        enable_derived_annotations: bool = False,
        assignee_principal_id: Optional[pulumi.Input[str]] = None,
        authorization_mode: Optional[str] = None,
        column_order: Optional[list[str]] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__(
            "synapseformation:curator:RecordBasedMetadataTask",
            resource_name,
            None,
            opts,
        )
        self.record_set = SynapseRecordSet(
            f"{resource_name}-record-set",
            name=record_set_name,
            parent_id=folder_id,
            description=record_set_description,
            upsert_keys=upsert_keys,
            schema_uri=schema_uri,
            column_order=column_order,
            opts=_child_opts(self),
        )
        task_deps = []
        self.schema_binding = None
        if bind_schema_to_record_set:
            self.schema_binding = SynapseSchemaBinding(
                f"{resource_name}-schema-binding",
                entity_id=self.record_set.id,
                schema_uri=schema_uri,
                enable_derived_annotations=enable_derived_annotations,
                opts=_child_opts(self),
            )
            task_deps.append(self.schema_binding)
        self.curation_task = SynapseCurationTask(
            f"{resource_name}-task",
            kind=RECORD_TASK,
            data_type=curation_task_name,
            instructions=instructions,
            folder_id=folder_id,
            record_set_id=self.record_set.id,
            assignee_principal_id=assignee_principal_id,
            authorization_mode=authorization_mode,
            opts=_child_opts(self, task_deps),
        )
        self.outputs = {
            "record_set_id": self.record_set.id,
            "curation_task_id": self.curation_task.id,
        }
        self.register_outputs(self.outputs)
