# synapseformation
Client for using [Synapse Formation Templates](https://github.com/Sage-Bionetworks/synapse-formation-templates). Given one of these templates, `synapseformation` will be able to create all the components required in a Synapse Project.  Currently the implementation does one of these two scenarios.

* Only creates new entities, will fail if entity already exists.
* Create entities that don't exist and gets the entity if it already exists, but does not update an entity.

## Usage
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