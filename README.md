# synapseformation

[![Get synapseformation from PyPI](https://img.shields.io/pypi/v/synapseformation.svg?&logo=pypi)](https://pypi.python.org/pypi/synapseformation) [![Coverage Status](https://img.shields.io/coveralls/github/Sage-Bionetworks/synapseformation.svg?&label=coverage&logo=Coveralls)](https://coveralls.io/github/Sage-Bionetworks/synapseformation) [![build](https://github.com/Sage-Bionetworks/synapseformation/actions/workflows/ci.yml/badge.svg)](https://github.com/Sage-Bionetworks/synapseformation/actions/workflows/ci.yml)

> [!WARNING]
> This package is not actively maintained and is an MVP. The functionality and dependencies may change at any time, but will follow semantic versioning guidelines. Use at your own risk.

> [!CAUTION]
> This project is completely AI vibe coded. Read what `plan` says it will change before you `apply`, and try new templates against Synapse staging (`--staging`) first.

Manage Synapse teams, projects, folders, access controls, JSON schemas and metadata curation tasks as code, from a YAML or JSON [template](templates). `synapseformation` runs on the [Pulumi](https://www.pulumi.com/) engine, which handles state, dependency ordering, plans, drift detection and deletes. Each Synapse resource type is a Pulumi dynamic provider written in Python on top of the `synapseclient` object models.

## Installation

```
pip install synapseformation
```

`synapseformation` supports Python 3.11 to 3.15.

You also need the [Pulumi CLI](https://www.pulumi.com/docs/install/). No Pulumi Cloud account is needed: state is kept locally by default.

Synapse credentials are read from `SYNAPSE_AUTH_TOKEN` or `~/.synapseConfig`. Run commands from an activated virtual environment that has `synapseformation` installed, because Pulumi runs the providers in a separate Python process.

## Usage

```
synapseformation plan TEMPLATE      # show what would change (reads Synapse first to catch drift)
synapseformation apply TEMPLATE     # create, update and delete to match the template
synapseformation refresh TEMPLATE   # update state from Synapse without changing anything
synapseformation output TEMPLATE    # print the Synapse ID of each resource
synapseformation destroy TEMPLATE   # delete everything this template manages
```

Useful options: `--diff` for property-level changes, `--yes` to skip confirmation, `--no-refresh` to skip reading Synapse first, `--stack NAME` to manage several copies of one template, and `--staging` to work against Synapse staging (`https://staging.synapse.org`) instead of production. `SYNAPSEFORMATION_STAGING=1` does the same as `--staging`.

### State

Each template file gets its own Pulumi stack, named after the file. State is stored in `./.synapseformation/` unless you pass `--backend-url` or set `PULUMI_BACKEND_URL`. For shared use, put state somewhere central, for example `--backend-url s3://my-bucket/synapseformation`.

With `--staging` the stack is named `<template>-staging`. Staging is a copy of production, so the same Synapse IDs exist in both; each stack records which one it manages, and `synapseformation` refuses to run a stack against the other.

## Templates

```yaml
version: 1
name: "Example"
resources:
  data_scientists:
    type: team
    properties:
      name: "Example Data Scientists"
      description: "Analysts on the study"

  study_project:
    type: project
    protect: true            # refuse to delete
    properties:
      name: "Example Study"

  raw_data:
    type: folder
    properties:
      name: "Raw Data"
      parent: project.study_project

  raw_data_acl:
    type: acl
    properties:
      resource: folder.raw_data
      grants:
        - principal: team.data_scientists
          access_type: [READ, DOWNLOAD]
        - principal: AUTHENTICATED_USERS
          access_type: [READ]
```

| Type | Properties |
| --- | --- |
| `team` | `name`, `description`, `can_public_join` |
| `project` | `name`, `description` |
| `folder` | `name`, `parent`, `description` |
| `acl` | `resource`, `grants` (list of `principal` and `access_type`) |
| `schema_organization` | `name`, `grants` (as for `acl`) |
| `json_schema` | `organization`, `name`, `version`, and `path` (a JSON file, relative to the template) or `schema` (inline) |
| `schema_binding` | `resource`, `schema`, `enable_derived_annotations` |
| `file_based_metadata_task` | `folder`, `curation_task_name`, `instructions`, `schema`, `enable_derived_annotations`, `entity_view_name`, `view_type_mask`, `column_order`, `assignee`, `authorization_mode` |
| `record_based_metadata_task` | `folder`, `record_set_name`, `record_set_description`, `curation_task_name`, `upsert_keys`, `instructions`, `schema`, `bind_schema_to_record_set`, `enable_derived_annotations`, `column_order`, `assignee`, `authorization_mode` |

References use `<type>.<logical_name>`. Resources can be listed in any order; dependencies are worked out from the references. `parent`, `resource` and `folder` may also be an existing Synapse ID such as `syn123`. A `principal` or `assignee` may be a team reference or a numeric principal ID, and a `principal` may also be `PUBLIC` or `AUTHENTICATED_USERS`. A `schema` may be a `json_schema.<name>` reference or the URI of a schema already registered in Synapse, and an `organization` may be a `schema_organization.<name>` reference or the name of an existing organization.

Any team, project, folder or schema organization can take:

- `import: <id>` to adopt an existing resource (for an organization, its name). It is updated to match the template and managed from then on, including deletion on `destroy`, so combine it with `protect` if it should outlive the stack.
- `protect: true` to make `apply` and `destroy` refuse to delete it.

### How ACLs behave

An `acl` resource manages grants only for the principals it lists. Other entries, such as the creator's administrator access, are left alone. If the entity was inheriting its permissions, the inherited ACL is copied down first so nobody loses access. Removing the `acl` resource then restores inheritance; otherwise it removes only its own principals.

### Metadata curation

The curation types cover what the `synapseclient.extensions.curator` functions do, as resources that can be planned, updated and deleted. See [`templates/curator_template.yaml`](templates/curator_template.yaml) for a full example.

```yaml
  example_org:
    type: schema_organization
    properties:
      name: "example.org"
      grants:
        - principal: team.curators
          access_type: [CREATE, READ]

  biospecimen_schema:
    type: json_schema            # register_jsonschema
    properties:
      organization: schema_organization.example_org
      name: "Biospecimen"
      version: "1.0.0"
      path: schemas/biospecimen.json

  biospecimen_metadata:
    type: record_based_metadata_task   # create_record_based_metadata_task
    properties:
      folder: folder.biospecimen_records
      record_set_name: "Biospecimen records"
      record_set_description: "One row per biospecimen"
      curation_task_name: "BiospecimenRecords"
      upsert_keys: [specimenID]
      instructions: "Fill in one row for every specimen collected."
      schema: json_schema.biospecimen_schema
```

- `schema_organization` creates the organization that schemas are registered in. Organization names are global across Synapse: 6 to 250 characters in dot-separated parts that start with a letter and contain only letters and digits. `grants` work like `acl` grants: only the listed principals are managed, so you keep your own access. Synapse won't delete an organization that still has schemas, so `import` and `protect` it if other people register schemas there too.
- `json_schema` registers one schema version in an organization. A registered version cannot change, so editing the body without bumping `version` is an error. Bumping it registers the new version, points the template's bindings and tasks at it, then deletes the old version. Bindings made outside the template are not moved.
- `schema_binding` is `bind_jsonschema`: it binds a schema to a project or folder.
- `file_based_metadata_task` binds `schema` to the folder (if given; otherwise the folder must already have one), creates a file view with one column per schema property, and creates a file-based curation task. A new schema, `view_type_mask` or `column_order` recreates the view. The view holds no data, since annotations live on the files.
- `record_based_metadata_task` creates a record set whose CSV has one column per schema property (upsert keys first), binds the schema to it unless `bind_schema_to_record_set: false`, and creates a record-based curation task. The schema only shapes the empty CSV: once the record set exists its rows belong to the curators, so later schema changes rebind it but never rewrite or replace it. No Grid is created; curators open grid sessions from the task.
- `view_type_mask` takes a name or list of names (`FILE`, `FOLDER`, ...) or an integer. `authorization_mode` is `SESSION_OWNER` or `SOURCE_BENEFACTOR`.
- Synapse allows one curation task per `curation_task_name` in a project. Renaming one deletes the old task before creating the new one.

## Using it from Python

The providers are ordinary Pulumi resources, so they can be used in a Pulumi program directly:

```python
from synapseformation.providers import SynapseProject, SynapseFolder

project = SynapseProject("study", name="Example Study")
SynapseFolder("raw", name="Raw Data", parent_id=project.id)
```

The curation types are `SynapseSchemaOrganization`, `SynapseJsonSchema`, `SynapseSchemaBinding`, `FileBasedMetadataTask` and `RecordBasedMetadataTask` (the last two are Pulumi components made of `SynapseSchemaView`, `SynapseRecordSet` and `SynapseCurationTask` resources).

## Contributing

Please view our [contributing guide](CONTRIBUTING.md)
