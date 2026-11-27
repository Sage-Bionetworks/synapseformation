"""Tests for the Synapse dynamic providers.

The providers call ``synapseclient.models`` classes and ``synapseclient.api``
functions. Here those are swapped for small fakes backed by an in-memory
Synapse, so the tests exercise the provider logic without network access.
"""

import csv
import json
from types import SimpleNamespace

import pytest
from synapseclient.models import (
    FileBasedMetadataTaskProperties,
    RecordBasedMetadataTaskProperties,
)

from synapseformation import providers
from synapseformation.providers import (
    FOLDER_TYPE,
    PROJECT_TYPE,
    AclProvider,
    CurationTaskProvider,
    EntityProvider,
    JsonSchemaProvider,
    RecordSetProvider,
    SchemaBindingProvider,
    SchemaOrganizationProvider,
    SchemaViewProvider,
    TeamProvider,
    normalize_grants,
    record_set_columns,
)

ME = 1000
SCHEMA_URI = "my.org-Bio-1.0.0"
SCHEMA_BODY = {
    "type": "object",
    "properties": {"specimenID": {"type": "string"}, "age": {}, "tissue": {}},
}


class NotFound(Exception):
    def __init__(self):
        super().__init__("404")
        self.response = SimpleNamespace(status_code=404)


class Conflict(Exception):
    pass


class FakeSynapse:
    """In-memory Synapse state, passed to the fakes as ``synapse_client``."""

    def __init__(self):
        self.entities, self.acls, self.teams = {}, {}, {}
        self.schemas, self.bindings, self.tasks, self.orgs = {}, {}, {}, {}
        self.next_id = 100

    def new_id(self):
        self.next_id += 1
        return self.next_id

    def entity(self, eid):
        if eid not in self.entities:
            raise NotFound()
        return self.entities[eid]

    def create_entity(self, concrete_type, name, parent_id, create_or_update, **fields):
        clash = [
            e
            for e in self.entities.values()
            if e["name"] == name and e["parentId"] == parent_id
        ]
        if clash and not create_or_update:
            raise Conflict(name)
        eid = f"syn{self.new_id()}"
        self.entities[eid] = dict(
            id=eid, concreteType=concrete_type, name=name, parentId=parent_id, **fields
        )
        if concrete_type == PROJECT_TYPE:
            self.acls[eid] = {
                "id": eid,
                "resourceAccess": [{"principalId": ME, "accessType": ["ADMIN"]}],
            }
        return self.entities[eid]

    def benefactor(self, eid):
        while eid not in self.acls:
            eid = self.entity(eid)["parentId"]
        return eid

    def principals(self, eid):
        return {
            e["principalId"]: sorted(e["accessType"])
            for e in self.acls[eid]["resourceAccess"]
        }

    # TeamProvider.update still uses REST, because Team has no update.
    def restGET(self, uri):
        team_id = uri.rsplit("/", 1)[1]
        if team_id not in self.teams:
            raise NotFound()
        return dict(self.teams[team_id])

    def restPUT(self, uri, body):
        assert uri == "/team"
        body = json.loads(body)
        self.teams[str(body["id"])] = body
        return body


# ---------------------------------------------------------------- fake models


class FakeEntity:
    TYPE = None

    def __init__(
        self,
        id=None,
        name=None,
        description=None,
        parent_id=None,
        create_or_update=True,
    ):
        self.id, self.name, self.description = id, name, description
        self.parent_id, self.create_or_update = parent_id, create_or_update

    def _fill(self, data):
        self.id, self.name = data["id"], data["name"]
        self.description, self.parent_id = data.get("description"), data["parentId"]
        return self

    def get(self, *, synapse_client):
        return self._fill(synapse_client.entity(self.id))

    def store(self, *, synapse_client):
        if self.id:
            data = synapse_client.entity(self.id)
            data.update(name=self.name, description=self.description)
            if self.parent_id:
                data["parentId"] = self.parent_id
        else:
            parent = "syn4489" if self.TYPE == PROJECT_TYPE else self.parent_id
            data = synapse_client.create_entity(
                self.TYPE,
                self.name,
                parent,
                self.create_or_update,
                description=self.description,
            )
        return self._fill(data)

    def delete(self, *, synapse_client):
        synapse_client.entity(self.id)
        del synapse_client.entities[self.id]


