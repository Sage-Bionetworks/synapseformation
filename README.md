# synapseformation

[![Get synapseformation from PyPI](https://img.shields.io/pypi/v/synapseformation.svg?&logo=pypi)](https://pypi.python.org/pypi/synapseformation)
[![Coverage Status](https://img.shields.io/coveralls/github/Sage-Bionetworks/synapseformation.svg?&label=coverage&logo=Coveralls)](https://coveralls.io/github/Sage-Bionetworks/synapseformation)
[![build](https://github.com/Sage-Bionetworks/synapseformation/actions/workflows/ci.yml/badge.svg)](https://github.com/Sage-Bionetworks/synapseformation/actions/workflows/ci.yml)

> [!WARNING]
> This package is not actively maintained and is an MVP. The functionality and dependencies may change at any time, but will follow semantic versioning guidelines. Use at your own risk.


Client for using [Synapse Formation Templates](templates). Given one of these templates, `synapseformation` will be able to create all the components required in a Synapse Project.  Currently the implementation does one of these two scenarios.

## Usage

### Command Line

`synapseformation` has a command line client that will create resources given a `yaml` or `json` template.

```bash
Usage: synapseformation [OPTIONS] COMMAND [ARGS]...

  synapseformation is a tool to manage Synapse resources via configuration
  files.

Options:
  -V, --version  Show the version and exit.
  --help         Show this message and exit.

Commands:
  apply  Creates Synapse Resources given a yaml or json
  plan   Creates Synapse Resources given a yaml or json
```

## Contributing
Please view our [contributing guide](CONTRIBUTING.md)
