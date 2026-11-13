"""Test the generated Pulumi program with Pulumi's runtime mocks"""

import pulumi
import pytest

from synapseformation.engine import build_program


class Mocks(pulumi.runtime.Mocks):
    def __init__(self):
        self.created = {}

    def new_resource(self, args: pulumi.runtime.MockResourceArgs):
        inputs = {k: v for k, v in args.inputs.items() if k != "__provider"}
        if "concrete_type" in inputs:
            resource_id = f"syn-{args.name}"
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
    mocks = Mocks()
    pulumi.runtime.set_mocks(mocks, preview=False)
    return mocks


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
