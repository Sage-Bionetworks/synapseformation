import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
from collections import defaultdict

from synapseformation.client import (
    State,
    apply_project,
    apply_folder,
    apply_team,
    apply_acl,
    sort_folders,
    get_resources,
    plan_config,
    apply_config,
    destroy_resources,
    initialize,
    export,
    sync_drift,
)
from synapseclient.models import Project, Folder, Team
from synapseclient import Synapse


class TestState:
    """Test cases for the State class"""

    def test_state_init_new_file(self):
        """Test State initialization with non-existent file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            assert state.resources == []
            assert state.path == state_path

    def test_state_init_existing_file(self):
        """Test State initialization with existing file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            test_data = {
                "resources": [{"type": "project", "name": "test", "id": "123"}]
            }
            with open(state_path, "w") as f:
                json.dump(test_data, f)

            state = State(path=str(state_path))
            assert len(state.resources) == 1
            assert state.resources[0]["name"] == "test"

    def test_state_save(self):
        """Test saving state to file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "subdir" / "state.json"
            state = State(path=str(state_path))
            state.resources = [{"type": "project", "name": "test", "id": "123"}]

            state.save()

            assert state_path.exists()
            with open(state_path, "r") as f:
                data = json.load(f)
                assert data["version"] == 1
                assert len(data["resources"]) == 1

    def test_state_get_id_found(self):
        """Test getting ID for existing resource"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            state.resources = [
                {"type": "project", "name": "test_project", "id": "syn123"}
            ]

            result = state.get_id("test_project", "project")
            assert result == "syn123"

    def test_state_get_id_not_found(self):
        """Test getting ID for non-existent resource"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            state.resources = []

            result = state.get_id("nonexistent", "project")
            assert result is None

    @patch.object(State, "save")
    def test_state_add(self, mock_save):
        """Test adding a resource to state"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))

            state.add("project", "test_project", "syn123", {"name": "Test Project"})

            assert len(state.resources) == 1
            resource = state.resources[0]
            assert resource["type"] == "project"
            assert resource["name"] == "test_project"
            assert resource["id"] == "syn123"
            assert resource["properties"] == {"name": "Test Project"}
            mock_save.assert_called_once()

    @patch.object(State, "save")
    def test_state_add_no_properties(self, mock_save):
        """Test adding a resource without properties"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))

            state.add("project", "test_project", "syn123")

            assert state.resources[0]["properties"] == {}
            mock_save.assert_called_once()

    @patch.object(State, "save")
    def test_state_update_properties(self, mock_save):
        """Test updating properties of existing resource"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            state.resources = [
                {
                    "type": "project",
                    "name": "test",
                    "id": "syn123",
                    "properties": {"old": "value"},
                }
            ]

            state.update_properties("test", "project", {"new": "value"})

            assert state.resources[0]["properties"] == {"new": "value"}
            mock_save.assert_called_once()

    @patch.object(State, "save")
    def test_state_clear(self, mock_save):
        """Test clearing all resources"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            state.resources = [{"type": "project", "name": "test", "id": "syn123"}]

            state.clear()

            assert state.resources == []
            mock_save.assert_called_once()


class TestApplyFunctions:
    """Test cases for apply_* functions"""

    @patch("synapseformation.client.Project")
    def test_apply_project_new(self, mock_project_class):
        """Test applying a new project"""
        mock_project_instance = Mock()
        mock_project_instance.id = "syn123"
        mock_project_instance.store.return_value = mock_project_instance
        mock_project_class.return_value = mock_project_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            props = {"name": "Test Project"}

            result = apply_project("test_project", props, state)

            assert result == mock_project_instance
            mock_project_class.assert_called_with(name="Test Project")
            mock_project_instance.store.assert_called_once()
            assert len(state.resources) == 1

    @patch("synapseformation.client.Project")
    def test_apply_project_existing(self, mock_project_class):
        """Test applying an existing project"""
        mock_project_instance = Mock()
        mock_project_instance.get.return_value = mock_project_instance
        mock_project_class.return_value = mock_project_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            state.resources = [
                {"type": "project", "name": "test_project", "id": "syn123"}
            ]
            props = {"name": "Test Project"}

            result = apply_project("test_project", props, state)

            assert result == mock_project_instance
            mock_project_class.assert_called_with(id="syn123")
            mock_project_instance.get.assert_called_once()

    @patch("synapseformation.client.Folder")
    def test_apply_folder_new(self, mock_folder_class):
        """Test applying a new folder"""
        mock_folder_instance = Mock()
        mock_folder_instance.id = "syn456"
        mock_folder_instance.store.return_value = mock_folder_instance
        mock_folder_class.return_value = mock_folder_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            state.resources = [
                {"type": "project", "name": "parent_project", "id": "syn123"}
            ]
            props = {"name": "Test Folder", "parent": "project.parent_project"}

            result = apply_folder("test_folder", props, state)

            assert result == mock_folder_instance
            mock_folder_class.assert_called_with(name="Test Folder", parent_id="syn123")
            mock_folder_instance.store.assert_called_once()

    @patch("synapseformation.client.Folder")
    def test_apply_folder_existing(self, mock_folder_class):
        """Test applying an existing folder"""
        mock_folder_instance = Mock()
        mock_folder_instance.get.return_value = mock_folder_instance
        mock_folder_class.return_value = mock_folder_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            state.resources = [
                {"type": "folder", "name": "test_folder", "id": "syn456"}
            ]
            props = {"name": "Test Folder", "parent": "project.parent_project"}

            result = apply_folder("test_folder", props, state)

            assert result == mock_folder_instance
            mock_folder_class.assert_called_with(id="syn456")
            mock_folder_instance.get.assert_called_once()

    @patch("synapseformation.client.Team")
    def test_apply_team_new(self, mock_team_class):
        """Test applying a new team"""
        mock_team_instance = Mock()
        mock_team_instance.id = "789"
        mock_team_instance.create.return_value = mock_team_instance
        mock_team_class.return_value = mock_team_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            props = {"name": "Test Team"}

            result = apply_team("test_team", props, state)

            assert result == mock_team_instance
            mock_team_class.assert_called_with(name="Test Team")
            mock_team_instance.create.assert_called_once()

    @patch("synapseformation.client.Team")
    def test_apply_team_existing(self, mock_team_class):
        """Test applying an existing team"""
        mock_team_instance = Mock()
        mock_team_instance.get.return_value = mock_team_instance
        mock_team_class.return_value = mock_team_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            state.resources = [{"type": "team", "name": "test_team", "id": "789"}]
            props = {"name": "Test Team"}

            result = apply_team("test_team", props, state)

            assert result == mock_team_instance
            mock_team_class.assert_called_with(id="789")
            mock_team_instance.get.assert_called_once()

    @patch("synapseformation.client.Folder")
    def test_apply_acl_new(self, mock_folder_class):
        """Test applying ACL to a resource"""
        mock_folder_instance = Mock()
        mock_folder_class.return_value.get.return_value = mock_folder_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            state.resources = [
                {"type": "folder", "name": "test_folder", "id": "syn456"},
                {"type": "team", "name": "test_team", "id": "789"},
            ]

            acl = {
                "name": "test_acl",
                "properties": {
                    "resource": "folder.test_folder",
                    "grants": [
                        {
                            "principal": "team.test_team",
                            "access_type": ["READ", "DOWNLOAD"],
                        }
                    ],
                },
            }

            result = apply_acl(acl, state)

            assert result == "syn456"
            mock_folder_instance.set_permissions.assert_called_once_with(
                principal_id="789", access_type=["READ", "DOWNLOAD"]
            )

    @patch("synapseformation.client.Project")
    def test_apply_acl_existing(self, mock_project_class):
        """Test applying ACL that already exists"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = State(path=str(state_path))
            state.resources = [{"type": "acl", "name": "test_acl", "id": "syn456"}]

            acl = {"name": "test_acl", "properties": {}}

            result = apply_acl(acl, state)

            assert result == "syn456"
            mock_project_class.assert_not_called()


