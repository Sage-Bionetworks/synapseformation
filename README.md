# synapseformation
Client for using [Synapse Formation Templates](https://github.com/Sage-Bionetworks/synapse-formation-templates). Given one of these templates, `synapseformation` will be able to create all the components required in a Synapse Project.

## Usage
```
import synapseclient
from synapseformation import create

syn = synapseclient.login()
# Only create entities
CreateCls = create.SynapseCreation(syn)
# Only retrieve entities (don't update)
RetrieveCls = create.SynapseCreation(syn, only_create=False)
```

## Contributing
Please view our [contributing guide](CONTRIBUTING.md)