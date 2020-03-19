"""Convenience functions to create Synapse entities"""
import json
import logging
from logging import Logger
from urllib.parse import quote

from synapseclient import Project, Team, Evaluation, File, Folder, Wiki
from synapseclient import EntityViewSchema, Schema
from synapseclient.exceptions import SynapseHTTPError


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

    def _get_challenge(self, projectId) -> 'Challenge':
        """Gets the Challenge associated with a Project.

        See the definition of a Challenge object here:
        https://docs.synapse.org/rest/org/sagebionetworks/repo/model/Challenge.html

        Args:
            projectId: A Synapse Id of a Project.

        Returns:
            Challenge object
        """
        challenge = self.syn.restGET(f"/entity/{projectId}/challenge")
        return challenge

    def _create_challenge(self, projectId: str,
                          participantTeamId: str) -> 'Challenge':
        """Creates Challenge associated with a Project

        See the definition of a Challenge object here:
        https://docs.synapse.org/rest/org/sagebionetworks/repo/model/Challenge.html

        Args:
            participantTeamId: An Entity or Synapse ID of a Project.
            projectId: A Team or Team ID.

        Returns:
            Challenge object
        """
        challenge_object = {'participantTeamId': participantTeamId,
                            'projectId': projectId}
        challenge = self.syn.restPOST('/challenge',
                                      json.dumps(challenge_object))
        return challenge

    def get_or_create_challenge(self, projectId, *args, **kwargs) -> 'Challenge':
        """Gets an existing challenge by projectId or creates a new one.

        Args:
            projectId: Synapse project id
            participantTeamId: An Entity or Synapse ID of a Project.

        Returns:
            A Synapse challenge object
            https://docs.synapse.org/rest/org/sagebionetworks/repo/model/Challenge.html
        """
        try:
            challenge = self._create_challenge(projectId, *args, **kwargs)
        except SynapseHTTPError:
            if self.only_create:
                raise ValueError("only_create is set to True.")
            challenge = self._get_challenge(projectId)
        self.logger.info("{} Challenge ({})".format(self._update_str,
                                                    challenge['id']))
        return challenge
