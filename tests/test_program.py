"""Test the generated Pulumi program with Pulumi's runtime mocks"""

import asyncio

import pulumi
import pytest

from synapseformation.engine import build_program


class Mocks(pulumi.runtime.Mocks):
    def __init__(self):
        self.created = {}

    def new_resource(self, args: pulumi.runtime.MockResourceArgs):
        inputs = {k: v for k, v in args.inputs.items() if k != "__provider"}
        if (
            "concrete_type" in inputs
            or "upsert_keys" in inputs
            or "view_type_mask" in inputs
        ):
            resource_id = f"syn-{args.name}"
        elif "grants" in inputs and "entity_id" not in inputs:
            resource_id = inputs["name"]
        elif "organization" in inputs:
            resource_id = (
                f"{inputs['organization']}-{inputs['name']}-{inputs['version']}"
            )
        elif "grants" in inputs:
            resource_id = f"{inputs['entity_id']}/acl"
        else:
            resource_id = "42"
        self.created[args.name] = inputs
        return resource_id, inputs

    def call(self, args: pulumi.runtime.MockCallArgs):
        return {}


@pytest.fixture
def mocks():
    # Pulumi's mocks need a current event loop, which Python 3.14 no longer
    # creates on demand.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    mocks = Mocks()
    pulumi.runtime.set_mocks(mocks, preview=False)
    yield mocks
    asyncio.set_event_loop(None)
    loop.close()


CONFIG = {
    "resources": {
        "ds": {"type": "team", "properties": {"name": "DS", "description": "x"}},
        "p": {"type": "project", "import": "syn7", "properties": {"name": "P"}},
        "raw": {"type": "folder", "properties": {"name": "Raw", "parent": "project.p"}},
        "acl": {
            "type": "acl",
            "properties": {
                "resource": "folder.raw",
                "grants": [
                    {"principal": "team.ds", "access_type": ["READ"]},
                    {"principal": "PUBLIC", "access_type": ["READ"]},
                ],
            },
        },
    }
}


@pulumi.runtime.test
def test_references_resolve_to_created_ids(mocks):
    created = build_program(CONFIG)()

    def check(_):
        assert mocks.created["p"]["adopt_id"] == "syn7"
        assert mocks.created["raw"]["parent_id"] == "syn-p"
        assert mocks.created["acl"]["entity_id"] == "syn-raw"
        principals = sorted(g["principal_id"] for g in mocks.created["acl"]["grants"])
        assert principals == [42, 273949]

    # Wait for every resource to register before checking.
    return pulumi.Output.all(*[r.id for r in created.values()]).apply(check)


CURATOR_CONFIG = {
    "resources": {
        "ds": {"type": "team", "properties": {"name": "DS"}},
        "p": {"type": "project", "protect": True, "properties": {"name": "P"}},
        "raw": {"type": "folder", "properties": {"name": "Raw", "parent": "project.p"}},
        "org": {
            "type": "schema_organization",
            "properties": {
                "name": "my.org",
                "grants": [{"principal": "team.ds", "access_type": ["CREATE"]}],
            },
        },
        "bio": {
            "type": "json_schema",
            "properties": {
                "organization": "schema_organization.org",
                "name": "Bio",
                "version": "1.0.0",
                "schema": {"type": "object"},
            },
        },
        "files": {
            "type": "file_based_metadata_task",
            "properties": {
                "folder": "folder.raw",
                "curation_task_name": "BioFiles",
                "instructions": "annotate",
                "schema": "json_schema.bio",
                "assignee": "team.ds",
                "authorization_mode": "source_benefactor",
            },
        },
        "records": {
            "type": "record_based_metadata_task",
            "properties": {
                "folder": "folder.raw",
                "record_set_name": "R",
                "record_set_description": "d",
                "curation_task_name": "BioRecords",
                "upsert_keys": ["specimenID"],
                "instructions": "fill in",
                "schema": "json_schema.bio",
            },
        },
    }
}


@pulumi.runtime.test
def test_curator_components_wire_children_together(mocks):
    created = build_program(CURATOR_CONFIG)()
    uri = "my.org-Bio-1.0.0"

    def check(_):
        made = mocks.created
        assert made["org"]["grants"] == [
            {"principal_id": 42, "access_type": ["CREATE"]}
        ]
        assert made["bio"]["organization"] == "my.org"
        assert made["files-schema-binding"]["entity_id"] == "syn-raw"
        assert made["files-schema-binding"]["schema_uri"] == uri
        assert made["files-view"]["parent_id"] == "syn-raw"
        assert made["files-view"]["view_type_mask"] == 1
        file_task = made["files-task"]
        assert file_task["file_view_id"] == "syn-files-view"
        assert file_task["assignee_principal_id"] == "42"
        assert file_task["authorization_mode"] == "SOURCE_BENEFACTOR"

        assert made["records-record-set"]["schema_uri"] == uri
        assert made["records-schema-binding"]["entity_id"] == "syn-records-record-set"
        assert made["records-task"]["record_set_id"] == "syn-records-record-set"
        assert made["records-task"]["kind"] == "record"

    outputs = [created["files"].outputs, created["records"].outputs]
    return pulumi.Output.all(*outputs).apply(check)
