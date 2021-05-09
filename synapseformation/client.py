"""Synapse Formation client"""
import synapseclient
from synapseclient import Synapse

from .create import SynapseCreation
from . import utils


# def expand_config(config: dict) -> dict:
#     """Expands shortened configuration to the official json format"""
#     # TODO: Once all resources are either under a key mapping or lists
#     # this will have to chance
#     if isinstance(config, dict) and config.get('type') == "Project":
#         # TODO: figure out how to clean this up.
#         # Remove yaml anchor objects as they are expanded
#         to_remove = [key for key in config
#                      if key not in ["type", "name", "children"]]
#         for key in to_remove:
#             config.pop(key)
#         # Get children if exists
#         children = config.get('children')
#         if children is not None:
#             expand_config(children)
#     else:
#         # Loop through folders and create them
#         for index, folder in enumerate(config):
#             # The folder configuration can be lists or dicts
#             # Must pull out children if it exists
#             if isinstance(folder, dict):
#                 children = folder.get('children')
#             else:
#                 config[index] = {"name": folder,
#                                  "type": "Folder"}
#                 children = None

#             # Create nested folders
#             if children is not None:
#                 expand_config(children)
#     return config


def _create_synapse_resources(syn: Synapse, config: dict,
                              parentid: str = None):
    """Recursively steps through template and creates synapse resources

    Args:
        syn: Synapse connection
        config: Synapse Formation template dict
        parentid: Synapse folder or project id to store entities
    """
    creation_cls = SynapseCreation(syn)
    if isinstance(config, dict) and config.get('type') == "Project":
        project = creation_cls.get_or_create_project(name=config['name'])
        parent_id = project.id
        config['id'] = parent_id
        # Get children if exists
        children = config.get('children', [])
        _create_synapse_resources(syn, children, parent_id)
    else:
        # Loop through folders and create them
        for folder in config:
            # Must pull out children if it exists
            folder_name = folder['name']
            folder_ent = creation_cls.get_or_create_folder(
                name=folder_name, parentId=parentid
            )
            folder['id'] = folder_ent.id
            # Create nested folders
            children = folder.get('children', [])
            _create_synapse_resources(syn, children, folder_ent.id)


def create_synapse_resources(template_path: str):
    """Creates synapse resources from template"""
    syn = synapseclient.login()
    # Function will attempt to read template as yaml then try to read in json
    config = utils.read_config(template_path)
    # Expands shortended configuration into full configuration.  This should
    # work if full configuration is passed in
    # TODO: Ignore expansion of configuration for now
    # full_config = expand_config(config)
    # Recursive function to create resources
    for resource in config:
        _create_synapse_resources(syn, resource)
    print(config)
