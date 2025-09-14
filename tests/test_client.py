import pytest
from unittest.mock import patch

from synapseformation.client import ensure_project, State, Project


@pytest.fixture
def state():
    return State()


@pytest.fixture
def project_id():
    return "12345"


@pytest.fixture
def project(project_id):
    return Project(id=project_id)
