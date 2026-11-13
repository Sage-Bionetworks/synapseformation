"""Tests for template parsing and dependency ordering"""

import pytest

from synapseformation.engine import TemplateError, parse_template


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
