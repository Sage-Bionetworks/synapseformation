# synapseformation

[![Get synapseformation from PyPI](https://img.shields.io/pypi/v/synapseformation.svg?&logo=pypi)](https://pypi.python.org/pypi/synapseformation)
[![Coverage Status](https://img.shields.io/coveralls/github/Sage-Bionetworks/synapseformation.svg?&label=coverage&logo=Coveralls)](https://coveralls.io/github/Sage-Bionetworks/synapseformation)
[![build](https://github.com/Sage-Bionetworks/synapseformation/actions/workflows/ci.yml/badge.svg)](https://github.com/Sage-Bionetworks/synapseformation/actions/workflows/ci.yml)

> [!WARNING]
> This package is not actively maintained and is an MVP. The functionality and dependencies may change at any time, but will follow semantic versioning guidelines. Use at your own risk.


Client for using [Synapse Formation Templates](templates). Given one of these templates, `synapseformation` will be able to create all the components required in a Synapse Project.  Currently the implementation does one of these two scenarios.

* Only creates new entities, will fail if entity already exists.
* Create entities that don't exist and gets the entity if it already exists, but does not update an entity.

## Usage

### Command Line

`synapseformation` has a command line client that will create resources given a `yaml` or `json` template.

```bash
synapseformation create --help
Usage: synapseformation create [OPTIONS]

  Creates Synapse Resources

Options:
  --template_path PATH  Template path
  --help                Show this message and exit.
```

### Python

These are some of the lower level functions that exist in the package.
```
import synapseclient
from synapseformation import create

syn = synapseclient.login()
# Only create entities
CreateCls = create.SynapseCreation(syn)
# Only retrieve entities (don't update)
RetrieveCls = create.SynapseCreation(syn, only_get=True)
```

## Contributing
Please view our [contributing guide](CONTRIBUTING.md)
