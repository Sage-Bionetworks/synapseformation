"""
Tests creation module
Functions are named with the function name in create module along
with what is tested
"""
import uuid

import mock
from mock import patch
import pytest
import synapseclient

from synapseformation.create import SynapseCreation

SYN = mock.create_autospec(synapseclient.Synapse)
CREATE_CLS = SynapseCreation(SYN)

def test_create_project__call():
    """Tests the correct parameters are passed in"""
    project_name = str(uuid.uuid1())
    project = synapseclient.Project(name=project_name)
    returned = synapseclient.Project(name=project_name,
                                     id=str(uuid.uuid1()))
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        new_project = CREATE_CLS.create_project(project_name)
        assert new_project == returned
        patch_syn_store.assert_called_once_with(project,
                                                createOrUpdate=False)


def test_create_folder__call():
    """Tests the correct parameters are passed in"""
    folder_name = str(uuid.uuid1())
    parentid = str(uuid.uuid1())
    folder = synapseclient.Folder(name=folder_name,
                                  parentId=parentid)
    returned = synapseclient.Folder(name=folder_name,
                                    id=str(uuid.uuid1()),
                                    parentId=parentid)
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        new_folder = CREATE_CLS.create_folder(folder_name, parentid)
        assert new_folder == returned
        patch_syn_store.assert_called_once_with(folder,
                                                createOrUpdate=False)


def test_create_file__call():
    """Tests the correct parameters are passed in"""
    file_path = str(uuid.uuid1())
    parentid = str(uuid.uuid1())
    file_ent = synapseclient.File(path=file_path,
                                  parentId=parentid)
    returned = synapseclient.File(path=file_path,
                                  id=str(uuid.uuid1()),
                                  parentId=parentid)
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        new_file = CREATE_CLS.create_file(file_path, parentid)
        assert new_file == returned
        patch_syn_store.assert_called_once_with(file_ent,
                                                createOrUpdate=False)


def test__create_team__call():
    """Tests the correct parameters are passed in"""
    team_name = str(uuid.uuid1())
    description = str(uuid.uuid1())
    can_public_join = True
    team_ent = synapseclient.Team(name=team_name,
                                  description=description,
                                  canPublicJoin=can_public_join)
    returned = synapseclient.Team(name=team_name,
                                  description=description,
                                  id=str(uuid.uuid1()),
                                  canPublicJoin=can_public_join)
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        new_team = CREATE_CLS.create_team(team_name, description=description,
                                          can_public_join=can_public_join)
        assert new_team == returned
        patch_syn_store.assert_called_once_with(team_ent)


def test__create_team__raise_error():
    """Error is raised when team name already exists"""
    team_name = str(uuid.uuid1())
    with patch.object(SYN, "store", side_effect=ValueError),\
         pytest.raises(ValueError, match=f"Team {team_name}*"):
        CREATE_CLS.create_team(team_name)

def test_create_team__call():
    """Tests the correct parameters are passed in"""
    team_name = str(uuid.uuid1())
    description = str(uuid.uuid1())
    can_public_join = True
    returned = synapseclient.Team(name=team_name,
                                  description=description,
                                  id=str(uuid.uuid1()),
                                  canPublicJoin=can_public_join)
    with patch.object(CREATE_CLS, "_create_team",
                      return_value=returned) as patch_create:
        new_team = CREATE_CLS.create_team(team_name, description=description,
                                          can_public_join=can_public_join)
        patch_create.assert_called_once_with(team_name,
                                             description=description,
                                             can_public_join=can_public_join)
        assert new_team == returned
