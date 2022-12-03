"""
Tests creation module
Functions are named with the function name in create module along
with what is tested
"""
import json
from unittest import mock
from unittest.mock import Mock, patch
import uuid

import pytest
import synapseclient
from synapseclient.core.exceptions import SynapseHTTPError

from synapseformation import create
from synapseformation.create import SynapseCreation

SYN = mock.create_autospec(synapseclient.Synapse)
CREATE_CLS = SynapseCreation(SYN)
GET_CLS = SynapseCreation(SYN, only_get=True)


def test__find_by_obj_or_create__create():
    """Tests creation"""
    entity = synapseclient.Entity(name=str(uuid.uuid1()))
    returned = synapseclient.Entity(name=str(uuid.uuid1()))
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        created_ent = CREATE_CLS._find_by_obj_or_create(entity)
        patch_syn_store.assert_called_once_with(entity,
                                                createOrUpdate=False)
        assert created_ent == returned


#@patch.object(SYN, "store")
def test__find_by_obj_or_create__onlycreate_raise():
    """Tests only create flag raises error when entity exists"""
    entity = synapseclient.Entity(name=str(uuid.uuid1()))
    returned = synapseclient.Entity(name=str(uuid.uuid1()))
    # Mock SynapseHTTPError with 409 response
    mocked_409 = SynapseHTTPError("foo", response=Mock(status_code=409))
    with patch.object(SYN, "store",
                      side_effect=mocked_409) as patch_syn_store,\
         pytest.raises(ValueError, match="foo. To use existing entities, "
                                         "set only_get to True."):
        CREATE_CLS._find_by_obj_or_create(entity)
        patch_syn_store.assert_called_once_with(entity, createOrUpdate=False)


def test__find_by_obj_or_create__wrongcode_raise():
    """Tests correct error is raised when not 409 code"""
    entity = synapseclient.Entity(name=str(uuid.uuid1()))
    returned = synapseclient.Entity(name=str(uuid.uuid1()))
    # Mock SynapseHTTPError with 404 response
    mocked_404 = SynapseHTTPError("Not Found", response=Mock(status_code=404))
    with patch.object(SYN, "store",
                      side_effect=mocked_404) as patch_syn_store,\
         pytest.raises(SynapseHTTPError, match="Not Found"):
        CREATE_CLS._find_by_obj_or_create(entity)
        patch_syn_store.assert_called_once_with(entity, createOrUpdate=False)


def test__find_by_obj_or_create__get():
    """Tests getting of entity"""
    concretetype = str(uuid.uuid1())
    entity = synapseclient.Entity(name=str(uuid.uuid1()),
                                  parentId=str(uuid.uuid1()),
                                  concreteType=concretetype)
    returned = synapseclient.Entity(name=str(uuid.uuid1()),
                                    id=str(uuid.uuid1()),
                                    parentId=str(uuid.uuid1()),
                                    concreteType=concretetype)
    mocked_409 = SynapseHTTPError("foo", response=Mock(status_code=409))

    with patch.object(SYN, "store",
                      side_effect=mocked_409) as patch_syn_store,\
         patch.object(GET_CLS, "_get_obj",
                      return_value=returned) as patch_cls_get:
        get_ent = GET_CLS._find_by_obj_or_create(entity)
        assert get_ent == returned
        patch_syn_store.assert_called_once()
        patch_cls_get.assert_called_once_with(entity)


def test__find_entity_by_name__valid():
    """Test getting entities by name"""
    post_return = {'id': "syn11111"}
    obj = synapseclient.File(path="foo.txt", parentId="syn12345",
                             id="syn11111")
    with patch.object(SYN, "findEntityId",
                      return_value=post_return) as patch_find,\
         patch.object(SYN, "get", return_value=obj) as patch_get:
        return_obj = GET_CLS._find_entity_by_name(
            parentid="syn12345",
            entity_name="foo.txt",
            concrete_type=obj.properties.concreteType
        )
        assert obj == return_obj
        patch_find.assert_called_once_with("foo.txt", parent="syn12345")
        patch_get.assert_called_once_with("syn11111", downloadFile=False)


def test__find_entity_by_name__invalid():
    """Test getting entities by name"""
    post_return = {'id': "syn11111"}
    obj = synapseclient.File(path="foo.txt", parentId="syn12345",
                             id="syn11111")
    with patch.object(SYN, "findEntityId", return_value=post_return),\
         patch.object(SYN, "get", return_value=obj),\
         pytest.raises(AssertionError,
                       match="Retrieved .* had type .* rather than .*"):
        GET_CLS._find_entity_by_name(
            parentid="syn12345",
            entity_name="foo.txt",
            concrete_type="Test"
        )


