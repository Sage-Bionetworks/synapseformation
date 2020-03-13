"""Convenience functions to create Synapse entities"""
import logging
import sys

from synapseclient import Project, Team, Evaluation, File, Folder, Wiki
from synapseclient.exceptions import SynapseHTTPError

from challengeutils import utils

logger = logging.getLogger(__name__)


class SynapseCreation:
    """Creates Synapse Features"""
    def __init__(self, syn: 'Synapse', create_or_update: bool = False):
        """
        Args:
            syn: Synapse connection
            create_or_update: Default is False, which means resources can
                              only be created and not updated if resource
                              already exists.
        """
        self.syn = syn
        self.create_or_update = create_or_update


    def create_project(self, project_name: str) -> Project:
        """Creates Synapse Project

        Args:
            syn: Synapse connection
            project_name: Name of project

        Returns:
            Project Entity

        """
        project = Project(project_name)
        # returns the handle to the project if the user has sufficient
        # priviledge
        project = self.syn.store(project,
                                 createOrUpdate=self.create_or_update)
        logger.info('Created/Fetched Project {} ({})'.format(project.name,
                                                             project.id))
        return project


    def create_team(self, team_name: str, desc: str,
                    can_public_join: bool = False) -> Team:
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
            team = self.syn.getTeam(team_name)
            logger.info('The team {} already exists.'.format(team_name))
            logger.info(team)
            # If you press enter, this will default to 'y'
            user_input = input('Do you want to use this team? (Y/n) ') or 'y'
            if user_input.lower() not in ('y', 'yes'):
                logger.info('Please specify a new challenge name. Exiting.')
                sys.exit(1)
        except ValueError:
            team = Team(name=team_name,
                        description=desc,
                        canPublicJoin=can_public_join)
            # raises a ValueError if a team with this name already exists
            team = self.syn.store(team)
            logger.info('Created Team {} ({})'.format(team.name, team.id))
        return team


    def create_evaluation_queue(self, name: str, description: str,
                                parentid: str, quota: dict = None) -> Evaluation:
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
                               contentSource=parentid,
                               quota=quota)
        queue = self.syn.store(queue_ent)
        logger.info('Created Queue {}({})'.format(queue.name, queue.id))
        return queue


    def create_challenge_widget(self, project_live: str,
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
            challenge = utils.create_challenge(self.syn, project_live,
                                               team_part_id)
            logger.info("Created Challenge ({})".format(challenge.id))
        except SynapseHTTPError:
            challenge = utils.get_challenge(self.syn, project_live)
            logger.info("Fetched existing Challenge ({})".format(challenge.id))
        return challenge


    def create_file(self, path: str, parentid: str) -> File:
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
        file_ent = self.syn.store(file_ent,
                                  createOrUpdate=self.create_or_update)
        logger.info('Created/Fetched File {} ({})'.format(file_ent.name,
                                                          file_ent.id))
        return file_ent


    def create_folder(self, folder_name: str, parentid: str) -> Folder:
        """Creates Synapse Folder

        Args:
            syn: Synapse connection
            folder_name: Name of folder

        Returns:
            Synapse folder

        """
        folder_ent = Folder(folder_name, parent=parentid)
        # returns the handle to the project if the user has sufficient
        # priviledge
        folder_ent = self.syn.store(folder_ent,
                                    createOrUpdate=self.create_or_update)
        logger.info('Created/Fetched Folder {} ({})'.format(folder_ent.name,
                                                            folder_ent.id))
        return folder_ent


    def create_wiki(self, title: str, markdown: str, projectid: str,
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
        wiki_ent = self.syn.store(wiki_ent)
        logger.info('Created/Fetched Wiki {} ({})'.format(wiki_ent.name,
                                                          wiki_ent.id))
        return wiki_ent
