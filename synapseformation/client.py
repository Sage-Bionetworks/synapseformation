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


def _add_acl(syn, entity, acl_config):
    """Adds ACLs to Synapse entity"""
    for acl in acl_config:
        syn.setPermissions(entity=entity, principalId=acl['principal_id'],
                           accessType=acl['access_type'])


def _create_synapse_resources(config: dict, creation_cls: SynapseCreation,
                              parentid: str = None):
    """Recursively steps through template and creates synapse resources

    Args:
        syn: Synapse connection
        config: Synapse Formation template dict
        creation_cls: SynapseCreation class that can create resources
        parentid: Synapse folder or project id to store entities
    """
    if isinstance(config, dict) and config.get('type') == "Project":
        project_ent = creation_cls.get_or_create_project(name=config['name'])
        _add_acl(creation_cls.syn, project_ent, config.get('acl', []))
        parent_id = project_ent.id
        config['id'] = parent_id
        # Get children if exists
        children = config.get('children', [])
        _create_synapse_resources(children, creation_cls,
                                  parentid=parent_id)
    else:
        # Loop through folders and create them
        for folder in config:
            # Must pull out children if it exists
            folder_name = folder['name']
            folder_ent = creation_cls.get_or_create_folder(
                name=folder_name, parentId=parentid
            )
            _add_acl(creation_cls.syn, folder_ent, folder.get('acl', []))
            folder['id'] = folder_ent.id
            # Create nested folders
            children = folder.get('children', [])
            _create_synapse_resources(children, creation_cls,
                                      parentid=folder_ent.id)


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