class TestUtilityFunctions:
    """Test cases for utility functions"""

    def test_sort_folders_simple(self):
        """Test sorting folders with simple hierarchy"""
        folders = [
            {"name": "child", "properties": {"parent": "folder.parent"}},
            {"name": "parent", "properties": {"parent": "project.root"}},
        ]

        result = sort_folders(folders)

        assert result == ["parent", "child"]

    def test_sort_folders_complex(self):
        """Test sorting folders with complex hierarchy"""
        folders = [
            {"name": "grandchild", "properties": {"parent": "folder.child"}},
            {"name": "child", "properties": {"parent": "folder.parent"}},
            {"name": "parent", "properties": {"parent": "project.root"}},
            {"name": "sibling", "properties": {"parent": "folder.parent"}},
        ]

        result = sort_folders(folders)

        assert result[0] == "parent"
        assert "child" in result
        assert "sibling" in result
        assert result.index("grandchild") > result.index("child")

    def test_sort_folders_cycle_detection(self):
        """Test cycle detection in folder hierarchy"""
        folders = [
            {"name": "folder1", "properties": {"parent": "folder.folder2"}},
            {"name": "folder2", "properties": {"parent": "folder.folder1"}},
        ]

        with pytest.raises(ValueError, match="Cycle detected"):
            sort_folders(folders)

    def test_get_resources(self):
        """Test getting resources organized by type"""
        config = {
            "project1": {"type": "project", "properties": {"name": "Project 1"}},
            "folder1": {"type": "folder", "properties": {"name": "Folder 1"}},
            "project2": {"type": "project", "properties": {"name": "Project 2"}},
        }

        result = get_resources(config)

        assert len(result["project"]) == 2
        assert len(result["folder"]) == 1
        assert result["project"][0]["name"] == "project1"
        assert result["project"][0]["properties"]["name"] == "Project 1"


