# synapseformation

[![Get synapseformation from PyPI](https://img.shields.io/pypi/v/synapseformation.svg?&logo=pypi)](https://pypi.python.org/pypi/synapseformation) [![Coverage Status](https://img.shields.io/coveralls/github/Sage-Bionetworks/synapseformation.svg?&label=coverage&logo=Coveralls)](https://coveralls.io/github/Sage-Bionetworks/synapseformation) [![build](https://github.com/Sage-Bionetworks/synapseformation/actions/workflows/ci.yml/badge.svg)](https://github.com/Sage-Bionetworks/synapseformation/actions/workflows/ci.yml)

> [!WARNING]
> This package is not actively maintained and is an MVP. The functionality and dependencies may change at any time, but will follow semantic versioning guidelines. Use at your own risk.

Manage Synapse teams, projects, folders and access controls as code, from a YAML or JSON [template](templates). `synapseformation` runs on the [Pulumi](https://www.pulumi.com/) engine, which handles state, dependency ordering, plans, drift detection and deletes. Each Synapse resource type is a Pulumi dynamic provider written in Python.

## Installation

```
pip install synapseformation
```

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

Useful options: `--diff` for property-level changes, `--yes` to skip confirmation, `--no-refresh` to skip reading Synapse first, and `--stack NAME` to manage several copies of one template.

### State

Each template file gets its own Pulumi stack, named after the file. State is stored in `./.synapseformation/` unless you pass `--backend-url` or set `PULUMI_BACKEND_URL`. For shared use, put state somewhere central, for example `--backend-url s3://my-bucket/synapseformation`.

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

References use `<type>.<logical_name>`. Resources can be listed in any order; dependencies are worked out from the references. `parent` and `resource` may also be an existing Synapse ID such as `syn123`. A `principal` may be a team reference, a numeric principal ID, `PUBLIC` or `AUTHENTICATED_USERS`.

Any team, project or folder can take:

- `import: <id>` to adopt an existing resource. It is updated to match the template and managed from then on, including deletion on `destroy`, so combine it with `protect` if it should outlive the stack.
- `protect: true` to make `apply` and `destroy` refuse to delete it.

### How ACLs behave

An `acl` resource manages grants only for the principals it lists. Other entries, such as the creator's administrator access, are left alone. If the entity was inheriting its permissions, the inherited ACL is copied down first so nobody loses access. Removing the `acl` resource then restores inheritance; otherwise it removes only its own principals.

## Using it from Python

The providers are ordinary Pulumi resources, so they can be used in a Pulumi program directly:

```python
from synapseformation.providers import SynapseProject, SynapseFolder

project = SynapseProject("study", name="Example Study")
SynapseFolder("raw", name="Raw Data", parent_id=project.id)
```

## Contributing

Please view our [contributing guide](CONTRIBUTING.md)
