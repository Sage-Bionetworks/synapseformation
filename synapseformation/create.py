"""Convenience functions to create Synapse entities"""
import json
import logging
from logging import Logger
from urllib.parse import quote

from synapseclient import (Project, Team, Evaluation, File, Folder, Wiki,
                           EntityViewSchema, Schema)
try:
    from synapseclient.core.exceptions import SynapseHTTPError
except ModuleNotFoundError:
    from synapseclient.exceptions import SynapseHTTPError


class SynapseCreation:
    """Creates Synapse Features"""
    def __init__(self, syn: 'Synapse', only_create: bool = True,
                 logger: Logger = None):
        """
        Args:
            syn: Synapse connection
            only_create: Only create entities. Default is True, which
                         means creation will fail if resource already exists.
        """
        self.syn = syn
        self.only_create = only_create
        self.logger = logger or logging.getLogger(__name__)
        self._update_str = "Fetched existing" if only_create else "Created"

    def _get_obj(self, obj: 'Object') -> 'Object':
        """Gets the object from Synapse based on object constructor

        Args:
            obj: synapseclient Object

        Returns:
            obj: synapseclient Object

        """
        if isinstance(obj, (Project, File, Folder, EntityViewSchema, Schema)):
            obj = self.syn.get(obj, downloadFile=False)
        elif isinstance(obj, Team):
            obj = self.syn.getTeam(obj)
        elif isinstance(obj, Wiki):
            obj = self.syn.getWiki(obj)
        elif isinstance(obj, Evaluation):
            obj = self.syn.getEvaluation(obj)
        else:
            raise ValueError(f"{obj} not recognized")
        return obj

    def _find_by_obj_or_create(self, obj: 'Object') -> 'Object':
        """Gets an existing synapse object or create a new one.

        Args:
            obj: synapseclient Object

        Returns:
            A synapseclient Object
        """
        try:
            obj = self.syn.store(obj, createOrUpdate=False)
        except SynapseHTTPError as err:
            # Must check for 409 error
            if err.response.status_code != 409:
                raise err
            if self.only_create:
                raise ValueError(f"{str(err)}. To use existing entities, "
                                 "set only_create to False.")
            obj = self._get_obj(obj)
        return obj

    def get_or_create_project(self, **kwargs) -> Project:
        """Gets an existing project by name or creates a new one.

        Args:
            Same arguments as synapseclient.Project

        Returns:
            A synapseclient.Project

        """
        project = Project(**kwargs)
        project = self._find_by_obj_or_create(project)
        self.logger.info('{} Project {}({})'.format(self._update_str,
                                                    project.name,
                                                    project.id))
        return project

    def get_or_create_file(self, **kwargs) -> File:
        """Gets an existing file by name and parent or
        creates a new one.

        Args:
            Same arguments as synapseclient.File

        Returns:
            A synapseclient.File

        """
        file_ent = File(**kwargs)
        file_ent = self._find_by_obj_or_create(file_ent)
        self.logger.info('{} File {} ({})'.format(self._update_str,
                                                  file_ent.name,
                                                  file_ent.id))
        return file_ent

    def get_or_create_folder(self, **kwargs) -> Folder:
        """Gets an existing folder by name and parent or
        creates a new one.

        Args:
            Same arguments as synapseclient.Folder

        Returns:
            A synapseclient.Folder

        """
        folder_ent = Folder(**kwargs)
        folder_ent = self._find_by_obj_or_create(folder_ent)
        self.logger.info('{} Folder {} ({})'.format(self._update_str,
                                                    folder_ent.name,
                                                    folder_ent.id))
        return folder_ent

    def get_or_create_view(self, **kwargs):
        """Gets an existing view schema by name and parent or
        creates a new one.

        Args:
            Same arguments as synapseclient.EntityViewSchema

        Returns:
            A synapseclient.EntityViewSchema.

        """
        view = EntityViewSchema(**kwargs)
        view = self._find_by_obj_or_create(view)
        self.logger.info('{} View {} ({})'.format(self._update_str,
                                                  view.name,
                                                  view.id))
        return view

    def get_or_create_schema(self, **kwargs):
        """Gets an existing table schema by name and parent or
        creates a new one.

        Args:
            Same arguments as synapseclient.Schema

        Returns:
            A synapseclient.Schema.

        """

        schema = Schema(**kwargs)
        schema = self._find_by_obj_or_create(schema)
        self.logger.info('{} Schema {} ({})'.format(self._update_str,
                                                    schema.name,
                                                    schema.id))
        return schema

    def get_or_create_team(self, **kwargs) -> Team:
        """Gets an existing team by name or creates a new one.

        Args:
            Same arguments as synapseclient.Team

        Returns:
            A synapseclient.Team

        """

        team = Team(**kwargs)
        team = self._find_by_obj_or_create(team)
        self.logger.info('{} Team {} ({})'.format(self._update_str,
                                                  team.name,
                                                  team.id))
        return team

    def get_or_create_wiki(self, **kwargs) -> Wiki:
        """Gets an existing wiki or creates a new one. If
        parentWikiId is specified, a page will always be created.
        There are no restrictions on wiki titles on subwiki pages.
        Get doesn't work for subwiki pages

        Args:
            Same arguments as synapseclient.Wiki

        Returns:
            Synapse wiki page

        """

        wiki = Wiki(**kwargs)
        wiki = self._find_by_obj_or_create(wiki)
        self.logger.info('{} Wiki {}'.format(self._update_str,
                                             wiki.title))
        return wiki

    def get_or_create_queue(self, **kwargs) -> Evaluation:
        """Gets an existing evaluation queue by name or creates a new one.

        Args:
            Same arguments as synapseclient.Evaluation

        Returns:
            A synapseclient.Evaluation

        """
        queue = Evaluation(**kwargs)
        queue = self._find_by_obj_or_create(queue)
        self.logger.info('{} Queue {}({})'.format(self._update_str,
                                                  queue.name, queue.id))
        return queue

    def _get_challenge(self, projectId: str) -> dict:
        """Gets the Challenge associated with a Project.

        See the definition of a Challenge object here:
        https://docs.synapse.org/rest/org/sagebionetworks/repo/model/Challenge.html

        Args:
            projectId: A Synapse Id of a Project.

        Returns:
            A Synapse challenge dict
            https://docs.synapse.org/rest/org/sagebionetworks/repo/model/Challenge.html

        """
        challenge = self.syn.restGET(f"/entity/{projectId}/challenge")
        return challenge

    def _create_challenge(self, projectId: str,
                          participantTeamId: str) -> dict:
        """Creates Challenge associated with a Project

        See the definition of a Challenge object here:
        https://docs.synapse.org/rest/org/sagebionetworks/repo/model/Challenge.html

        Args:
            participantTeamId: An Entity or Synapse ID of a Project.
            projectId: A Team or Team ID.

        Returns:
            A Synapse challenge dict
            https://docs.synapse.org/rest/org/sagebionetworks/repo/model/Challenge.html

        """
        challenge_object = {'participantTeamId': participantTeamId,
                            'projectId': projectId}
        challenge = self.syn.restPOST('/challenge',
                                      json.dumps(challenge_object))
        return challenge

    def get_or_create_challenge(self, **kwargs) -> dict:
        """Gets an existing challenge by projectId or creates a new one.
        # TODO: Use eventually implemented challenge class

        Args:
            projectId: Synapse project id
            participantTeamId: An Entity or Synapse ID of a Project.

        Returns:
            A Synapse challenge dict
            https://docs.synapse.org/rest/org/sagebionetworks/repo/model/Challenge.html
        """
        try:
            challenge = self._create_challenge(**kwargs)
        except SynapseHTTPError as err:
            # Must check for 409 error
            if err.response.status_code != 409:
                raise err
            if self.only_create:
                raise ValueError(f"{str(err)}. To use existing entities, "
                                 "set only_create to False.")
            challenge = self._get_challenge(kwargs['projectId'])
        self.logger.info("{} Challenge ({})".format(self._update_str,
                                                    challenge['id']))
        return challenge
