"""Synapse Formation client"""
import synapseclient
import yaml

from .create import SynapseCreation


def get_yaml_config(template_path: str) -> dict:
    """Get yaml synapse formation template"""
    with open(template_path, "r") as template_f:
        template = yaml.load(template_f, Loader=yaml.FullLoader)
    return template


def _create_synapse_resources_yamlanchor(syn, config: dict, parentid: str = None):
    """Creates synapse resources using yaml anchor template"""
    creation_cls = SynapseCreation(syn)
    if isinstance(config, dict) and config.get('type') == "Project":
        # TODO: remove
        config['name'] = "tyu-test TREAD_AD_YAML"
        project = creation_cls.get_or_create_project(name=config['name'])
        parent_id = project.id
        # Must call create synapse resources
        children = config.get('next_level')
        # Add project level folders into the first "next_level"
        if children is not None:
            _create_synapse_resources_yamlanchor(syn, children, parent_id)
    else:
        for folder in config:
            if isinstance(folder, dict):
                folder_name = folder['name']
                children = folder.get('next_level')
            else:
                folder_name = folder
                children = None
            print(folder_name)
            folder_ent = creation_cls.get_or_create_folder(
                name=folder_name, parentId=parentid
            )
            # Create nested folders
            if children is not None:
                _create_synapse_resources_yamlanchor(syn, children, folder_ent.id)


def create_synapse_resources(template_path: str):
    """Creates synapse resources from template"""
    syn = synapseclient.login()
    config = get_yaml_config(template_path)
    _create_synapse_resources_yamlanchor(syn, config)
