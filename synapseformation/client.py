"""Synapse Formation client"""
from typing import List

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


def _create_synapse_resources(config_list: List[dict],
                              creation_cls: SynapseCreation,
                              get_cls: SynapseCreation,
                              parentid: str = None):
    """Recursively steps through template and creates synapse resources

    Args:
        config_list: List of Synapse resources
        creation_cls: SynapseCreation class that can create resources
        parentid: Synapse folder or project id to store entities
    """
    # Specify entity or there will be an issue when the recursive
    # function is called from within the for loop
    # Error: entity not specified
    entity = None
    # Must iterate through list to avoid recursion limit issue
    # This works because every layer in the json is a list
    for config in config_list:
        get_or_create_cls = (
            creation_cls if config.get("id") is None else get_cls
        )
        if isinstance(config, dict) and config.get('type') == "Project":
            entity = get_or_create_cls.get_or_create_project(
                name=config['name']
            )
        elif isinstance(config, dict) and config.get('type') == "Folder":
            entity = get_or_create_cls.get_or_create_folder(
                name=config['name'], parentId=parentid
            )
        elif isinstance(config, dict) and config.get('type') == "Team":
            team = get_or_create_cls.get_or_create_team(
                name=config['name'], description=config['description'],
                canPublicJoin=config['can_public_join']
            )
            config['id'] = team.id
            if config.get("invitations") is not None:
                for invite in config['invitations']:
                    for member in invite['members']:
                        user = member.get("principal_id")
                        email = member.get("email")
                        get_or_create_cls.syn.invite_to_team(
                            team=team, user=user, inviteeEmail=email,
                            message=invite['message']
                        )
        # only entities can have children and ACLs
        if entity is not None:
            parent_id = entity.id
            config['id'] = parent_id
            # Get ACL if exists
            create._set_acl(syn=creation_cls.syn, entity=entity,
                            acl_config=config.get('acl', []))
            children = config.get('children', None)
            # implement this to not run into recursion limit
            if children is not None:
                _create_synapse_resources(config_list=children,
                                          creation_cls=creation_cls,
                                          get_cls=get_cls,
                                          parentid=parent_id)


def create_synapse_resources(syn: synapseclient.Synapse, template_path: str):
    """Creates synapse resources from template"""
    # Function will attempt to read template as yaml then try to read in json
    config = utils.read_config(template_path)
    # Expands shortended configuration into full configuration.  This should
    # work if full configuration is passed in
    # TODO: Ignore expansion of configuration for now
    # full_config = expand_config(config)
    # Recursive function to create resources
    creation_cls = SynapseCreation(syn)
    get_cls = SynapseCreation(syn, only_get=True)
    _create_synapse_resources(config_list=config, creation_cls=creation_cls,
                              get_cls=get_cls)
    print(config)
