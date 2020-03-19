"""
Tests creation module
Functions are named with the function name in create module along
with what is tested
"""
import json
import uuid

from challengeutils import utils
import mock
from mock import patch
import pytest
import synapseclient
from synapseclient.exceptions import SynapseHTTPError

from synapseformation.create import SynapseCreation

SYN = mock.create_autospec(synapseclient.Synapse)
CREATE_CLS = SynapseCreation(SYN)
GET_CLS = SynapseCreation(SYN, only_create=False)
# remove this later
UPDATE_CLS = SynapseCreation(SYN, only_create=False)


def test__find_by_name_or_create__create():
    """Tests creation"""
    entity = synapseclient.Entity(name=str(uuid.uuid1()))
    returned = synapseclient.Entity(name=str(uuid.uuid1()))
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        created_ent = CREATE_CLS._find_by_name_or_create(entity)
        patch_syn_store.assert_called_once_with(entity,
                                                createOrUpdate=False)
        assert created_ent == returned


def test__find_by_name_or_create__onlycreate_raise():
    """Tests only create flag raises error when entity exists"""
    entity = synapseclient.Entity(name=str(uuid.uuid1()))
    returned = synapseclient.Entity(name=str(uuid.uuid1()))
    with patch.object(SYN, "store", side_effect=SynapseHTTPError),\
         pytest.raises(ValueError, match="only_create is set to True."):
        CREATE_CLS._find_by_name_or_create(entity)


def test__find_by_name_or_create__get():
    """Tests only create flag raises error when entity exists"""
    concretetype = str(uuid.uuid1())
    entity = synapseclient.Entity(name=str(uuid.uuid1()),
                                  parentId=str(uuid.uuid1()),
                                  concreteType=concretetype)
    restpost = synapseclient.Entity(name=str(uuid.uuid1()),
                                    id=str(uuid.uuid1()),
                                    parentId=str(uuid.uuid1()))
    returned = synapseclient.Entity(name=str(uuid.uuid1()),
                                    id=str(uuid.uuid1()),
                                    parentId=str(uuid.uuid1()),
                                    concreteType=concretetype)
    body = json.dumps({"parentId": entity.properties.get("parentId", None),
                       "entityName": entity.name})
    with patch.object(SYN, "store", side_effect=SynapseHTTPError),\
         patch.object(SYN, "restPOST",
                      return_value=restpost) as patch_rest_post,\
         patch.object(SYN, "get", return_value=returned) as patch_rest_get:
        get_ent = GET_CLS._find_by_name_or_create(entity)
        assert get_ent == returned
        patch_rest_post.assert_called_once_with("/entity/child", body=body)
        patch_rest_get.assert_called_once_with(restpost.id, downloadFile=False)


def test_get_or_create_project__call():
    """Makes sure correct parameters are called"""
    project_name = str(uuid.uuid1())
    project = synapseclient.Project(name=project_name)
    returned = synapseclient.Project(name=project_name,
                                     id=str(uuid.uuid1()))
    with patch.object(CREATE_CLS,
                      "_find_by_name_or_create",
                      return_value=returned) as patch_find_or_create:
        new_project = CREATE_CLS.get_or_create_project(name=project_name)
        assert new_project == returned
        patch_find_or_create.assert_called_once_with(project)


def test_get_or_create_team__create():
    """Tests creation of team"""
    team_name = str(uuid.uuid1())
    description = str(uuid.uuid1())
    public_join = True
    team_ent = synapseclient.Team(name=team_name,
                                  description=description,
                                  canPublicJoin=public_join)
    returned = synapseclient.Team(name=team_name,
                                  description=description,
                                  id=str(uuid.uuid1()),
                                  canPublicJoin=public_join)
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        new_team = CREATE_CLS.get_or_create_team(team_name,
                                                 description=description,
                                                 canPublicJoin=public_join)
        assert new_team == returned
        patch_syn_store.assert_called_once_with(team_ent,
                                                createOrUpdate=False)


