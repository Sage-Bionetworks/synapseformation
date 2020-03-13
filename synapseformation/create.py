"""Convenience functions to create Synapse entities"""
import logging
import sys

import synapseclient
from synapseclient.exceptions import SynapseHTTPError

from challengeutils import utils

logger = logging.getLogger(__name__)


def create_project(syn, project_name):
    """Creates Synapse Project

    Args:
        syn: Synpase object
        project_name: Name of project

    Returns:
        Project Entity
    """
    project = synapseclient.Project(project_name)
    # returns the handle to the project if the user has sufficient priviledge
    project = syn.store(project, createOrUpdate=False)
    logger.info('Created/Fetched Project {} ({})'.format(project.name,
                                                         project.id))
    return project


def create_team(syn, team_name, desc, can_public_join=False):
    """Creates Synapse Team

    Args:
        syn: Synpase object
        team_name: Name of team
        desc: Description of team
        can_public_join: true for teams which members can join without
                         an invitation or approval. Default to False

    Returns:
        Synapse Team id
    """
    try:
        # raises a ValueError if a team does not exist
        team = syn.getTeam(team_name)
        logger.info('The team {} already exists.'.format(team_name))
        logger.info(team)
        # If you press enter, this will default to 'y'
        user_input = input('Do you want to use this team? (Y/n) ') or 'y'
        if user_input.lower() not in ('y', 'yes'):
            logger.info('Please specify a new challenge name. Exiting.')
            sys.exit(1)
    except ValueError:
        team = synapseclient.Team(name=team_name,
                                  description=desc,
                                  canPublicJoin=can_public_join)
        # raises a ValueError if a team with this name already exists
        team = syn.store(team)
        logger.info('Created Team {} ({})'.format(team.name, team.id))
    return team


def create_evaluation_queue(syn, name, description, parentid,
                            quota=None):
    """Creates Evaluation Queues

    Args:
        syn: Synpase object
        name: Name of evaluation queue
        description: Description of queue
        parentid: Synapse project id

    Returns:
        Evalation Queue
    """

    queue_ent = synapseclient.Evaluation(name=name,
                                         description=description,
                                         contentSource=parentid)
    queue = syn.store(queue_ent)
    logger.info('Created Queue {}({})'.format(queue.name, queue.id))
    return queue


def create_challenge_widget(syn, project_live, team_part_id):
    """Creates challenge widget - activates a Synapse project
    If challenge object exists, it retrieves existing object

    Args:
        syn: Synpase object
        project_live: Synapse id of live challenge project
        team_part_id: Synapse team id of participant team

    Returns:
        Challenge object
    """
    try:
        challenge = utils.create_challenge(syn, project_live, team_part_id)
        logger.info("Created Challenge ({})".format(challenge.id))
    except SynapseHTTPError:
        challenge = utils.get_challenge(syn, project_live)
        logger.info("Fetched existing Challenge ({})".format(challenge.id))
    return challenge


def create_file(syn, path, parentid):
    """Creates Synapse File

    Args:
        syn: Synpase object
        path: Path to file
        parentid: Synapse parent id

    Returns:
        File Entity
    """
    file_ent = synapseclient.File(path, parent=parentid)
    # returns the handle to the file if the user has sufficient priviledge
    file_ent = syn.store(file_ent)
    logger.info('Created/Fetched File {} ({})'.format(file_ent.name,
                                                      file_ent.id))
    return file_ent


def create_folder(syn, folder_name, parentid):
    """Creates Synapse Folder

    Args:
        syn: Synpase object
        folder_name: Name of folder

    Returns:
        Folder Entity
    """
    folder_ent = synapseclient.Folder(folder_name, parent=parentid)
    # returns the handle to the project if the user has sufficient priviledge
    folder_ent = syn.store(folder_ent)
    logger.info('Created/Fetched Folder {} ({})'.format(folder_ent.name,
                                                        folder_ent.id))
    return folder_ent


def create_wiki(syn, title, markdown, projectid, parent_wiki):
    """Creates wiki page

    Args:
        syn: Synapse object
        title: Title of wiki
        markdown: markdown formatted string
        projectid: Synapse project id,
        parent_wiki: Parent wiki id

    Returns:
        wiki
    """
    wiki_ent = synapseclient.Wiki(title=title,
                                  markdown=markdown,
                                  owner=projectid,
                                  parent_wiki=parent_wiki)
    wiki_ent = syn.store(wiki_ent)
    logger.info('Created/Fetched Wiki {} ({})'.format(wiki_ent.name,
                                                      wiki_ent.id))
    return wiki_ent