@pytest.mark.parametrize(
    "obj", [synapseclient.Project(name="foo"),
            synapseclient.File(path="foo.txt", parentId="syn12345"),
            synapseclient.Folder(name="foo", parentId="syn12345"),
            synapseclient.Schema(name="foo", parentId="syn12345")]
)
def test__get_obj__entity(obj):
    """Test getting of entities"""
    with patch.object(GET_CLS, "_find_entity_by_name",
                      return_value=obj) as patch_get:
        return_obj = GET_CLS._get_obj(obj)
        patch_get.assert_called_once_with(
            parentid=obj.properties.get("parentId", None),
            entity_name=obj.name,
            concrete_type=obj.properties.concreteType)
        assert obj == return_obj


@pytest.mark.parametrize("obj,get_func",
                         [(synapseclient.Team(name="foo"), "getTeam"),
                          (synapseclient.Wiki(owner="foo"), "getWiki"),
                          (synapseclient.Evaluation(name="foo",
                                                    contentSource="syn123"),
                           "getEvaluationByName")])
def test__get_obj__nonentity(obj, get_func):
    """Test getting of entities"""
    with patch.object(SYN, get_func, return_value=obj) as patch_get:
        return_obj = GET_CLS._get_obj(obj)
        if isinstance(obj, (synapseclient.Team, synapseclient.Evaluation)):
            patch_get.assert_called_once_with(obj.name)
        elif isinstance(obj, synapseclient.Wiki):
            patch_get.assert_called_once_with(obj.ownerId)
        assert return_obj == obj


def test_get_or_create_project__call():
    """Makes sure correct parameters are called"""
    project_name = str(uuid.uuid1())
    project = synapseclient.Project(name=project_name)
    returned = synapseclient.Project(name=project_name,
                                     id=str(uuid.uuid1()))
    with patch.object(CREATE_CLS,
                      "_find_by_obj_or_create",
                      return_value=returned) as patch_find_or_create:
        new_project = CREATE_CLS.get_or_create_project(name=project_name)
        assert new_project == returned
        patch_find_or_create.assert_called_once_with(project)


def test_get_or_create_team__call():
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
    with patch.object(CREATE_CLS,
                      "_find_by_obj_or_create",
                      return_value=returned) as patch_find_or_create:
        new_team = CREATE_CLS.get_or_create_team(name=team_name,
                                                 description=description,
                                                 canPublicJoin=public_join)
        assert new_team == returned
        patch_find_or_create.assert_called_once_with(team_ent)


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
                      "_find_by_obj_or_create",
                      return_value=returned) as patch_find_or_create:
        new_folder = CREATE_CLS.get_or_create_folder(name=folder_name,
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
                      "_find_by_obj_or_create",
                      return_value=returned) as patch_find_or_create:
        new_file = CREATE_CLS.get_or_create_file(path=file_path,
                                                 parentId=parentid)
        assert new_file == returned
        patch_find_or_create.assert_called_once_with(file_ent)


def test_get_or_create_view__call():
    """Makes sure correct parameters are called"""
    view_name = str(uuid.uuid1())
    parentid = str(uuid.uuid1())
    view_ent = synapseclient.EntityViewSchema(name=view_name,
                                              parentId=parentid)
    returned = synapseclient.EntityViewSchema(name=view_name,
                                              id=str(uuid.uuid1()),
                                              parentId=parentid)
    with patch.object(CREATE_CLS,
                      "_find_by_obj_or_create",
                      return_value=returned) as patch_find_or_create:
        new_view = CREATE_CLS.get_or_create_view(name=view_name,
                                                 parentId=parentid)
        assert new_view == returned
        patch_find_or_create.assert_called_once_with(view_ent)


def test_get_or_create_schema__call():
    """Makes sure correct parameters are called"""
    schema_name = str(uuid.uuid1())
    parentid = str(uuid.uuid1())
    schema_ent = synapseclient.Schema(name=schema_name,
                                      parentId=parentid)
    returned = synapseclient.Schema(name=schema_name,
                                    id=str(uuid.uuid1()),
                                    parentId=parentid)
    with patch.object(CREATE_CLS,
                      "_find_by_obj_or_create",
                      return_value=returned) as patch_find_or_create:
        new_schema = CREATE_CLS.get_or_create_schema(name=schema_name,
                                                     parentId=parentid)
        assert new_schema == returned
        patch_find_or_create.assert_called_once_with(schema_ent)


def test_get_or_create_wiki__call():
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
    with patch.object(CREATE_CLS,
                      "_find_by_obj_or_create",
                      return_value=returned) as patch_find_or_create:
        new_wiki = CREATE_CLS.get_or_create_wiki(owner=owner,
                                                 title=wiki_title,
                                                 markdown=markdown)
        assert new_wiki == returned
        patch_find_or_create.assert_called_once_with(wiki_ent)


def test_get_or_create_queue__call():
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
    with patch.object(CREATE_CLS,
                      "_find_by_obj_or_create",
                      return_value=returned) as patch_find_or_create:
        new_queue = CREATE_CLS.get_or_create_queue(name=queue_name,
                                                   contentSource=parentid,
                                                   description=description,
                                                   quota={})
        assert new_queue == returned
        patch_find_or_create.assert_called_once_with(queue)


