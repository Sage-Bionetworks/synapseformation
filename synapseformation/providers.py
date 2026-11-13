"""Pulumi dynamic providers for Synapse resources.

Each provider implements create/read/update/delete/diff against the Synapse
REST API. Pulumi's engine handles state, dependency ordering, previews,
refresh (drift detection), targeted deletes and import.

Dynamic providers are serialized with dill and executed in a separate
process, so providers must not hold a logged-in client on ``self``. They get
one from :func:`get_client`, which logs in from ``SYNAPSE_AUTH_TOKEN`` or
``~/.synapseConfig``.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import pulumi
from pulumi.dynamic import (
    CreateResult,
    DiffResult,
    ReadResult,
    Resource,
    ResourceProvider,
    UpdateResult,
)

PROJECT_TYPE = "org.sagebionetworks.repo.model.Project"
FOLDER_TYPE = "org.sagebionetworks.repo.model.Folder"

_CLIENT = None


def get_client():
    """Return a logged-in Synapse client, created once per process."""
    global _CLIENT
    if _CLIENT is None:
        import synapseclient

        from . import __version__

        syn = synapseclient.Synapse(
            skip_checks=True,
            silent=True,
            user_agent=f"synapseformation/{__version__}",
        )
        syn.login(silent=True)
        _CLIENT = syn
    return _CLIENT


def _is_not_found(error: Exception) -> bool:
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None) == 404


def _changed(olds: dict, news: dict, keys: list[str]) -> list[str]:
    return [k for k in keys if olds.get(k) != news.get(k)]


# --------------------------------------------------------------------------
# Entities (projects and folders)
# --------------------------------------------------------------------------

ENTITY_KEYS = ["name", "description", "parent_id"]


def _entity_outs(entity: dict) -> dict:
    concrete_type = entity["concreteType"]
    outs = {
        "concrete_type": concrete_type,
        "name": entity.get("name"),
        "description": entity.get("description"),
        "parent_id": entity.get("parentId"),
    }
    # Synapse sets a parent on projects; it is not user-managed.
    if concrete_type == PROJECT_TYPE:
        outs["parent_id"] = None
    return outs


class EntityProvider(ResourceProvider):
    """Manages a Synapse project or folder.

    If ``adopt_id`` is set, create takes over that existing entity and
    updates it to match the template instead of making a new one. (Pulumi's
    ``import`` resource option does not work with dynamic providers.)
    """

    def create(self, props: dict) -> CreateResult:
        syn = get_client()
        if props.get("adopt_id"):
            entity = syn.restGET(f"/entity/{props['adopt_id']}")
            if entity["concreteType"] != props["concrete_type"]:
                raise ValueError(
                    f"{props['adopt_id']} is a {entity['concreteType']}, "
                    f"not a {props['concrete_type']}"
                )
            result = self.update(entity["id"], {}, props)
            return CreateResult(id_=entity["id"], outs=result.outs)
        body = {
            "concreteType": props["concrete_type"],
            "name": props["name"],
            "description": props.get("description"),
        }
        if props.get("parent_id"):
            body["parentId"] = props["parent_id"]
        entity = syn.restPOST("/entity", body=json.dumps(body))
        return CreateResult(id_=entity["id"], outs=_entity_outs(entity))

    def read(self, id_: str, props: dict) -> ReadResult:
        syn = get_client()
        try:
            entity = syn.restGET(f"/entity/{id_}")
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
        entity = syn.restGET(f"/entity/{id_}")
        entity["name"] = news["name"]
        entity["description"] = news.get("description")
        if news.get("parent_id"):
            entity["parentId"] = news["parent_id"]
        entity = syn.restPUT(f"/entity/{id_}", body=json.dumps(entity))
        return UpdateResult(outs=_entity_outs(entity))

    def delete(self, id_: str, props: dict) -> None:
        syn = get_client()
        try:
            syn.restDELETE(f"/entity/{id_}")
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


def _team_outs(team: dict) -> dict:
    return {
        "name": team.get("name"),
        "description": team.get("description"),
        "can_public_join": bool(team.get("canPublicJoin", False)),
    }


class TeamProvider(ResourceProvider):
    """Manages a Synapse team. ``adopt_id`` works as for entities."""

    def create(self, props: dict) -> CreateResult:
        syn = get_client()
        if props.get("adopt_id"):
            team_id = str(props["adopt_id"])
            result = self.update(team_id, {}, props)
            return CreateResult(id_=team_id, outs=result.outs)
        body = {
            "name": props["name"],
            "description": props.get("description"),
            "canPublicJoin": bool(props.get("can_public_join", False)),
        }
        team = syn.restPOST("/team", body=json.dumps(body))
        return CreateResult(id_=str(team["id"]), outs=_team_outs(team))

    def read(self, id_: str, props: dict) -> ReadResult:
        syn = get_client()
        try:
            team = syn.restGET(f"/team/{id_}")
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                return ReadResult(id_=None, outs={})
            raise
        outs = _team_outs(team)
        return ReadResult(id_=id_, outs=outs, inputs=outs)

    def diff(self, id_: str, olds: dict, news: dict) -> DiffResult:
        return DiffResult(changes=bool(_changed(olds, news, TEAM_KEYS)))

    def update(self, id_: str, olds: dict, news: dict) -> UpdateResult:
        syn = get_client()
        team = syn.restGET(f"/team/{id_}")
        team["name"] = news["name"]
        team["description"] = news.get("description")
        team["canPublicJoin"] = bool(news.get("can_public_join", False))
        team = syn.restPUT("/team", body=json.dumps(team))
        return UpdateResult(outs=_team_outs(team))

    def delete(self, id_: str, props: dict) -> None:
        syn = get_client()
        try:
            syn.restDELETE(f"/team/{id_}")
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


def _get_local_acl(syn, entity_id: str) -> Optional[dict]:
    """Return the entity's own ACL, or None if it inherits from a benefactor."""
    benefactor = syn.restGET(f"/entity/{entity_id}/benefactor")
    if benefactor["id"] != entity_id:
        return None
    return syn.restGET(f"/entity/{entity_id}/acl")


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

    def create(self, props: dict) -> CreateResult:
        syn = get_client()
        entity_id = props["entity_id"]
        grants = normalize_grants(props["grants"])
        acl = _get_local_acl(syn, entity_id)
        created_local_acl = acl is None
        if created_local_acl:
            benefactor = syn.restGET(f"/entity/{entity_id}/benefactor")
            inherited = syn.restGET(f"/entity/{benefactor['id']}/acl")
            acl = {"id": entity_id, "resourceAccess": inherited["resourceAccess"]}
            acl = _apply_grants(acl, grants, remove=set())
            syn.restPOST(f"/entity/{entity_id}/acl", body=json.dumps(acl))
        else:
            acl = _apply_grants(acl, grants, remove=set())
            syn.restPUT(f"/entity/{entity_id}/acl", body=json.dumps(acl))
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
        syn.restPUT(f"/entity/{entity_id}/acl", body=json.dumps(acl))
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
                syn.restDELETE(f"/entity/{entity_id}/acl")
                return
            managed = {g["principal_id"] for g in normalize_grants(props["grants"])}
            acl = _apply_grants(acl, [], remove=managed)
            syn.restPUT(f"/entity/{entity_id}/acl", body=json.dumps(acl))
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
