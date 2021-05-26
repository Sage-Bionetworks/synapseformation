"""Synapse Formation client"""
import synapseclient
from synapseclient import Synapse

from .create import SynapseCreation
from . import create, utils


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


def _create_synapse_resources(config: dict, creation_cls: SynapseCreation,
                              parentid: str = None):
    """Recursively steps through template and creates synapse resources

    Args:
        syn: Synapse connection
        config: Synapse Formation template dict
        creation_cls: SynapseCreation class that can create resources
        parentid: Synapse folder or project id to store entities
    """
    # Specify entity or there will be an issue when the recursive
    # function is called from within the for loop
    # Error: entity not specified
    entity = None
    if isinstance(config, dict) and config.get('type') == "Project":
        entity = creation_cls.get_or_create_project(name=config['name'])
    elif isinstance(config, dict) and config.get('type') == "Folder":
        entity = creation_cls.get_or_create_folder(
            name=config['name'], parentId=parentid
        )
    else:
        # Loop through folders and create them
        for folder_config in config:
            _create_synapse_resources(folder_config, creation_cls,
                                      parentid=parentid)
    if entity is not None:
        parent_id = entity.id
        config['id'] = parent_id
        # Get ACL if exists
        create._set_acl(syn=creation_cls.syn, entity=entity,
                        acl_config=config.get('acl', []))
        children = config.get('children', [])
        _create_synapse_resources(children, creation_cls,
                                  parentid=parent_id)


def create_synapse_resources(template_path: str):
    """Creates synapse resources from template"""
    # TODO: abstract out login function
    syn = synapseclient.login()
    # Function will attempt to read template as yaml then try to read in json
    config = utils.read_config(template_path)
    # Expands shortended configuration into full configuration.  This should
    # work if full configuration is passed in
    # TODO: Ignore expansion of configuration for now
    # full_config = expand_config(config)
    # Recursive function to create resources
    creation_cls = SynapseCreation(syn)
    for resource in config:
        _create_synapse_resources(resource, creation_cls)
    print(config)