class TestPlanConfig:
    """Test cases for plan_config function"""

    @patch("synapseformation.client.State")
    @patch("synapseformation.client.Team")
    @patch("synapseformation.client.Project")
    @patch("synapseformation.client.Folder")
    def test_plan_config_new_resources(
        self, mock_folder, mock_project, mock_team, mock_state_class
    ):
        """Test planning config with new resources"""
        mock_state = Mock()
        mock_state.resources = []
        mock_state.get_id.return_value = None
        mock_state_class.return_value = mock_state

        syn = Mock()
        config = {
            "resources": {
                "project1": {"type": "project", "properties": {"name": "Project 1"}}
            }
        }

        result = plan_config(config, syn)

        assert len(result["changes"]) == 1
        assert result["changes"][0]["action"] == "create"
        assert result["changes"][0]["type"] == "project"
        assert result["changes"][0]["name"] == "project1"

    @patch("synapseformation.client.State")
    @patch("synapseformation.client.Project")
    def test_plan_config_deleted_resources(self, mock_project_class, mock_state_class):
        """Test planning config with deleted resources"""
        mock_project_instance = Mock()
        mock_project_instance.name = "Deleted Project"
        mock_project_class.return_value.get.return_value = mock_project_instance

        mock_state = Mock()
        mock_state.resources = [
            {
                "type": "project",
                "name": "deleted_project",
                "id": "syn123",
                "properties": {"name": "Deleted Project"},
            }
        ]
        mock_state_class.return_value = mock_state

        syn = Mock()
        config = {"resources": {}}

        result = plan_config(config, syn)

        assert len(result["changes"]) == 1
        assert result["changes"][0]["action"] == "delete"
        assert result["changes"][0]["name"] == "deleted_project"

    @patch("synapseformation.client.State")
    @patch("synapseformation.client.Team")
    def test_plan_config_drift_detection(self, mock_team_class, mock_state_class):
        """Test drift detection in plan_config"""
        mock_team_instance = Mock()
        mock_team_instance.name = "Different Name"
        mock_team_class.return_value.get.return_value = mock_team_instance

        mock_state = Mock()
        mock_state.resources = [
            {
                "type": "team",
                "name": "test_team",
                "id": "789",
                "properties": {"name": "Original Name"},
            }
        ]
        mock_state.get_id.return_value = None
        mock_state_class.return_value = mock_state

        syn = Mock()
        config = {"resources": {}}

        result = plan_config(config, syn)

        assert len(result["drift"]) == 1
        assert result["drift"][0]["type"] == "team"
        assert result["drift"][0]["synapse_properties"]["name"] == "Different Name"


