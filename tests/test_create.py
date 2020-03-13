"""
Tests creation module
Functions are named with the function name in create module along
with what is tested
"""
import mock
from mock import patch
import uuid

import synapseclient

from synapseformation import create

SYN = mock.create_autospec(synapseclient.Synapse)


def test_create_project__call():
    """Tests the correct parameters are passed in"""
    project_name = str(uuid.uuid1())
    project = synapseclient.Project(name=project_name)
    returned = synapseclient.Project(name=project_name,
                                     id=str(uuid.uuid1()))
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        new_project = create.create_project(SYN, project_name)
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
        new_folder = create.create_folder(SYN, folder_name, parentid)
        assert new_folder == returned
        patch_syn_store.assert_called_once_with(folder)


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
        new_file = create.create_file(SYN, file_path, parentid)
        assert new_file == returned
        patch_syn_store.assert_called_once_with(file_ent)