"""Tests for template parsing and dependency ordering"""

import json

import pytest

from synapseformation.engine import TemplateError, parse_template, view_type_mask


def template(**resources):
    return {"version": 1, "resources": resources}


EXAMPLE = template(
    acl={
        "type": "acl",
        "properties": {
            "resource": "folder.mri",
            "grants": [{"principal": "team.ds", "access_type": ["READ"]}],
        },
    },
    mri={"type": "folder", "properties": {"name": "MRI", "parent": "folder.raw"}},
    raw={"type": "folder", "properties": {"name": "Raw", "parent": "project.p"}},
    ds={"type": "team", "properties": {"name": "DS"}},
    p={"type": "project", "properties": {"name": "P"}},
)


def test_order_respects_dependencies_across_types():
    order = [s.logical_name for s in parse_template(EXAMPLE)]
    assert order.index("p") < order.index("raw") < order.index("mri")
    assert order.index("acl") > max(order.index("mri"), order.index("ds"))


def test_literal_ids_and_well_known_principals_need_no_dependency():
    specs = parse_template(
        template(
            f={"type": "folder", "properties": {"name": "F", "parent": "syn123"}},
            a={
                "type": "acl",
                "properties": {
                    "resource": "syn456",
                    "grants": [
                        {"principal": 3324230, "access_type": ["READ"]},
                        {"principal": "PUBLIC", "access_type": ["READ"]},
                        {"principal": "authenticated_users", "access_type": ["READ"]},
                    ],
                },
            },
        )
    )
    assert all(s.depends_on == [] for s in specs)


def test_import_and_protect_are_parsed():
    (spec,) = parse_template(
        template(
            p={
                "type": "project",
                "import": "syn9",
                "protect": True,
                "properties": {"name": "P"},
            }
        )
    )
    assert spec.import_id == "syn9"
    assert spec.protect is True


def curator_template(**overrides):
    resources = dict(
        p={"type": "project", "properties": {"name": "P"}},
        raw={"type": "folder", "properties": {"name": "Raw", "parent": "project.p"}},
        ds={"type": "team", "properties": {"name": "DS"}},
        bio={
            "type": "json_schema",
            "properties": {
                "organization": "my.org",
                "name": "Bio",
                "version": "1.0.0",
                "path": "bio.json",
            },
        },
        files={
            "type": "file_based_metadata_task",
            "properties": {
                "folder": "folder.raw",
                "curation_task_name": "BioFiles",
                "instructions": "annotate",
                "schema": "json_schema.bio",
                "assignee": "team.ds",
                "view_type_mask": ["file", "FOLDER"],
            },
        },
        records={
            "type": "record_based_metadata_task",
            "properties": {
                "folder": "syn99",
                "record_set_name": "R",
                "record_set_description": "d",
                "curation_task_name": "BioRecords",
                "upsert_keys": ["specimenID"],
                "instructions": "fill in",
                "schema": "org.other-Thing-1.0.0",
            },
        },
    )
    resources.update(overrides)
    return template(**resources)


@pytest.fixture
def schema_dir(tmp_path):
    body = {"$id": "ignored", "type": "object", "properties": {"specimenID": {}}}
    (tmp_path / "bio.json").write_text(json.dumps(body))
    return tmp_path


def test_curator_resources(schema_dir):
    specs = {s.logical_name: s for s in parse_template(curator_template(), schema_dir)}
    # Synapse sets the schema's $id itself.
    assert specs["bio"].schema_body == {
        "type": "object",
        "properties": {"specimenID": {}},
    }
    assert sorted(specs["files"].depends_on) == ["bio", "ds", "raw"]
    # A literal schema URI and Synapse ID need no dependency.
    assert specs["records"].depends_on == []


def test_inline_schema_needs_no_file():
    (spec,) = parse_template(
        template(
            s={
                "type": "json_schema",
                "properties": {
                    "organization": "my.org",
                    "name": "n",
                    "version": "0.0.1",
                    "schema": {"type": "object"},
                },
            }
        )
    )
    assert spec.schema_body == {"type": "object"}


def test_schema_organization(schema_dir):
    config = curator_template(
        org={
            "type": "schema_organization",
            "import": "example.org",
            "properties": {
                "name": "example.org",
                "grants": [{"principal": "team.ds", "access_type": ["CREATE"]}],
            },
        }
    )
    config["resources"]["bio"]["properties"]["organization"] = "schema_organization.org"
    specs = {s.logical_name: s for s in parse_template(config, schema_dir)}
    assert specs["org"].import_id == "example.org"
    assert specs["org"].depends_on == ["ds"]
    assert specs["bio"].depends_on == ["org"]
    order = [s.logical_name for s in parse_template(config, schema_dir)]
    assert order.index("org") < order.index("bio") < order.index("files")


