"""Synapse Formation client"""
import synapseclient
from synapseclient import Synapse
import yaml

from .create import SynapseCreation


def get_yaml_config(template_path: str) -> dict:
    """Get yaml synapse formation template

    Args:
        template_path: Path to yaml synapse formation template

    Returns:
        dict for synapse configuration
    """
    with open(template_path, "r") as template_f:
        template = yaml.load(template_f, Loader=yaml.FullLoader)
    return template


def _create_synapse_resources_yamlanchor(syn: Synapse, config: dict,
                                         parentid: str = None):
    """Creates synapse resources using yaml anchor template

    Args:
        syn: Synapse connection
        config: Synapse Formation template dict
        parentid: Synapse folder or project id to store entities
    """
    creation_cls = SynapseCreation(syn)
    if isinstance(config, dict) and config.get('type') == "Project":
        # TODO: remove this testing code
        config['name'] = "tyu-test TREAD_AD_YAML"
        project = creation_cls.get_or_create_project(name=config['name'])
        parent_id = project.id
        # Get children if exists
        children = config.get('next_level')
        if children is not None:
            _create_synapse_resources_yamlanchor(syn, children, parent_id)
    else:
        # Loop through folders and create them
        for folder in config:
            # The folder configuration can be lists or dicts
            # Must pull out "children" if next_level exists
            if isinstance(folder, dict):
                folder_name = folder['name']
                children = folder.get('next_level')
            else:
                folder_name = folder
                children = None
            folder_ent = creation_cls.get_or_create_folder(
                name=folder_name, parentId=parentid
            )
            # Create nested folders
            if children is not None:
                _create_synapse_resources_yamlanchor(
                    syn, children, folder_ent.id
                )


def create_synapse_resources(template_path: str):
    """Creates synapse resources from template"""
    syn = synapseclient.login()
    config = get_yaml_config(template_path)
    _create_synapse_resources_yamlanchor(syn, config)