class TestApplyConfig:
    """Test cases for apply_config function"""

    @patch("synapseformation.client.apply_team")
    @patch("synapseformation.client.apply_project")
    @patch("synapseformation.client.apply_folder")
    @patch("synapseformation.client.apply_acl")
    @patch("synapseformation.client.sort_folders")
    @patch("synapseformation.client.State")
    def test_apply_config(
        self,
        mock_state_class,
        mock_sort_folders,
        mock_apply_acl,
        mock_apply_folder,
        mock_apply_project,
        mock_apply_team,
    ):
        """Test applying configuration"""
        mock_state = Mock()
        mock_state_class.return_value = mock_state
        mock_sort_folders.return_value = ["folder1"]

        config = {
            "resources": {
                "team1": {"type": "team", "properties": {"name": "Team 1"}},
                "project1": {"type": "project", "properties": {"name": "Project 1"}},
                "folder1": {"type": "folder", "properties": {"name": "Folder 1"}},
                "acl1": {"type": "acl", "properties": {"resource": "project.project1"}},
            }
        }

        apply_config(config)

        mock_apply_team.assert_called_once()
        mock_apply_project.assert_called_once()
        mock_apply_folder.assert_called_once()
        mock_apply_acl.assert_called_once()


class TestDestroyResources:
    """Test cases for destroy_resources function"""

    @patch("synapseformation.client.State")
    @patch("synapseformation.client.Project")
    @patch("synapseformation.client.Team")
    def test_destroy_resources(
        self, mock_team_class, mock_project_class, mock_state_class
    ):
        """Test destroying resources"""
        mock_state = Mock()
        mock_state.resources = [
            {"type": "project", "id": "syn123", "properties": {}},
            {"type": "team", "id": "789", "properties": {}},
            {
                "type": "acl",
                "id": "syn456",
                "properties": {"grants": [{"principal": "789"}]},
            },
        ]
        mock_state_class.return_value = mock_state

        mock_project_instance = Mock()
        mock_team_instance = Mock()
        mock_project_class.return_value = mock_project_instance
        mock_team_class.return_value = mock_team_instance

        syn = Mock()

        destroy_resources(syn)

        syn.setPermissions.assert_called_once()
        mock_project_instance.delete.assert_called_once()
        mock_team_instance.delete.assert_called_once()
        mock_state.clear.assert_called_once()


class TestStubFunctions:
    """Test cases for stub functions that need implementation"""

    def test_initialize(self):
        """Test initialize function (stub)"""
        # This should pass without error since it's currently a stub
        result = initialize()
        assert result is None

    def test_export(self):
        """Test export function (stub)"""
        # This should pass without error since it's currently a stub
        result = export()
        assert result is None

    def test_sync_drift(self):
        """Test sync_drift function (stub)"""
        # This should pass without error since it's currently a stub
        result = sync_drift()
        assert result is None


# Test fixtures
@pytest.fixture
def state():
    return State()


@pytest.fixture
def project_id():
    return "12345"


@pytest.fixture
def project(project_id):
    return Project(id=project_id)
