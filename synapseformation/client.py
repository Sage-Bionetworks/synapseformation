"""Synapse Formation client"""
import json
from pathlib import Path
import yaml
from collections import defaultdict, deque

import synapseclient
from synapseclient import Synapse
from synapseclient.models import Project, Folder, Team


class State:
    """Saves the synapseformation state per configuration file"""

    def __init__(self, path=".synapseformation/state.json"):
        self.path = Path(path)
        self.resources = []
        if self.path.exists():
            with open(self.path, "r") as f:
                data = json.load(f)
                self.resources = data.get("resources", [])
        else:
            self.resources = []

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "resources": self.resources}
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def get_id(self, logical_name: str, resource_type: str) -> str:
        """Get the Synapse resource ID for a given logical name and resource type.

        Args:
            logical_name (str): _description_
            resource_type (str): _description_

        Returns:
            str: _description_
        """
        for r in self.resources:
            if r["name"] == logical_name and r["type"] == resource_type:
                return r["id"]
        return None

    def add(self, resource_type, logical_name, resource_id, properties=None):
        self.resources.append(
            {
                "type": resource_type,
                "name": logical_name,
                "id": resource_id,
                "properties": properties or {},
            }
        )
        self.save()

    def update_properties(self, logical_name, resource_type, properties):
        for r in self.resources:
            if r["name"] == logical_name and r["type"] == resource_type:
                r["properties"] = properties
                break
        self.save()


def apply_acl(acl: dict, state: State) -> str:
    """_summary_

    Args:
        acl (dict): _description_
        state (State): _description_

    Returns:
        _type_: _description_
    """
    acl_applied = state.get_id(acl["resource"], "acl")
    if acl_applied:
        return acl_applied
    # Resolve resource
    res_ref = acl["resource"].split(".")  # e.g. "folder.raw_data"
    res_type, logical_name = res_ref[0], res_ref[1]
    res_id = state.get_id(logical_name, res_type)
    for grant in acl["grants"]:
        principal_ref = grant["principal"].split(".")  # e.g. "team.data_scientists"
        principal_id = state.get_id(principal_ref[1], principal_ref[0])
        access_type = grant["access_type"]
        if res_type == "project":
            res = Project(id=res_id).get()
        elif res_type == "folder":
            res = Folder(id=res_id).get()
        res.set_permissions(principal_id=principal_id, access_type=access_type)
    state.add("acl", acl["resource"], res_id, acl["grants"])
    return res_id


def ensure_project(logical_name: str, props: dict, state: State) -> Project:
    """Create or get project from state file

    Args:
        logical_name (str): _description_
        props (dict): _description_
        state (State): _description_

    Returns:
        _type_: _description_
    """
    project_id = state.get_id(logical_name, "project")
    if project_id:
        return Project(id=project_id).get()
    else:
        project = Project(name=props["name"]).store()
        state.add("project", logical_name, project.id, props)
        return project


def ensure_folder(logical_name: str, props: dict, state: State) -> Folder:
    """
    Ensures that a folder with the given logical name and properties exists in Synapse under the given project.

    If the folder does not exist, it is created with the given properties.  If it does exist, the existing folder is returned.

    Args:
        logical_name: The logical name of the folder
        props: The properties of the folder
        state: The state object to store the created folder

    Returns:
        The created or existing Synapse folder
    """
    folder_id = state.get_id(logical_name, "folder")
    if folder_id:
        return Folder(id=folder_id).get()
    else:
        parent_id = state.get_id(
            props["parent"].split(".")[1], props["parent"].split(".")[0]
        )
        folder = Folder(name=props["name"], parent_id=parent_id).store()
        state.add("folder", logical_name, folder.id, props)
        return folder


def ensure_team(logical_name: str, props: dict, state: State) -> Team:
    """_summary_

    Args:
        logical_name (str): _description_
        props (dict): _description_
        state (State): _description_

    Returns:
        _type_: _description_
    """
    team_id = state.get_id(logical_name, "team")
    if team_id:
        return Team(id=team_id).get()
    else:
        team = Team(name=props["name"]).create()
        state.add("team", logical_name, team.id, props)
        return team


def sort_folders(folders: dict) -> list:
    """
    Perform a topological sort of folders based on parent references.
    Returns a list of folder logical names in the correct creation order.
    """
    # Build adjacency + in-degree
    graph = defaultdict(list)
    in_degree = {name: 0 for name in folders.keys()}

    for name, props in folders.items():
        parent_ref = props["parent"]
        parent_type, parent_name = parent_ref.split(".")
        if parent_type == "folder":
            graph[parent_name].append(name)
            in_degree[name] += 1

    # Topological sort (Kahn's algorithm)
    queue = deque([name for name, deg in in_degree.items() if deg == 0])
    order = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for child in graph[node]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(order) != len(folders):
        raise ValueError("Cycle detected in folder hierarchy!")

    return order


def initialize():
    """initialize .synapseformation directory with state.json for one project"""
    pass


def plan():
    """reads yaml template and diffs the desired vs actual state"""
    pass


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def apply_config(config_path):
    """Executes API calls to reconcile drift.
    Updates the state.json file with the new resource IDs and metadata.
    """
    config = load_config(config_path)
    my_agent = "synapseformation/0.0.0"
    syn = Synapse(user_agent=my_agent)
    syn.login()
    state = State()

    # 1. Teams
    for logical_name, props in config.get("teams", {}).items():
        team = ensure_team(logical_name, props, state)

    # 2. Projects (and nested folders)
    for logical_name, props in config.get("projects", {}).items():
        project = ensure_project(logical_name, props, state)

    folder_order = sort_folders(config.get("folders", {}))
    for logical_name in folder_order:
        props = config["folders"][logical_name]
        ensure_folder(logical_name, props, state)

    # 3. Access Controls
    for acl in config.get("access_controls", []):
        apply_acl(acl, state)


def export():
    """Reads Synapse resources and dumps them into YAML."""
    pass


def destroy():
    """Deletes Synapse resources created by synapseformation."""
    pass
