"""Convenience functions to create Synapse entities"""
import logging
import sys

import synapseclient
from synapseclient import Project, Team, Evaluation, File, Folder, Wiki
from synapseclient.exceptions import SynapseHTTPError

from challengeutils import utils

logger = logging.getLogger(__name__)


def create_project(syn: 'Synapse', project_name: str) -> Project:
    """Creates Synapse Project

    Args:
        syn: Synapse connection
        project_name: Name of project

    Returns:
        Project Entity

    """
    project = Project(project_name)
    # returns the handle to the project if the user has sufficient priviledge
    project = syn.store(project, createOrUpdate=False)
    logger.info('Created/Fetched Project {} ({})'.format(project.name,
                                                         project.id))
    return project


def create_team(syn: 'Synapse', team_name: str, desc: str,
                can_public_join: bool=False) -> Team:
    """Creates Synapse Team

    Args:
        syn: Synapse connection
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


def create_evaluation_queue(syn: 'Synapse', name: str, description:str,
                            parentid: str, quota: dict=None) -> Evaluation:
    """Creates Evaluation Queues

    Args:
        syn: Synapse connection
        name: Name of evaluation queue
        description: Description of queue
        parentid: Synapse project id
        quota: Evaluation queue quota

    Returns:
        Synapse Evaluation Queue

    """

    queue_ent = Evaluation(name=name,
                           description=description,
                           contentSource=parentid)
    queue = syn.store(queue_ent)
    logger.info('Created Queue {}({})'.format(queue.name, queue.id))
    return queue


def create_challenge_widget(syn: 'Synapse', project_live: str,
                            team_part_id: str) -> 'Challenge':
    """Creates challenge widget - activates a Synapse project
    If challenge object exists, it retrieves existing object

    Args:
        syn: Synapse connection
        project_live: Synapse id of live challenge project
        team_part_id: Synapse team id of participant team

    Returns:
        Synapse challenge object

    """
    try:
        challenge = utils.create_challenge(syn, project_live, team_part_id)
        logger.info("Created Challenge ({})".format(challenge.id))
    except SynapseHTTPError:
        challenge = utils.get_challenge(syn, project_live)
        logger.info("Fetched existing Challenge ({})".format(challenge.id))
    return challenge


def create_file(syn: 'Synapse', path: str, parentid: str) -> File:
    """Creates Synapse File

    Args:
        syn: Synapse connection
        path: Path to file
        parentid: Synapse parent id

    Returns:
        Synapse file

    """
    file_ent = File(path, parent=parentid)
    # returns the handle to the file if the user has sufficient priviledge
    file_ent = syn.store(file_ent)
    logger.info('Created/Fetched File {} ({})'.format(file_ent.name,
                                                      file_ent.id))
    return file_ent


def create_folder(syn: 'Synapse', folder_name: str, parentid: str) -> Folder:
    """Creates Synapse Folder

    Args:
        syn: Synapse connection
        folder_name: Name of folder

    Returns:
        Synapse folder

    """
    folder_ent = Folder(folder_name, parent=parentid)
    # returns the handle to the project if the user has sufficient priviledge
    folder_ent = syn.store(folder_ent)
    logger.info('Created/Fetched Folder {} ({})'.format(folder_ent.name,
                                                        folder_ent.id))
    return folder_ent


def create_wiki(syn: 'Synapse', title: str, markdown: str, projectid: str,
                parent_wiki: str) -> Wiki:
    """Creates wiki page

    Args:
        syn: Synapse connection
        title: Title of wiki
        markdown: markdown formatted string
        projectid: Synapse project id,
        parent_wiki: Parent wiki id

    Returns:
        Synapse wiki page

    """
    wiki_ent = Wiki(title=title,
                    markdown=markdown,
                    owner=projectid,
                    parent_wiki=parent_wiki)
    wiki_ent = syn.store(wiki_ent)
    logger.info('Created/Fetched Wiki {} ({})'.format(wiki_ent.name,
                                                      wiki_ent.id))
    return wiki_ent
