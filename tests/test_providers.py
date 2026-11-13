"""Tests for the Synapse dynamic providers, using an in-memory fake client"""

import json
import re
from types import SimpleNamespace

import pytest

from synapseformation import providers
from synapseformation.providers import (
    FOLDER_TYPE,
    PROJECT_TYPE,
    AclProvider,
    EntityProvider,
    TeamProvider,
    normalize_grants,
)

ME = 1000


class NotFound(Exception):
    def __init__(self):
        super().__init__("404")
        self.response = SimpleNamespace(status_code=404)


class FakeSynapse:
    """Just enough of the Synapse REST API for the providers."""

    def __init__(self):
        self.entities, self.acls, self.teams = {}, {}, {}
        self.next_id = 100

    def _new_id(self):
        self.next_id += 1
        return self.next_id

    def _benefactor(self, eid):
        while eid not in self.acls:
            eid = self.entities[eid]["parentId"]
        return eid

    def restGET(self, uri):
        if m := re.match(r"^/entity/(syn\d+)/benefactor$", uri):
            self._entity(m.group(1))
            return {"id": self._benefactor(m.group(1))}
        if m := re.match(r"^/entity/(syn\d+)/acl$", uri):
            if m.group(1) not in self.acls:
                raise NotFound()
            return json.loads(json.dumps(self.acls[m.group(1)]))
        if m := re.match(r"^/entity/(syn\d+)$", uri):
            return dict(self._entity(m.group(1)))
        if m := re.match(r"^/team/(\d+)$", uri):
            if m.group(1) not in self.teams:
                raise NotFound()
            return dict(self.teams[m.group(1)])
        raise AssertionError(uri)

    def restPOST(self, uri, body):
        body = json.loads(body)
        if uri == "/entity":
            eid = f"syn{self._new_id()}"
            body["id"] = eid
            if body["concreteType"] == PROJECT_TYPE:
                body["parentId"] = "syn4489"
                self.acls[eid] = {
                    "id": eid,
                    "resourceAccess": [{"principalId": ME, "accessType": ["ADMIN"]}],
                }
            self.entities[eid] = body
            return body
        if m := re.match(r"^/entity/(syn\d+)/acl$", uri):
            assert m.group(1) not in self.acls, "local ACL already exists"
            self.acls[m.group(1)] = body
            return body
        if uri == "/team":
            body["id"] = str(self._new_id())
            self.teams[body["id"]] = body
            return body
        raise AssertionError(uri)

    def restPUT(self, uri, body):
        body = json.loads(body)
        if m := re.match(r"^/entity/(syn\d+)/acl$", uri):
            if m.group(1) not in self.acls:
                raise NotFound()
            self.acls[m.group(1)] = body
            return body
        if m := re.match(r"^/entity/(syn\d+)$", uri):
            self.entities[m.group(1)] = body
            return body
        if uri == "/team":
            self.teams[body["id"]] = body
            return body
        raise AssertionError(uri)

    def restDELETE(self, uri):
        if m := re.match(r"^/entity/(syn\d+)/acl$", uri):
            self.acls.pop(m.group(1), None)
            return
        if m := re.match(r"^/entity/(syn\d+)$", uri):
            self._entity(m.group(1))
            del self.entities[m.group(1)]
            return
        if m := re.match(r"^/team/(\d+)$", uri):
            if self.teams.pop(m.group(1), None) is None:
                raise NotFound()
            return
        raise AssertionError(uri)

    def _entity(self, eid):
        if eid not in self.entities:
            raise NotFound()
        return self.entities[eid]

    def principals(self, eid):
        return {
            e["principalId"]: sorted(e["accessType"])
            for e in self.acls[eid]["resourceAccess"]
        }


@pytest.fixture
def syn(monkeypatch):
    fake = FakeSynapse()
    monkeypatch.setattr(providers, "get_client", lambda: fake)
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

    def test_read_missing_entity_reports_deleted(self, syn):
        assert EntityProvider().read("syn999", {}).id is None

    def test_type_change_replaces(self, syn):
        olds = project_props()
        news = dict(olds, concrete_type=FOLDER_TYPE)
        result = EntityProvider().diff("syn1", olds, news)
        assert result.replaces == ["concrete_type"]

    def test_unchanged_is_not_a_change(self, syn):
        assert not EntityProvider().diff("syn1", project_props(), project_props()).changes

    def test_adopt_existing_entity(self, syn):
        existing = EntityProvider().create(project_props(name="Old")).id
        adopted = EntityProvider().create(
            project_props(name="New", adopt_id=existing)
        )
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
            {"entity_id": project, "grants": [{"principal_id": 7, "access_type": ["READ"]}]}
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
        olds = {"entity_id": "syn1", "grants": [{"principal_id": 7, "access_type": ["READ", "DOWNLOAD"]}]}
        news = {"entity_id": "syn1", "grants": [{"principal_id": "7", "access_type": ["download", "read"]}]}
        assert not AclProvider().diff("syn1/acl", olds, news).changes

    def test_entity_change_replaces(self, syn):
        olds = {"entity_id": "syn1", "grants": []}
        news = {"entity_id": "syn2", "grants": []}
        assert AclProvider().diff("syn1/acl", olds, news).replaces == ["entity_id"]

    def test_read_detects_drift_and_lost_local_acl(self, syn):
        _, folder = make_tree(syn)
        provider = AclProvider()
        created = provider.create(
            {"entity_id": folder, "grants": [{"principal_id": 7, "access_type": ["READ"]}]}
        )
        syn.acls[folder]["resourceAccess"].append({"principalId": 99, "accessType": ["READ"]})
        syn.acls[folder]["resourceAccess"][1]["accessType"] = ["READ", "UPDATE"]
        read = provider.read(created.id, created.outs)
        # Only managed principals are reported.
        assert read.outs["grants"] == [{"principal_id": 7, "access_type": ["READ", "UPDATE"]}]

        del syn.acls[folder]
        assert provider.read(created.id, created.outs).outs["grants"] == []
        # Update recreates the local ACL if it was removed outside the tool.
        provider.update(created.id, created.outs, created.outs)
        assert syn.principals(folder)[7] == ["READ"]

    def test_delete_after_entity_is_gone(self, syn):
        project, folder = make_tree(syn)
        outs = AclProvider().create(
            {"entity_id": folder, "grants": [{"principal_id": 7, "access_type": ["READ"]}]}
        ).outs
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