def test_get_or_create_team__get():
    """Tests getting of team"""
    team_name = str(uuid.uuid1())
    description = str(uuid.uuid1())
    public_join = False
    returned = synapseclient.Team(name=team_name,
                                  description=description,
                                  id=str(uuid.uuid1()),
                                  canPublicJoin=public_join)
    with patch.object(SYN, "store", side_effect=SynapseHTTPError),\
         patch.object(SYN, "getTeam",
                      return_value=returned) as patch_get_team:
        new_team = UPDATE_CLS.get_or_create_team(team_name,
                                                 description=description,
                                                 canPublicJoin=public_join)
        patch_get_team.assert_called_once_with(team_name)
        assert new_team == returned


def test_get_or_create_team__get_raise():
    """Tests trying to get a team when only_create"""
    team_name = str(uuid.uuid1())
    with patch.object(SYN, "store", side_effect=SynapseHTTPError),\
         pytest.raises(ValueError, match="only_create is set to True."):
        CREATE_CLS.get_or_create_team(team_name)


def test_get_or_create_folder__call():
    """Makes sure correct parameters are called"""
    folder_name = str(uuid.uuid1())
    parentid = str(uuid.uuid1())
    folder = synapseclient.Folder(name=folder_name,
                                  parentId=parentid)
    returned = synapseclient.Folder(name=folder_name,
                                    id=str(uuid.uuid1()),
                                    parentId=parentid)
    with patch.object(CREATE_CLS,
                      "_find_by_name_or_create",
                      return_value=returned) as patch_find_or_create:
        new_folder = CREATE_CLS.get_or_create_folder(folder_name,
                                                     parentId=parentid)
        assert new_folder == returned
        patch_find_or_create.assert_called_once_with(folder)


def test_get_or_create_file__call():
    """Makes sure correct parameters are called"""
    file_path = str(uuid.uuid1())
    parentid = str(uuid.uuid1())
    file_ent = synapseclient.File(path=file_path,
                                  parentId=parentid)
    returned = synapseclient.File(path=file_path,
                                  id=str(uuid.uuid1()),
                                  parentId=parentid)
    with patch.object(CREATE_CLS,
                      "_find_by_name_or_create",
                      return_value=returned) as patch_find_or_create:
        new_file = CREATE_CLS.get_or_create_file(file_path,
                                                 parentId=parentid)
        assert new_file == returned
        patch_find_or_create.assert_called_once_with(file_ent)


def test_get_or_create_view__call():
    """Makes sure correct parameters are called"""
    view_name = str(uuid.uuid1())
    parentid = str(uuid.uuid1())
    view_ent = synapseclient.EntityViewSchema(view_name,
                                              parentId=parentid)
    returned = synapseclient.EntityViewSchema(view_name,
                                              id=str(uuid.uuid1()),
                                              parentId=parentid)
    with patch.object(CREATE_CLS,
                      "_find_by_name_or_create",
                      return_value=returned) as patch_find_or_create:
        new_view = CREATE_CLS.get_or_create_view(view_name,
                                                 parentId=parentid)
        assert new_view == returned
        patch_find_or_create.assert_called_once_with(view_ent)


def test_get_or_create_schema__call():
    """Makes sure correct parameters are called"""
    schema_name = str(uuid.uuid1())
    parentid = str(uuid.uuid1())
    schema_ent = synapseclient.Schema(schema_name,
                                      parentId=parentid)
    returned = synapseclient.Schema(schema_name,
                                    id=str(uuid.uuid1()),
                                    parentId=parentid)
    with patch.object(CREATE_CLS,
                      "_find_by_name_or_create",
                      return_value=returned) as patch_find_or_create:
        new_schema = CREATE_CLS.get_or_create_schema(schema_name,
                                                     parentId=parentid)
        assert new_schema == returned
        patch_find_or_create.assert_called_once_with(schema_ent)


