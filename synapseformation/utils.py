"""Utility functions"""
import yaml

import synapseclient
from synapseclient.core.exceptions import (
    SynapseNoCredentialsError,
    SynapseAuthenticationError,
)


def read_config(template_path: str) -> dict:
    """Read in yaml or json configuration

    Args:
        template_path: Path to yaml or json configuration

    Returns:
        Configuration
    """
    # JSON is technically yaml but not the other way around.
    # yaml.safe_load can actually read in json files.
    with open(template_path, "r") as template_f:
        config = yaml.safe_load(template_f)
    return config


def synapse_login(synapse_config=synapseclient.client.CONFIG_FILE):
    """Login to Synapse

    Args:
        synapse_config: Path to synapse configuration file.
                        Defaults to ~/.synapseConfig

    Returns:
        Synapse connection
    """
    try:
        syn = synapseclient.Synapse(configPath=synapse_config)
        syn.login(silent=True)
    except (SynapseNoCredentialsError, SynapseAuthenticationError):
        raise ValueError(
            "Login error: please make sure you have correctly "
            "configured your client.  Instructions here: "
            "https://help.synapse.org/docs/Client-Configuration.1985446156.html. "
            "You can also create a Synapse Personal Access Token and set it "
            "as an environmental variable: "
            "SYNAPSE_AUTH_TOKEN='<my_personal_access_token>'"
        )
    return(syn)