def test_view_type_mask():
    assert view_type_mask("FILE") == 1
    assert view_type_mask(["file", "folder"]) == 9
    assert view_type_mask(33) == 33
    with pytest.raises(TemplateError, match="unknown view type"):
        view_type_mask(["FILE", "WIKI"])


def _with(name, **props):
    """``curator_template`` with properties of one resource replaced."""
    config = curator_template()
    resource = config["resources"][name]
    resource["properties"] = {**resource["properties"], **props}
    for key, value in props.items():
        if value is None:
            del resource["properties"][key]
    return config


@pytest.mark.parametrize(
    "config, message",
    [
        (_with("bio", version="1.0"), "version must look like"),
        (_with("bio", organization="my_org"), "invalid organization name"),
        (
            _with("bio", organization="schema_organization.nope"),
            "unknown resource 'nope'",
        ),
        (_with("bio", organization="schema_organization.ds"), "refers to a team"),
        (
            curator_template(
                o={
                    "type": "schema_organization",
                    "properties": {"name": "org.sagebionetworks"},
                }
            ),
            "invalid organization name",
        ),
        (
            curator_template(
                o={"type": "schema_organization", "properties": {"name": "1st.org"}}
            ),
            "invalid organization name",
        ),
        (
            curator_template(
                o={
                    "type": "schema_organization",
                    "import": "other.org",
                    "properties": {"name": "example.org"},
                }
            ),
            "'import' must be the organization name",
        ),
        (
            curator_template(
                o={
                    "type": "schema_organization",
                    "properties": {"name": "example.org", "grants": [{"principal": 1}]},
                }
            ),
            "needs principal and access_type",
        ),
        (_with("bio", version="0.0.0"), "version must look like"),
        (_with("bio", path=None), "exactly one of 'path' or 'schema'"),
        (_with("bio", schema={"type": "object"}), "exactly one of 'path' or 'schema'"),
        (_with("bio", path="missing.json"), "not found"),
        (_with("files", schema="json_schema.nope"), "unknown resource 'nope'"),
        (
            _with("files", schema="json_schema.ds"),
            "refers to a team, not a json_schema",
        ),
        (_with("files", folder="team.ds"), "invalid reference"),
        (_with("files", authorization_mode="ANYONE"), "authorization_mode must be"),
        (_with("files", view_type_mask="WIKI"), "unknown view type"),
        (_with("files", column_order="age"), "column_order: must be a list"),
        (_with("records", upsert_keys=[]), "upsert_keys: must be a non-empty list"),
        (_with("records", schema=None), "missing properties \\['schema'\\]"),
        (
            curator_template(
                b={
                    "type": "schema_binding",
                    "import": "syn1",
                    "properties": {"resource": "syn1", "schema": "o-n-1.0.0"},
                }
            ),
            "'import' is not supported for schema_binding",
        ),
    ],
)
def test_invalid_curator_templates(schema_dir, config, message):
    with pytest.raises(TemplateError, match=message):
        parse_template(config, schema_dir)


@pytest.mark.parametrize(
    "config, message",
    [
        ({}, "non-empty 'resources'"),
        (template(x={"type": "wiki", "properties": {}}), "unknown type 'wiki'"),
        (template(x={"type": "folder", "properties": {"name": "X"}}), "missing"),
        (
            template(
                x={"type": "folder", "properties": {"name": "X", "parent": "nope"}}
            ),
            "invalid reference",
        ),
        (
            template(
                x={
                    "type": "folder",
                    "properties": {"name": "X", "parent": "project.missing"},
                }
            ),
            "unknown resource 'missing'",
        ),
        (
            template(
                t={"type": "team", "properties": {"name": "T"}},
                x={"type": "folder", "properties": {"name": "X", "parent": "folder.t"}},
            ),
            "refers to a team, not a folder",
        ),
        (
            template(
                a={"type": "folder", "properties": {"name": "A", "parent": "folder.b"}},
                b={"type": "folder", "properties": {"name": "B", "parent": "folder.a"}},
            ),
            "cycle",
        ),
        (
            template(
                a={
                    "type": "acl",
                    "import": "syn1",
                    "properties": {"resource": "syn1", "grants": []},
                }
            ),
            "not supported for acl",
        ),
        (
            template(
                a={
                    "type": "acl",
                    "properties": {"resource": "syn1", "grants": [{"principal": 1}]},
                }
            ),
            "needs principal and access_type",
        ),
    ],
)
def test_invalid_templates(config, message):
    with pytest.raises(TemplateError, match=message):
        parse_template(config)