def test_get_or_create_wiki__create():
    """Tests creation of wiki"""
    wiki_title = str(uuid.uuid1())
    markdown = str(uuid.uuid1())
    owner = str(uuid.uuid1())
    wiki_ent = synapseclient.Wiki(title=wiki_title,
                                  markdown=markdown,
                                  owner=owner)
    returned = synapseclient.Wiki(title=wiki_title,
                                  markdown=markdown,
                                  id=str(uuid.uuid1()),
                                  owner=owner)
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        new_wiki = CREATE_CLS.get_or_create_wiki(owner=owner,
                                                 title=wiki_title,
                                                 markdown=markdown)
        assert new_wiki == returned
        patch_syn_store.assert_called_once_with(wiki_ent,
                                                createOrUpdate=False)


def test_get_or_create_wiki__get():
    """Tests getting of wiki"""
    wiki_title = str(uuid.uuid1())
    markdown = str(uuid.uuid1())
    owner = str(uuid.uuid1())
    returned = synapseclient.Wiki(title=wiki_title,
                                  markdown=markdown,
                                  id=str(uuid.uuid1()),
                                  owner=owner)
    with patch.object(SYN, "store", side_effect=SynapseHTTPError),\
         patch.object(SYN, "getWiki",
                      return_value=returned) as patch_get_wiki:
        new_wiki = UPDATE_CLS.get_or_create_wiki(owner=owner,
                                                 title=wiki_title,
                                                 markdown=markdown)
        patch_get_wiki.assert_called_once_with(owner=owner)
        assert new_wiki == returned


def test_get_or_create_wiki__get_raise():
    """Tests trying to get a wiki when only_create"""
    owner = str(uuid.uuid1())
    with patch.object(SYN, "store", side_effect=SynapseHTTPError),\
         pytest.raises(ValueError, match="only_create is set to True."):
        CREATE_CLS.get_or_create_wiki(owner)


def test_get_or_create_queue__create():
    """Tests creation of queue"""
    queue_name = str(uuid.uuid1())
    parentid = "syn" + str(uuid.uuid1())
    description = str(uuid.uuid1())
    queue = synapseclient.Evaluation(name=queue_name,
                                     contentSource=parentid,
                                     description=description,
                                     quota={})
    returned = synapseclient.Evaluation(name=queue_name,
                                        contentSource=parentid,
                                        id=str(uuid.uuid1()),
                                        description=description,
                                        quota={})
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        new_queue = CREATE_CLS.get_or_create_queue(name=queue_name,
                                                   contentSource=parentid,
                                                   description=description,
                                                   quota={})
        assert new_queue == returned
        patch_syn_store.assert_called_once_with(queue,
                                                createOrUpdate=False)


def test_get_or_create_queue__get():
    """Tests getting of queue"""
    queue_name = str(uuid.uuid1())
    parentid = "syn" + str(uuid.uuid1())
    description = str(uuid.uuid1())
    evalid = str(uuid.uuid1())
    # Rest get return json
    queue_json = {"name": queue_name,
                  "contentSource": parentid,
                  "id": evalid,
                  "description": description,
                  "quota": {}}
    returned = synapseclient.Evaluation(**queue_json)
    with patch.object(SYN, "store", side_effect=SynapseHTTPError),\
         patch.object(SYN, "restGET",
                      return_value=queue_json) as patch_rest_get:
        new_queue = UPDATE_CLS.get_or_create_queue(name=queue_name,
                                                   contentSource=parentid,
                                                   description=description,
                                                   quota={})
        patch_rest_get.assert_called_once_with(f"/evaluation/name/{queue_name}")
        assert new_queue == returned


def test_get_or_create_queue__get_raise():
    """Tests trying to get a queue when only_create"""
    queue_name = str(uuid.uuid1())
    parentid = "syn" + str(uuid.uuid1())
    with patch.object(SYN, "store", side_effect=SynapseHTTPError),\
         pytest.raises(ValueError, match="only_create is set to True."):
        CREATE_CLS.get_or_create_queue(name=queue_name,
                                       contentSource=parentid)
