"""Convenience functions to create Synapse entities"""
import logging
from logging import Logger
import json
from urllib.parse import quote

from synapseclient import Project, Team, Evaluation, File, Folder, Wiki
from synapseclient import EntityViewSchema, Schema
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
        """Gets an existing project by name or creates a new one.

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

    def get_or_create_file(self, *args, **kwargs) -> File:
        """Gets an existing file by name and parent or
        creates a new one.

        Args:
            Same arguments as synapseclient.File

        Returns:
            A synapseclient.File

        """
        file_ent = File(*args, **kwargs)
        file_ent = self._find_by_name_or_create(file_ent)
        self.logger.info('{} File {} ({})'.format(self._update_str,
                                                  file_ent.name,
                                                  file_ent.id))
        return file_ent

    def get_or_create_folder(self, *args, **kwargs) -> Folder:
        """Gets an existing folder by name and parent or
        creates a new one.

        Args:
            Same arguments as synapseclient.Folder

        Returns:
            A synapseclient.Folder

        """
        folder_ent = Folder(*args, **kwargs)
        folder_ent = self._find_by_name_or_create(folder_ent)
        self.logger.info('{} Folder {} ({})'.format(self._update_str,
                                                    folder_ent.name,
                                                    folder_ent.id))
        return folder_ent

    def get_or_create_view(self, *args, **kwargs):
        """Gets an existing view schema by name and parent or
        creates a new one.

        Args:
            Same arguments as synapseclient.EntityViewSchema

        Returns:
            A synapseclient.EntityViewSchema.

        """
        view = EntityViewSchema(*args, **kwargs)
        view = self._find_by_name_or_create(view)
        return view

    def get_or_create_schema(self, *args, **kwargs):
        """Gets an existing table schema by name and parent or
        creates a new one.

        Args:
            Same arguments as synapseclient.Schema

        Returns:
            A synapseclient.Schema.

        """

        schema = Schema(*args, **kwargs)
        schema = self._find_by_name_or_create(schema)
        return schema

    def get_or_create_team(self, name: str, *args, **kwargs) -> Team:
        """Gets an existing team by name or creates a new one.

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

    def get_or_create_wiki(self, owner: str, *args, **kwargs) -> Wiki:
        """Gets an existing wiki or creates a new one. If
        parentWikiId is specified, a page will always be created.
        There are no restrictions on wiki titles on subwiki pages.
        Get doesn't work for subwiki pages

        Args:
            owner: Synapse Entity or its id that allows wikis
            Same arguments as synapseclient.Wiki

        Returns:
            Synapse wiki page

        """
        try:
            wiki_ent = Wiki(owner=owner, *args, **kwargs)
            wiki_ent = self.syn.store(wiki_ent,
                                      createOrUpdate=False)
        except SynapseHTTPError:
            if self.only_create:
                raise ValueError("only_create is set to True.")
            wiki_ent = self.syn.getWiki(owner=owner)
        self.logger.info('{} Wiki {}'.format(self._update_str,
                                             wiki_ent.title))
        return wiki_ent

    def get_or_create_queue(self, name: str, *args,
                            **kwargs) -> Evaluation:
        """Gets an existing evaluation queue by name or creates a new one.

        Args:
            name: Name of evaluation queue
            Same arguments as synapseclient.Evaluation

        Returns:
            A synapseclient.Evaluation

        """
        try:
            queue_ent = Evaluation(name=name, *args, **kwargs)
            queue = self.syn.store(queue_ent, createOrUpdate=False)
        except SynapseHTTPError:
            if self.only_create:
                raise ValueError("only_create is set to True.")
            url_name = quote(name)
            queue = self.syn.restGET(f"/evaluation/name/{url_name}")
            queue = Evaluation(**queue)
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
