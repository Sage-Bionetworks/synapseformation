"""Test utility functions"""

import json
from unittest import mock

from synapseformation import utils


def test_read_config_yaml():
    """Test reading in yaml configuration"""
    test_yaml = "Test:\n  name: foo\n  test: bar"
    expected = {"Test": {"name": "foo", "test": "bar"}}
    mock_open = mock.mock_open(read_data=test_yaml)
    with mock.patch("builtins.open", mock_open):
        yaml_dict = utils.read_config("file")
        assert yaml_dict == expected


def test_read_config_json():
    """Test JSON config can be read with yaml.safe_load"""
    expected = {"Test": {"name": "foo", "test": "bar"}}
    mock_open = mock.mock_open(read_data=json.dumps(expected))
    with mock.patch("builtins.open", mock_open):
        json_dict = utils.read_config("file")
        assert json_dict == expected