def test__get_challenge__call():
    """Tests the correct parameters are passed in"""
    projectid = str(uuid.uuid1())
    chalid = str(uuid.uuid1())
    etag = str(uuid.uuid1())
    participant_teamid = str(uuid.uuid1())
    rest_return = {'id': chalid,
                   'projectId': projectid,
                   'etag': etag,
                   'participantTeamId': participant_teamid}
    with patch.object(SYN, "restGET",
                      return_value=rest_return) as patch_rest_get:
        chal = CREATE_CLS._get_challenge(projectid)
        patch_rest_get.assert_called_once_with(f"/entity/{projectid}/challenge")
        assert chal == rest_return


def test__create_challenge__call():
    """Tests the correct parameters are passed in"""
    projectid = str(uuid.uuid1())
    chalid = str(uuid.uuid1())
    etag = str(uuid.uuid1())
    teamid = str(uuid.uuid1())
    rest_return = {'id': chalid,
                   'projectId': projectid,
                   'etag': etag,
                   'participantTeamId': teamid}
    input_dict = {'participantTeamId': teamid,
                  'projectId': projectid}
    with patch.object(SYN, "restPOST",
                      return_value=rest_return) as patch_rest_post:
        chal = CREATE_CLS._create_challenge(participantTeamId=teamid,
                                            projectId=projectid)
        patch_rest_post.assert_called_once_with('/challenge',
                                                json.dumps(input_dict))
        assert chal == rest_return


def test_get_or_create_challenge__create():
    """Tests creation of challenge"""
    projectid = str(uuid.uuid1())
    teamid = str(uuid.uuid1())
    returned = {'id': str(uuid.uuid1())}
    with patch.object(CREATE_CLS, "_create_challenge",
                      return_value=returned) as patch_create:
        new_chal = CREATE_CLS.get_or_create_challenge(participantTeamId=teamid,
                                                      projectId=projectid)
        assert new_chal == returned
        patch_create.assert_called_once_with(projectId=projectid,
                                             participantTeamId=teamid)


def test_get_or_create_challenge__get():
    """Tests getting of challenge"""
    projectid = str(uuid.uuid1())
    teamid = str(uuid.uuid1())
    returned = {'id': str(uuid.uuid1())}
    mocked_400 = SynapseHTTPError("foo", response=Mock(status_code=400))
    with patch.object(GET_CLS, "_create_challenge",
                      side_effect=mocked_400),\
         patch.object(GET_CLS, "_get_challenge",
                      return_value=returned) as patch_get:
        new_chal = GET_CLS.get_or_create_challenge(participantTeamId=teamid,
                                                   projectId=projectid)
        patch_get.assert_called_once_with(projectid)
        assert new_chal == returned


def test_get_or_create_challenge__get_raise():
    """Tests trying to get a queue when only_get"""
    projectid = str(uuid.uuid1())
    teamid = str(uuid.uuid1())
    mocked_400 = SynapseHTTPError("foo", response=Mock(status_code=400))
    with patch.object(CREATE_CLS, "_create_challenge",
                      side_effect=mocked_400),\
         pytest.raises(ValueError, match="foo. To use existing entities, "
                                         "set only_get to True."):
        CREATE_CLS.get_or_create_challenge(participantTeamId=teamid,
                                           projectId=projectid)


def test_get_or_create_challenge__get_raise_404():
    """Tests trying to get a queue raise 404"""
    projectid = str(uuid.uuid1())
    teamid = str(uuid.uuid1())
    mocked_404 = SynapseHTTPError("Not Found", response=Mock(status_code=404))
    with patch.object(CREATE_CLS, "_create_challenge",
                      side_effect=mocked_404),\
         pytest.raises(SynapseHTTPError, match="Not Found"):
        CREATE_CLS.get_or_create_challenge(participantTeamId=teamid,
                                           projectId=projectid)


def test_get_or_create_challenge__get_raise_missing_param():
    """Tests that a missing parameter will raise an error"""
    teamid = str(uuid.uuid1())
    with pytest.raises(TypeError,
                       match=".*missing 1 required positional argument: "
                             "'projectId'"):
        CREATE_CLS.get_or_create_challenge(participantTeamId=teamid)


def test__set_acl():
    syn = Mock()
    entity = Mock()
    acl_config = [
        {"principal_id": "1111111",
         "access_type": ["READ", "DOWNLOAD"]},
        {"principal_id": "2222222",
         "access_type": ["READ", "DOWNLOAD", "UPDATE"]}
    ]
    expected_calls = [
        mock.call(entity=entity, principalId="1111111",
                  accessType=["READ", "DOWNLOAD"]),
        mock.call(entity=entity, principalId="2222222",
                  accessType=["READ", "DOWNLOAD", "UPDATE"])
    ]
    with patch.object(syn, "setPermissions") as patch_set:
        create._set_acl(syn=syn, entity=entity,
                        acl_config=acl_config)
        patch_set.assert_has_calls(expected_calls)
