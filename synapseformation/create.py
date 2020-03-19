"""Convenience functions to create Synapse entities"""
import logging
from logging import Logger
import json
from urllib.parse import quote

from synapseclient import Project, Team, Evaluation, File, Folder, Wiki
from synapseclient import EntityViewSchema, Table
from synapseclient.exceptions import SynapseHTTPError

from challengeutils import utils


class SynapseCreation:
    """Creates Synapse Features"""
    def __init__(self, syn: 'Synapse', only_create: bool = True,
                 logger: Logger = None):
        """
        Args:
            syn: Synapse connection
            only_create: Only create entities.  Default is True, which
                         means creation will fail if resource already exists.
        """
        self.syn = syn
        self.only_create = only_create
        self.logger = logger or logging.getLogger(__name__)
        self._update_str = "Fetched existing" if only_create else "Created"

    def _find_by_name_or_create(self, entity: 'Entity') -> 'Entity':
        """Gets an existing entity by name and parent or create a new one.

        Args:
            entity: synapseclient.Entity type

        Returns:
            synapseclient.Entity
        """
        try:
            entity = self.syn.store(entity, createOrUpdate=False)
        except SynapseHTTPError:
            if self.only_create:
                raise ValueError("only_create is set to True.")
            body = json.dumps({"parentId": entity.properties.get("parentId", None),  # pylint: disable=line-too-long
                               "entityName": entity.name})
            entity_obj = self.syn.restPOST("/entity/child", body=body)
            entity_tmp = self.syn.get(entity_obj['id'], downloadFile=False)
            assert entity.properties.concreteType == entity_tmp.properties.concreteType, "Different types."  # pylint: disable=line-too-long
            entity = entity_tmp
        return entity

    def get_or_create_project(self, *args, **kwargs) -> Project:
        """Creates Synapse Project

        Args:
            Same arguments as synapseclient.Project

        Returns:
            A synapseclient.Project

        """
        project = Project(*args, **kwargs)
        project = self._find_by_name_or_create(project)
        self.logger.info('{} Project {}({})'.format(self._update_str,
                                                    project.name,
                                                    project.id))
        return project

    def get_or_create_team(self, name, *args, **kwargs) -> Team:
        """Creates Synapse Team

        Args:
            name: Name of Team
            Same arguments as synapseclient.Team

        Returns:
            A synapseclient.Team

        """
        try:
            team = Team(name=name, *args, **kwargs)
            team = self.syn.store(team, createOrUpdate=False)
        except SynapseHTTPError:
            if self.only_create:
                raise ValueError("only_create is set to True.")
            team = self.syn.getTeam(name)
        self.logger.info('{} Team {} ({})'.format(self._update_str,
                                                  team.name,
                                                  team.id))
        return team

    def create_evaluation_queue(self, name: str, parentid: str,
                                description: str = None,
                                quota: dict = None) -> Evaluation:
        """Creates Evaluation Queues

        Args:
            syn: Synapse connection
            name: Name of evaluation queue
            parentid: Synapse project id
            description: Description of queue
            quota: Evaluation queue quota

        Returns:
            Synapse Evaluation Queue

        """
        if self.only_create:
            url_name = quote(name)
            queue = self.syn.restGET(f"/evaluation/name/{url_name}")
            queue = Evaluation(**queue)
        else:
            queue_ent = Evaluation(name=name,
                                   description=description,
                                   contentSource=parentid,
                                   quota=quota)
            # Throws SynapseHTTPError is queue already exists
            queue = self.syn.store(queue_ent,
                                   createOrUpdate=self.only_create)
        self.logger.info('{} Queue {}({})'.format(self._update_str,
                                                  queue.name, queue.id))
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
        if self.only_create:
            challenge = utils.get_challenge(self.syn, project_live)
        else:
            challenge = utils.create_challenge(self.syn, project_live,
                                               team_part_id)
        self.logger.info("{} Challenge ({})".format(self._update_str,
                                                    challenge.id))
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
                                  createOrUpdate=self.only_create)
        self.logger.info('{} File {} ({})'.format(self._update_str,
                                                  file_ent.name,
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
                                    createOrUpdate=self.only_create)
        self.logger.info('{} Folder {} ({})'.format(self._update_str,
                                                    folder_ent.name,
                                                    folder_ent.id))
        return folder_ent

    def create_wiki(self, title: str, projectid: str, markdown: str = None,
                    parent_wiki: str = None) -> Wiki:
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
        wiki_ent = Wiki(title=title, markdown=markdown, owner=projectid,
                        parentWikiId=parent_wiki)
        # Create or update won't make a difference for subwiki pages
        # because there is no restriction on names.  So you could
        # have duplicated wiki title names
        wiki_ent = self.syn.store(wiki_ent,
                                  createOrUpdate=self.only_create)
        self.logger.info('{} Wiki {}'.format(self._update_str,
                                             wiki_ent.title))
        return wiki_ent

    def get_or_create_view(self, *args, **kwargs):
        """Wrapper to get an entity view by name, or create one if not found.

        Args:
            Same arguments as synapseclient.EntityViewSchema

        Returns:
            A synapseclient.EntityViewSchema.
        """
        view = EntityViewSchema(*args, **kwargs)
        view = self._find_by_name_or_create(view)
        return view