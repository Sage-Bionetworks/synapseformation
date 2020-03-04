"""
Tests creation module
Functions are named with the function name in create module along
with what is tested
"""
from mock import patch
import uuid

import synapseclient

from synapseformation import create

SYN = mock.create_autospec(synapseclient.Synapse)


def test_create_project__call():
    """Tests the correct parameters are passed in"""
    project = str(uuid.uuid1())
    returned = str(uuid.uuid2())
    with patch.object(SYN, "store", return_value=returned) as patch_syn_store:
        project = create.create_project(SYN, project)
        assert project == returned
        patch_syn_store.assert_called_once_with(project)
