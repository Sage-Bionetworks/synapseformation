"""
Test client
"""
from unittest import mock
from unittest.mock import patch

import synapseclient
from synapseformation import client, create
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

    def test__create_synapse_resources_acl(self):
        """Test ACL gets created"""
        project_config = {
            'name': 'Test Configuration',
            'type': 'Project',
            'acl': ['fake']
        }
        expected_config = {
            'name': 'Test Configuration',
            'type': 'Project',
            'id': 'syn12222',
            'acl': ['fake']
        }
        project_ent = synapseclient.Project(id="syn12222")
        with patch.object(self.create_cls, "get_or_create_project",
                          return_value=project_ent) as patch_create,\
             patch.object(create, "_set_acl") as patch_set:
            client._create_synapse_resources(config=project_config,
                                             creation_cls=self.create_cls)
            patch_create.assert_called_once_with(name=project_config['name'])
            assert project_config == expected_config
            patch_set.assert_called_once_with(
                syn=self.create_cls.syn, entity=project_ent,
                acl_config=['fake'])

    def test__create_synapse_resources_recursive(self):
        """Test recursive calls are made"""
        project_ent = synapseclient.Project(id="syn5555")
        folder_ent = synapseclient.Folder(id="syn33333", parentId="syn5555")
        call_1 = mock.call(name="Genes", parentId="syn5555")
        call_2 = mock.call(name="testing", parentId="syn33333")
        with patch.object(self.create_cls, "get_or_create_project",
                          return_value=project_ent) as patch_create_proj,\
             patch.object(self.create_cls, "get_or_create_folder",
                          return_value=folder_ent) as patch_create_folder:
            client._create_synapse_resources(config=self.config,
                                             creation_cls=self.create_cls)
            patch_create_proj.assert_called_once_with(
                name="Test Configuration"
            )
            patch_create_folder.assert_has_calls([call_1, call_2])

    def test__create_synapse_resources_team(self):
        """Test team gets created"""
        team_config = {
            'name': 'Test Configuration',
            'type': 'Team',
            'can_public_join': False,
            'description': 'Test team description'
        }
        expected_config = {
            'name': 'Test Configuration',
            'type': 'Team',
            'can_public_join': False,
            'description': 'Test team description',
            'id': '11111'
        }
        team_ent = synapseclient.Team(id="11111")
        with patch.object(self.create_cls, "get_or_create_team",
                          return_value=team_ent) as patch_create:
            client._create_synapse_resources(config=team_config,
                                             creation_cls=self.create_cls)
            patch_create.assert_called_once_with(
                name=team_config['name'], description=team_config['description'],
                canPublicJoin=team_config['can_public_join']
            )
            assert team_config == expected_config

    def test__create_synapse_resources_team_invite(self):
        """Test team members are invited"""
        team_config = {
            'name': 'Test Configuration',
            'type': 'Team',
            'can_public_join': False,
            'description': 'Test team description',
            'invitations': [
                {
                    'message': 'Welcome to the Test Team! ',
                    'members': [
                        {"principal_id": 3426116},
                        {"email": "synapseformation-test-user@sagebase.org"}
                    ]
                }
            ]
        }

        expected_config = {
            'name': 'Test Configuration',
            'type': 'Team',
            'can_public_join': False,
            'description': 'Test team description',
            'id': '11111',
            'invitations': [
                {
                    'message': 'Welcome to the Test Team! ',
                    'members': [
                        {"principal_id": 3426116},
                        {"email": "synapseformation-test-user@sagebase.org"}
                    ]
                }
            ]
        }
        team_ent = synapseclient.Team(id="11111")
        with patch.object(self.create_cls, "get_or_create_team",
                          return_value=team_ent) as patch_create,\
             patch.object(self.create_cls.syn,
                          "invite_to_team") as patch_invite:
            client._create_synapse_resources(config=team_config,
                                             creation_cls=self.create_cls)
            patch_invite.assert_called()