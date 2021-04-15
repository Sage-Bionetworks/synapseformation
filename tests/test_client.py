from io import StringIO

from synapseformation import client
import yaml


def test_expand_config():
    test_config = {
        'TestRemove': "foo",
        'name': 'Test Configuration',
        'type': 'Project',
        'children': [
            {
                'name': 'Genes',
                'type': 'Folder',
                'children': [
                    'testing',
                    'foobar',
                    'wow',
                    {
                        'name': "test",
                        'type': "Folder"
                    }
                ]
            }
        ]
    }
    expected_config = {
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
                    },
                    {
                        'name': "foobar",
                        'type': "Folder"
                    },
                    {
                        'name': "wow",
                        'type': "Folder"
                    },
                    {
                        'name': "test",
                        'type': "Folder"
                    }
                ]
            }
        ]
    }
    full_config = client.expand_config(test_config)
    assert full_config == expected_config