class FakeProject(FakeEntity):
    TYPE = PROJECT_TYPE


class FakeFolder(FakeEntity):
    TYPE = FOLDER_TYPE


def fake_get(synapse_id, *, file_options=None, synapse_client):
    assert file_options is not None and not file_options.download_file
    data = synapse_client.entity(synapse_id)
    cls = FakeProject if data["concreteType"] == PROJECT_TYPE else FakeFolder
    return cls()._fill(data)


class FakeTeam:
    def __init__(self, id=None, name=None, description=None, can_public_join=False):
        self.id, self.name, self.description = id, name, description
        self.can_public_join = can_public_join

    def fill_from_dict(self, data):
        self.id, self.name = int(data["id"]), data["name"]
        self.description = data.get("description")
        self.can_public_join = data.get("canPublicJoin", False)
        return self

    def create(self, *, synapse_client):
        data = {
            "id": str(synapse_client.new_id()),
            "name": self.name,
            "description": self.description,
            "canPublicJoin": self.can_public_join,
        }
        synapse_client.teams[data["id"]] = data
        return self.fill_from_dict(data)

    def get(self, *, synapse_client):
        return self.fill_from_dict(synapse_client.restGET(f"/team/{self.id}"))

    def delete(self, *, synapse_client):
        if synapse_client.teams.pop(str(self.id), None) is None:
            raise NotFound()


class FakeJSONSchema:
    def __init__(self, name, organization_name):
        self.name, self.organization_name = name, organization_name

    def store(self, *, schema_body, version, synapse_client):
        uri = f"{self.organization_name}-{self.name}-{version}"
        if uri in synapse_client.schemas:
            raise Conflict(uri)
        # Like the real model, write "$id" into the body we were given.
        schema_body["$id"] = f"https://repo/schema/{uri}"
        synapse_client.schemas[uri] = dict(schema_body)
        return self


class FakeOrganization:
    def __init__(self, name):
        self.name, self.id = name, None

    def _fill(self, syn):
        if self.name not in syn.orgs:
            raise NotFound()
        self.id = syn.orgs[self.name]["id"]
        return self

    def store(self, *, synapse_client):
        if self.name in synapse_client.orgs:
            raise Conflict(self.name)
        synapse_client.orgs[self.name] = {
            "id": str(synapse_client.new_id()),
            "acl": {
                "etag": "e0",
                "resourceAccess": [
                    {"principalId": ME, "accessType": ["CREATE", "READ"]}
                ],
            },
        }
        return self._fill(synapse_client)

    def get(self, *, synapse_client):
        return self._fill(synapse_client)

    def get_acl(self, *, synapse_client):
        return json.loads(json.dumps(synapse_client.orgs[self.name]["acl"]))

    def delete(self, *, synapse_client):
        if synapse_client.orgs.pop(self.name, None) is None:
            raise NotFound()


