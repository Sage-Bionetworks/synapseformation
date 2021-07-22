"""Test utility functions"""
import json
import tempfile
from unittest import mock
from unittest.mock import patch, Mock

import pytest
import synapseclient
from synapseclient.core.exceptions import (
    SynapseAuthenticationError,
    SynapseNoCredentialsError,
)

from synapseformation import utils


def test_read_config_yaml():
    """Test reading in yaml configuration"""
    test_yaml = "Test:\n  name: foo\n  test: bar"
    expected = {'Test': {'name': 'foo', 'test': 'bar'}}
    mock_open = mock.mock_open(read_data=test_yaml)
    with mock.patch("builtins.open", mock_open):
        yaml_dict = utils.read_config('file')
        assert yaml_dict == expected


def test_read_config_json():
    """Test JSON config can be read with yaml.safe_load"""
    expected = {'Test': {'name': 'foo', 'test': 'bar'}}
    mock_open = mock.mock_open(read_data=json.dumps(expected))
    with mock.patch("builtins.open", mock_open):
        json_dict = utils.read_config('file')
        assert json_dict == expected


def test_synapse_login_default():
    """Test default synapse login config path"""
    syn = Mock()
    with patch.object(synapseclient, "Synapse",
                      return_value=syn) as patch_synapse,\
         patch.object(syn, "login") as patch_login:
        syn_conn = utils.synapse_login()
        assert syn_conn == syn
        patch_synapse.assert_called_once_with(
            configPath=synapseclient.client.CONFIG_FILE
        )
        patch_login.assert_called_once()


def test_synapse_login_specify():
    """Test default synapse login config path"""
    syn = Mock()
    temp_config = tempfile.NamedTemporaryFile()
    with patch.object(synapseclient, "Synapse",
                      return_value=syn) as patch_synapse:
        syn_conn = utils.synapse_login(synapse_config=temp_config.name)
        assert syn_conn == syn
        patch_synapse.assert_called_once_with(
            configPath=temp_config.name
        )
    temp_config.close()


@pytest.mark.parametrize("error", [SynapseAuthenticationError,
                                   SynapseNoCredentialsError])
def test_synapse_login_error(error):
    """Test default synapse login config path"""
    syn = Mock()
    with patch.object(synapseclient, "Synapse", return_value=syn),\
         patch.object(syn, "login", side_effect=error),\
         pytest.raises(ValueError,
                       match=r"Login error: please make sure you .*"):
        utils.synapse_login()
