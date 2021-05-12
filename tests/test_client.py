"""
Test client
"""
from unittest import mock
from unittest.mock import Mock, patch

import synapseclient
from synapseformation import client
from synapseformation.create import SynapseCreation


# def test_expand_config():
#     test_config = {
#         'TestRemove': "foo",
#         'name': 'Test Configuration',
#         'type': 'Project',
#         'children': [
#             {
#                 'name': 'Genes',
#                 'type': 'Folder',
#                 'children': [
#                     'testing',
#                     'foobar',
#                     'wow',
#                     {
#                         'name': "test",
#                         'type': "Folder"
#                     }
#                 ]
#             }
#         ]
#     }
#     expected_config = {
#         'name': 'Test Configuration',
#         'type': 'Project',
#         'children': [
#             {
#                 'name': 'Genes',
#                 'type': 'Folder',
#                 'children': [
#                     {
#                         'name': "testing",
#                         'type': "Folder"
#                     },
#                     {
#                         'name': "foobar",
#                         'type': "Folder"
#                     },
#                     {
#                         'name': "wow",
#                         'type': "Folder"
#                     },
#                     {
#                         'name': "test",
#                         'type': "Folder"
#                     }
#                 ]
#             }
#         ]
#     }
#     full_config = client.expand_config(test_config)
#     assert full_config == expected_config

class TestCreateSynapseResources():

    def setup_method(self):
        """Setting up for each method"""
        self.syn = mock.create_autospec(synapseclient.Synapse)
        self.create_cls = SynapseCreation(self.syn)
        self.config = {
            'name': 'Test Configuration',
            'type': 'Project',
            'children': [
                {
                    'name': 'Genes',
                    'type': 'Folder',
                    'children': [
                        {
                            'name': "testing",
                            'type': "Folder"
                        }
                    ]
                }
            ]
        }

    def test__create_synapse_resources_project(self):
        """Test project gets created"""
        project_config = {
            'name': 'Test Configuration',
            'type': 'Project'
        }
        expected_config = {
            'name': 'Test Configuration',
            'type': 'Project',
            'id': 'syn12222'
        }
        project_ent = synapseclient.Project(id="syn12222")
        with patch.object(self.create_cls, "get_or_create_project",
                          return_value=project_ent) as patch_create:
            client._create_synapse_resources(config=project_config,
                                             creation_cls=self.create_cls)
            patch_create.assert_called_once_with(name=project_config['name'])
            assert project_config == expected_config

    def test__create_synapse_resources_folder(self):
        """Test folders gets created"""
        folder_config = [
            {
                'name': 'Test 1',
                'type': 'Folder'
            },
            {
                'name': 'Test 2',
                'type': 'Folder'
            }
        ]
        expected_config = [
            {
                'name': 'Test 1',
                'type': 'Folder',
                'id': 'syn33333'
            },
            {
                'name': 'Test 2',
                'type': 'Folder',
                'id': 'syn22222'
            }
        ]
        folder_ent_1 = synapseclient.Folder(id="syn33333", parentId="syn5555")
        folder_ent_2 = synapseclient.Folder(id="syn22222", parentId="syn5555")
        call_1 = mock.call(name="Test 1", parentId="syn5555")
        call_2 = mock.call(name="Test 2", parentId="syn5555")
        with patch.object(self.create_cls, "get_or_create_folder",
                          side_effect=[folder_ent_1,
                                       folder_ent_2]) as patch_create:
            client._create_synapse_resources(config=folder_config,
                                             creation_cls=self.create_cls,
                                             parentid="syn5555")
            patch_create.assert_has_calls([call_1, call_2])
            assert folder_config == expected_config