class FakeRecordSet:
    def __init__(
        self,
        id=None,
        name=None,
        description=None,
        parent_id=None,
        path=None,
        upsert_keys=None,
        create_or_update=True,
        download_file=True,
    ):
        self.id, self.name, self.description = id, name, description
        self.parent_id, self.path, self.upsert_keys = parent_id, path, upsert_keys
        self.create_or_update, self.download_file = create_or_update, download_file
        self.force_version = True

    def _fill(self, data):
        self.id, self.name = data["id"], data["name"]
        self.description, self.parent_id = data["description"], data["parentId"]
        self.upsert_keys = data["upsertKeys"]
        return self

    def store(self, *, synapse_client):
        if self.id:
            data = synapse_client.entity(self.id)
            data.update(
                name=self.name,
                description=self.description,
                parentId=self.parent_id,
                upsertKeys=self.upsert_keys,
            )
            if self.force_version:
                data["version"] += 1
            return self._fill(data)
        with open(self.path, newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        data = synapse_client.create_entity(
            "RecordSet",
            self.name,
            self.parent_id,
            self.create_or_update,
            description=self.description,
            upsertKeys=self.upsert_keys,
            header=header,
            version=1,
        )
        return self._fill(data)

    def get(self, *, synapse_client):
        assert not self.download_file
        return self._fill(synapse_client.entity(self.id))

    def delete(self, *, synapse_client):
        synapse_client.entity(self.id)
        del synapse_client.entities[self.id]


class FakeEntityView:
    def __init__(self, id=None):
        self.id, self.columns_loaded = id, None

    def get(self, *, include_columns, synapse_client):
        data = synapse_client.entity(self.id)
        self.name, self.parent_id = data["name"], data["parentId"]
        self.columns_loaded = include_columns
        return self

    def store(self, *, synapse_client):
        assert self.columns_loaded, "storing a view without its columns"
        synapse_client.entity(self.id)["name"] = self.name
        return self

    def delete(self, *, synapse_client):
        synapse_client.entity(self.id)
        del synapse_client.entities[self.id]


def fake_create_json_schema_entity_view(
    synapse_entity_id, entity_view_name, view_type_mask, column_order, syn
):
    uri = syn.bindings[synapse_entity_id]["uri"]
    columns = ["name", "id", *syn.schemas[uri]["properties"]]
    data = syn.create_entity(
        "EntityView",
        entity_view_name,
        synapse_entity_id,
        True,
        mask=view_type_mask,
        columns=columns,
    )
    view = FakeEntityView(data["id"])
    view.name, view.parent_id = data["name"], data["parentId"]
    return view


class FakeCurationTask:
    def __init__(
        self,
        task_id=None,
        data_type=None,
        project_id=None,
        instructions=None,
        assignee_principal_id=None,
        task_properties=None,
    ):
        self.task_id, self.data_type, self.project_id = task_id, data_type, project_id
        self.instructions, self.task_properties = instructions, task_properties
        self.assignee_principal_id = assignee_principal_id

    def _save(self, syn):
        syn.tasks[self.task_id] = dict(vars(self))
        return self

    def store(self, *, synapse_client):
        if not self.task_id:
            # Like the real model: reuse a task with the same data type.
            for task in synapse_client.tasks.values():
                if (task["project_id"], task["data_type"]) == (
                    self.project_id,
                    self.data_type,
                ):
                    self.task_id = task["task_id"]
                    break
            else:
                self.task_id = synapse_client.new_id()
        return self._save(synapse_client)

    def get(self, *, synapse_client):
        if self.task_id not in synapse_client.tasks:
            raise NotFound()
        vars(self).update(synapse_client.tasks[self.task_id])
        return self

    def delete(self, *, delete_source, synapse_client):
        assert delete_source is False
        if synapse_client.tasks.pop(self.task_id, None) is None:
            raise NotFound()


def fake_project_id(entity_id, synapse_client):
    while synapse_client.entity(entity_id)["concreteType"] != PROJECT_TYPE:
        entity_id = synapse_client.entity(entity_id)["parentId"]
    return entity_id


def fake_api():
    """Async stand-ins for the ``synapseclient.api`` functions used."""

    async def get_entity_benefactor(entity_id, *, synapse_client):
        return SimpleNamespace(id=synapse_client.benefactor(entity_id))

    async def get_entity_acl(entity_id, *, synapse_client):
        if entity_id not in synapse_client.acls:
            raise NotFound()
        return json.loads(json.dumps(synapse_client.acls[entity_id]))

    async def post_entity_acl(entity_id, acl, *, synapse_client):
        assert entity_id not in synapse_client.acls, "local ACL already exists"
        synapse_client.acls[entity_id] = acl
        return acl

    async def put_entity_acl(entity_id, acl, *, synapse_client):
        if entity_id not in synapse_client.acls:
            raise NotFound()
        synapse_client.acls[entity_id] = acl
        return acl

    async def delete_entity_acl(entity_id, *, synapse_client):
        synapse_client.acls.pop(entity_id, None)

    async def get_json_schema_body(uri, *, synapse_client):
        if uri not in synapse_client.schemas:
            raise NotFound()
        return synapse_client.schemas[uri]

    async def delete_json_schema(uri, *, synapse_client):
        if synapse_client.schemas.pop(uri, None) is None:
            raise NotFound()

    async def bind_json_schema_to_entity(
        entity_id, uri, *, enable_derived_annotations, synapse_client
    ):
        synapse_client.entity(entity_id)
        synapse_client.bindings[entity_id] = {
            "uri": uri,
            "derived": enable_derived_annotations,
        }

    async def get_json_schema_from_entity(entity_id, *, synapse_client):
        if entity_id not in synapse_client.bindings:
            raise NotFound()
        binding = synapse_client.bindings[entity_id]
        return {
            "jsonSchemaVersionInfo": {"$id": binding["uri"]},
            "enableDerivedAnnotations": binding["derived"],
        }

    async def delete_json_schema_from_entity(entity_id, *, synapse_client):
        if synapse_client.bindings.pop(entity_id, None) is None:
            raise NotFound()

    async def update_organization_acl(org_id, resource_access, etag, *, synapse_client):
        (org,) = [o for o in synapse_client.orgs.values() if o["id"] == org_id]
        assert etag == org["acl"]["etag"]
        org["acl"] = {"etag": etag + "'", "resourceAccess": list(resource_access)}

    return SimpleNamespace(**{k: v for k, v in locals().items() if callable(v)})


@pytest.fixture
def syn(monkeypatch):
    fake = FakeSynapse()
    monkeypatch.setattr(providers, "get_client", lambda: fake)
    monkeypatch.setattr(providers, "synapse_api", fake_api())
    monkeypatch.setattr(
        providers,
        "operations",
        SimpleNamespace(
            get=fake_get,
            FileOptions=lambda download_file: SimpleNamespace(
                download_file=download_file
            ),
        ),
    )
    monkeypatch.setattr(providers, "project_id_from_entity_id", fake_project_id)
    for name, fake_cls in {
        "Project": FakeProject,
        "Folder": FakeFolder,
        "Team": FakeTeam,
        "JSONSchema": FakeJSONSchema,
        "Organization": FakeOrganization,
        "RecordSet": FakeRecordSet,
        "EntityView": FakeEntityView,
        "CurationTask": FakeCurationTask,
    }.items():
        monkeypatch.setattr(providers, name, fake_cls)
    monkeypatch.setattr(
        "synapseclient.extensions.curator.file_based_metadata_task."
        "_create_json_schema_entity_view",
        fake_create_json_schema_entity_view,
    )
    return fake


def project_props(**extra):
    return {
        "concrete_type": PROJECT_TYPE,
        "name": "P",
        "description": "d",
        "parent_id": None,
        **extra,
    }


def make_tree(syn):
    entity = EntityProvider()
    project = entity.create(project_props()).id
    folder = entity.create(
        {"concrete_type": FOLDER_TYPE, "name": "F", "parent_id": project}
    ).id
    return project, folder


def bound_folder(syn):
    project, folder = make_tree(syn)
    syn.schemas[SCHEMA_URI] = dict(SCHEMA_BODY)
    SchemaBindingProvider().create({"entity_id": folder, "schema_uri": SCHEMA_URI})
    return project, folder


class TestEntityProvider:
    def test_create_read_update_delete(self, syn):
        provider = EntityProvider()
        created = provider.create(project_props())
        assert created.outs["parent_id"] is None
        assert provider.read(created.id, created.outs).outs == created.outs

        news = dict(created.outs, description="new")
        assert provider.diff(created.id, created.outs, news).changes
        provider.update(created.id, created.outs, news)
        assert syn.entities[created.id]["description"] == "new"

        provider.delete(created.id, news)
        assert created.id not in syn.entities
        provider.delete(created.id, news)  # already gone is fine

    def test_folder_can_move(self, syn):
        project, folder = make_tree(syn)
        other = (
            EntityProvider()
            .create(
                {"concrete_type": FOLDER_TYPE, "name": "Other", "parent_id": project}
            )
            .id
        )
        news = {"concrete_type": FOLDER_TYPE, "name": "F", "parent_id": other}
        assert EntityProvider().update(folder, {}, news).outs["parent_id"] == other

    def test_name_clash_fails_instead_of_adopting(self, syn):
        EntityProvider().create(project_props())
        with pytest.raises(Conflict):
            EntityProvider().create(project_props())

    def test_read_missing_entity_reports_deleted(self, syn):
        assert EntityProvider().read("syn999", {}).id is None

    def test_type_change_replaces(self, syn):
        olds = project_props()
        news = dict(olds, concrete_type=FOLDER_TYPE)
        result = EntityProvider().diff("syn1", olds, news)
        assert result.replaces == ["concrete_type"]

    def test_unchanged_is_not_a_change(self, syn):
        assert (
            not EntityProvider().diff("syn1", project_props(), project_props()).changes
        )

    def test_adopt_existing_entity(self, syn):
        existing = EntityProvider().create(project_props(name="Old")).id
        adopted = EntityProvider().create(project_props(name="New", adopt_id=existing))
        assert adopted.id == existing
        assert syn.entities[existing]["name"] == "New"
        assert len(syn.entities) == 1

    def test_adopt_rejects_wrong_type(self, syn):
        project, folder = make_tree(syn)
        with pytest.raises(ValueError, match="not a"):
            EntityProvider().create(project_props(adopt_id=folder))


class TestTeamProvider:
    def test_lifecycle_and_drift(self, syn):
        provider = TeamProvider()
        props = {"name": "T", "description": "d", "can_public_join": False}
        created = provider.create(props)
        syn.teams[created.id]["name"] = "Renamed in UI"
        read = provider.read(created.id, created.outs)
        assert read.outs["name"] == "Renamed in UI"
        assert provider.diff(created.id, read.outs, props).changes

        provider.update(created.id, read.outs, props)
        assert syn.teams[created.id]["name"] == "T"
        provider.delete(created.id, props)
        assert provider.read(created.id, props).id is None

    def test_adopt_existing_team(self, syn):
        existing = TeamProvider().create({"name": "Old"}).id
        adopted = TeamProvider().create({"name": "New", "adopt_id": existing})
        assert adopted.id == existing
        assert syn.teams[existing]["name"] == "New"


class TestAclProvider:
    def test_grant_on_inheriting_folder_creates_then_restores_local_acl(self, syn):
        project, folder = make_tree(syn)
        provider = AclProvider()
        created = provider.create(
            {
                "entity_id": folder,
                "grants": [{"principal_id": "7", "access_type": ["read", "DOWNLOAD"]}],
            }
        )
        assert created.outs["created_local_acl"] is True
        # The inherited creator ADMIN grant is copied, not dropped.
        assert syn.principals(folder) == {ME: ["ADMIN"], 7: ["DOWNLOAD", "READ"]}

        provider.delete(created.id, created.outs)
        assert folder not in syn.acls  # inheritance restored

    def test_existing_local_acl_keeps_other_principals_on_delete(self, syn):
        project, _ = make_tree(syn)
        provider = AclProvider()
        created = provider.create(
            {
                "entity_id": project,
                "grants": [{"principal_id": 7, "access_type": ["READ"]}],
            }
        )
        assert created.outs["created_local_acl"] is False
        provider.delete(created.id, created.outs)
        assert syn.principals(project) == {ME: ["ADMIN"]}

    def test_update_changes_and_removes_grants(self, syn):
        project, _ = make_tree(syn)
        provider = AclProvider()
        created = provider.create(
            {
                "entity_id": project,
                "grants": [
                    {"principal_id": 7, "access_type": ["READ", "DOWNLOAD"]},
                    {"principal_id": 8, "access_type": ["READ"]},
                ],
            }
        )
        news = {
            "entity_id": project,
            "grants": [{"principal_id": 7, "access_type": ["READ"]}],
        }
        assert provider.diff(created.id, created.outs, news).changes
        provider.update(created.id, created.outs, news)
        assert syn.principals(project) == {ME: ["ADMIN"], 7: ["READ"]}

    def test_no_diff_when_only_order_or_case_differs(self, syn):
        olds = {
            "entity_id": "syn1",
            "grants": [{"principal_id": 7, "access_type": ["READ", "DOWNLOAD"]}],
        }
        news = {
            "entity_id": "syn1",
            "grants": [{"principal_id": "7", "access_type": ["download", "read"]}],
        }
        assert not AclProvider().diff("syn1/acl", olds, news).changes

    def test_check_normalizes_grants_and_tolerates_unknowns(self, syn):
        news = {
            "entity_id": "syn1",
            "grants": [{"principal_id": 7, "access_type": ["read", "DOWNLOAD"]}],
        }
        checked = AclProvider().check({}, news).inputs
        assert checked["grants"] == [
            {"principal_id": 7, "access_type": ["DOWNLOAD", "READ"]}
        ]
        # During preview a team's principal ID is not known yet.
        pending = {
            "entity_id": "syn1",
            "grants": [{"principal_id": "<unknown>", "access_type": ["READ"]}],
        }
        assert AclProvider().check({}, pending).inputs == pending

    def test_entity_change_replaces(self, syn):
        olds = {"entity_id": "syn1", "grants": []}
        news = {"entity_id": "syn2", "grants": []}
        assert AclProvider().diff("syn1/acl", olds, news).replaces == ["entity_id"]

    def test_read_detects_drift_and_lost_local_acl(self, syn):
        _, folder = make_tree(syn)
        provider = AclProvider()
        created = provider.create(
            {
                "entity_id": folder,
                "grants": [{"principal_id": 7, "access_type": ["READ"]}],
            }
        )
        syn.acls[folder]["resourceAccess"].append(
            {"principalId": 99, "accessType": ["READ"]}
        )
        syn.acls[folder]["resourceAccess"][1]["accessType"] = ["READ", "UPDATE"]
        read = provider.read(created.id, created.outs)
        # Only managed principals are reported.
        assert read.outs["grants"] == [
            {"principal_id": 7, "access_type": ["READ", "UPDATE"]}
        ]

        del syn.acls[folder]
        assert provider.read(created.id, created.outs).outs["grants"] == []
        # Update recreates the local ACL if it was removed outside the tool.
        provider.update(created.id, created.outs, created.outs)
        assert syn.principals(folder)[7] == ["READ"]

    def test_delete_after_entity_is_gone(self, syn):
        project, folder = make_tree(syn)
        outs = (
            AclProvider()
            .create(
                {
                    "entity_id": folder,
                    "grants": [{"principal_id": 7, "access_type": ["READ"]}],
                }
            )
            .outs
        )
        del syn.entities[folder]
        AclProvider().delete(f"{folder}/acl", outs)


def test_normalize_grants_merges_duplicates_and_sorts():
    grants = [
        {"principal_id": "9", "access_type": ["read"]},
        {"principal_id": 3, "access_type": ["UPDATE", "READ", "READ"]},
    ]
    assert normalize_grants(grants) == [
        {"principal_id": 3, "access_type": ["READ", "UPDATE"]},
        {"principal_id": 9, "access_type": ["READ"]},
    ]


class TestSchemaOrganizationProvider:
    def org_principals(self, syn, name):
        return {
            e["principalId"]: sorted(e["accessType"])
            for e in syn.orgs[name]["acl"]["resourceAccess"]
        }

    def test_create_grant_update_delete(self, syn):
        provider = SchemaOrganizationProvider()
        props = {
            "name": "example.org",
            "grants": [{"principal_id": 7, "access_type": ["create", "READ"]}],
        }
        created = provider.create(props)
        assert created.id == "example.org"
        assert created.outs["organization_id"] == syn.orgs["example.org"]["id"]
        # The creator keeps their access.
        assert self.org_principals(syn, "example.org") == {
            ME: ["CREATE", "READ"],
            7: ["CREATE", "READ"],
        }
        assert provider.read(created.id, created.outs).outs == created.outs

        news = {
            "name": "example.org",
            "grants": [{"principal_id": 8, "access_type": ["READ"]}],
        }
        assert provider.diff(created.id, created.outs, news).changes
        provider.update(created.id, created.outs, news)
        assert self.org_principals(syn, "example.org") == {
            ME: ["CREATE", "READ"],
            8: ["READ"],
        }

        provider.delete(created.id, news)
        assert provider.read(created.id, news).id is None
        provider.delete(created.id, news)

    def test_read_reports_only_managed_principals(self, syn):
        provider = SchemaOrganizationProvider()
        created = provider.create({"name": "example.org", "grants": []})
        assert created.outs["grants"] == []
        assert provider.read(created.id, created.outs).outs["grants"] == []

    def test_adopt_existing_organization(self, syn):
        FakeOrganization("example.org").store(synapse_client=syn)
        adopted = SchemaOrganizationProvider().create(
            {"name": "example.org", "grants": [], "adopt_id": "example.org"}
        )
        assert adopted.id == "example.org"
        with pytest.raises(Conflict):
            SchemaOrganizationProvider().create({"name": "example.org", "grants": []})

    def test_rename_replaces(self, syn):
        olds = {"name": "example.org", "grants": []}
        news = {"name": "example.other", "grants": []}
        assert SchemaOrganizationProvider().diff(
            "example.org", olds, news
        ).replaces == ["name"]


class TestJsonSchemaProvider:
    def props(self, **extra):
        return {
            "organization": "my.org",
            "name": "Bio",
            "version": "1.0.0",
            "body": json.loads(json.dumps(SCHEMA_BODY)),
            **extra,
        }

    def test_create_read_delete(self, syn):
        provider = JsonSchemaProvider()
        props = self.props()
        created = provider.create(props)
        assert created.id == SCHEMA_URI
        assert created.outs["uri"] == SCHEMA_URI
        # Synapse's "$id" ends up neither in our outputs nor in the template.
        assert "$id" in syn.schemas[SCHEMA_URI]
        assert "$id" not in props["body"] and "$id" not in created.outs["body"]

        assert provider.read(created.id, created.outs).outs == created.outs
        provider.delete(created.id, created.outs)
        assert provider.read(created.id, created.outs).id is None
        provider.delete(created.id, created.outs)

    def test_body_change_needs_a_new_version(self, syn):
        olds = self.props()
        changed = self.props(body={"type": "object"})
        failures = JsonSchemaProvider().check(olds, changed).failures
        assert [f.property for f in failures] == ["version"]
        assert not JsonSchemaProvider().check({}, changed).failures  # first create
        bumped = dict(changed, version="1.0.1")
        assert not JsonSchemaProvider().check(olds, bumped).failures
        assert JsonSchemaProvider().diff(SCHEMA_URI, olds, bumped).replaces == [
            "version",
            "body",
        ]

    def test_synapse_id_is_not_a_body_change(self, syn):
        olds = self.props()
        olds["body"]["$id"] = "https://repo/schema/x"
        assert not JsonSchemaProvider().diff(SCHEMA_URI, olds, self.props()).changes
        assert not JsonSchemaProvider().check(olds, self.props()).failures


class TestSchemaBindingProvider:
    def test_bind_read_rebind_unbind(self, syn):
        _, folder = make_tree(syn)
        provider = SchemaBindingProvider()
        props = {"entity_id": folder, "schema_uri": SCHEMA_URI}
        created = provider.create(props)
        assert created.id == f"{folder}/schema"
        assert created.outs["enable_derived_annotations"] is False
        assert provider.read(created.id, created.outs).outs == created.outs

        news = dict(
            props, schema_uri="my.org-Bio-2.0.0", enable_derived_annotations=True
        )
        assert provider.diff(created.id, created.outs, news).changes
        provider.update(created.id, created.outs, news)
        assert syn.bindings[folder] == {"uri": "my.org-Bio-2.0.0", "derived": True}

        provider.delete(created.id, news)
        assert provider.read(created.id, news).id is None
        provider.delete(created.id, news)

    def test_unversioned_uri_matches_bound_version(self, syn):
        _, folder = make_tree(syn)
        syn.bindings[folder] = {"uri": "my.org-Bio-1.2.3", "derived": False}
        read = SchemaBindingProvider().read(
            f"{folder}/schema", {"entity_id": folder, "schema_uri": "my.org-Bio"}
        )
        assert read.outs["schema_uri"] == "my.org-Bio"

    def test_reports_a_different_bound_schema(self, syn):
        _, folder = make_tree(syn)
        syn.bindings[folder] = {"uri": "other.org-X-1.0.0", "derived": False}
        read = SchemaBindingProvider().read(
            f"{folder}/schema", {"entity_id": folder, "schema_uri": SCHEMA_URI}
        )
        assert read.outs["schema_uri"] == "other.org-X-1.0.0"

    def test_entity_change_replaces(self, syn):
        olds = {"entity_id": "syn1", "schema_uri": SCHEMA_URI}
        news = {"entity_id": "syn2", "schema_uri": SCHEMA_URI}
        assert SchemaBindingProvider().diff("syn1/schema", olds, news).replaces == [
            "entity_id"
        ]


class TestRecordSetProvider:
    def props(self, folder, **extra):
        return {
            "name": "Records",
            "description": "d",
            "parent_id": folder,
            "upsert_keys": ["specimenID"],
            "schema_uri": SCHEMA_URI,
            "column_order": None,
            **extra,
        }

    def test_columns_put_upsert_keys_then_requested_order_first(self):
        assert record_set_columns(SCHEMA_BODY, ["specimenID"], ["tissue"]) == [
            "specimenID",
            "tissue",
            "age",
        ]

    def test_upsert_keys_must_be_schema_properties(self):
        with pytest.raises(ValueError, match="upsert_keys"):
            record_set_columns(SCHEMA_BODY, ["sampleID"], None)

    def test_create_seeds_csv_and_update_keeps_version(self, syn):
        _, folder = bound_folder(syn)
        provider = RecordSetProvider()
        created = provider.create(self.props(folder))
        assert syn.entities[created.id]["header"] == ["specimenID", "age", "tissue"]
        assert provider.read(created.id, created.outs).outs == created.outs

        news = self.props(folder, description="new", upsert_keys=["specimenID", "age"])
        assert provider.diff(created.id, created.outs, news).changes
        provider.update(created.id, created.outs, news)
        assert syn.entities[created.id]["description"] == "new"
        assert syn.entities[created.id]["version"] == 1

        provider.delete(created.id, news)
        assert provider.read(created.id, news).id is None

    def test_schema_and_column_order_are_create_only(self, syn):
        olds = self.props("syn1")
        news = self.props("syn1", schema_uri="my.org-Bio-2.0.0", column_order=["age"])
        assert not RecordSetProvider().diff("syn9", olds, news).changes


class TestSchemaViewProvider:
    def props(self, folder, **extra):
        return {
            "name": "View",
            "parent_id": folder,
            "view_type_mask": 1,
            "column_order": None,
            "schema_uri": SCHEMA_URI,
            **extra,
        }

    def test_lifecycle(self, syn):
        _, folder = bound_folder(syn)
        provider = SchemaViewProvider()
        created = provider.create(self.props(folder))
        assert syn.entities[created.id]["columns"] == [
            "name",
            "id",
            *SCHEMA_BODY["properties"],
        ]
        assert provider.read(created.id, created.outs).outs == created.outs

        provider.update(created.id, created.outs, self.props(folder, name="Renamed"))
        assert syn.entities[created.id]["name"] == "Renamed"
        provider.delete(created.id, created.outs)
        assert provider.read(created.id, created.outs).id is None

    def test_rename_updates_but_new_schema_replaces_first(self, syn):
        olds = self.props("syn1")
        rename = SchemaViewProvider().diff("syn9", olds, self.props("syn1", name="New"))
        assert rename.changes and not rename.replaces
        new_schema = SchemaViewProvider().diff(
            "syn9", olds, self.props("syn1", schema_uri="my.org-Bio-2.0.0")
        )
        assert new_schema.replaces == ["schema_uri"]
        assert new_schema.delete_before_replace


class TestCurationTaskProvider:
    def file_props(self, folder, **extra):
        return {
            "kind": "file",
            "data_type": "Bio",
            "instructions": "go",
            "folder_id": folder,
            "file_view_id": "syn55",
            "record_set_id": None,
            "assignee_principal_id": "3",
            "authorization_mode": "SOURCE_BENEFACTOR",
            **extra,
        }

    def test_file_task_lifecycle(self, syn):
        project, folder = make_tree(syn)
        provider = CurationTaskProvider()
        created = provider.create(self.file_props(folder))
        task = syn.tasks[int(created.id)]
        assert task["project_id"] == project
        assert task["task_properties"] == FileBasedMetadataTaskProperties(
            upload_folder_id=folder,
            file_view_id="syn55",
            suggested_authorization_mode="SOURCE_BENEFACTOR",
        )
        read = provider.read(created.id, created.outs)
        assert read.outs == created.outs
        assert "project_id" not in read.inputs

        news = self.file_props(folder, instructions="new", file_view_id="syn56")
        assert provider.diff(created.id, created.outs, news).changes
        provider.update(created.id, created.outs, news)
        assert syn.tasks[int(created.id)]["instructions"] == "new"
        assert syn.tasks[int(created.id)]["task_properties"].file_view_id == "syn56"

        provider.delete(created.id, news)
        assert provider.read(created.id, news).id is None
        provider.delete(created.id, news)

    def test_record_task(self, syn):
        _, folder = make_tree(syn)
        props = self.file_props(
            folder,
            kind="record",
            file_view_id=None,
            record_set_id="syn77",
            authorization_mode=None,
            assignee_principal_id=None,
        )
        created = CurationTaskProvider().create(props)
        assert syn.tasks[int(created.id)]["task_properties"] == (
            RecordBasedMetadataTaskProperties(record_set_id="syn77")
        )
        assert created.outs["folder_id"] == folder

    def test_new_data_type_deletes_old_task_first(self, syn):
        olds = self.file_props("syn1")
        result = CurationTaskProvider().diff("8", olds, dict(olds, data_type="Other"))
        assert result.replaces == ["data_type"]
        assert result.delete_before_replace
