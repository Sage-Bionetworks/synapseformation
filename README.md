# synapseformation

[![Get synapseformation from PyPI](https://img.shields.io/pypi/v/synapseformation.svg?style=for-the-badge&logo=pypi)](https://pypi.python.org/pypi/synapseformation) [![GitHub CI](https://img.shields.io/github/workflow/status/Sage-Bionetworks/synapseformation/build.svg?color=94398d&labelColor=555555&logoColor=ffffff&style=for-the-badge&logo=github)](https://github.com/Sage-Bionetworks/synapseformation)
[![Coverage Status](https://img.shields.io/coveralls/github/Sage-Bionetworks/synapseformation.svg?&style=for-the-badge&label=coverage&logo=Coveralls)](https://coveralls.io/github/Sage-Bionetworks/synapseformation)


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
