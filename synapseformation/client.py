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
    acl_applied = state.get_id(acl["name"], "acl")
    if acl_applied:
        return acl_applied
    properties = acl["properties"]

    # Resolve resource
    res_ref = properties["resource"].split(".")  # e.g. "folder.raw_data"
    res_type, logical_name = res_ref[0], res_ref[1]
    res_id = state.get_id(logical_name, res_type)
    for grant in properties["grants"]:
        principal_ref = grant["principal"].split(".")  # e.g. "team.data_scientists"
        principal_id = state.get_id(principal_ref[1], principal_ref[0])
        access_type = grant["access_type"]
        if res_type == "project":
            res = Project(id=res_id).get()
        elif res_type == "folder":
            res = Folder(id=res_id).get()
        res.set_permissions(principal_id=principal_id, access_type=access_type)
    state.add("acl", acl["name"], res_id, properties["grants"])
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


def sort_folders(folders: list[dict]) -> list:
    """
    Perform a topological sort of folders based on parent references.
    Returns a list of folder logical names in the correct creation order.
    """
    # Build adjacency + in-degree
    graph = defaultdict(list)
    in_degree = {folder["name"]: 0 for folder in folders}

    for folder in folders:
        name = folder["name"]
        properties = folder["properties"]
        parent_ref = properties["parent"]
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


def plan(config_path):
    """Reads the configuration file and compares it to the state file to determine what changes need to be made to reconcile any drift.

    Returns:
        dict: A dictionary containing the changes that need to be made to reconcile any drift.
            The keys are the resource types and the values are lists of dictionaries containing the changes for each resource.
            Each dictionary in the list has the following keys:
                - logical_name: The logical name of the resource.
                - action: The action to take for the resource (create, update, delete).
                - properties: The properties for the resource.
    """
    # Read the configuration file
    config = load_config(config_path)

    # Read the state file
    state = State()

    # Get the resources from the state file
    state_resources = state.resources

    # Create a dictionary to store the changes that need to be made to reconcile any drift
    changes = defaultdict(list)

    # Loop through the configuration file and compare it to the state file to determine what changes need to be made
    for logical_name, config_resource in config["resources"].items():
        # changes[config_resource['type']] = []
        # for resource in resources:
        #     logical_name = resource["logical_name"]
        print(logical_name)
        resource_id = state.get_id(logical_name, config_resource["type"])
        print(resource_id)
        # if resource_type == "project":
        #     # Get the project from the state file
        #     project = Project(id=state.get_id(logical_name, resource_type)).get()
        #     # Compare the properties of the project in the configuration file to the properties in the state file
        #     if project.properties != resource["properties"]:
        #         # Add the project to the list of changes for the project resource type
        #         changes[resource_type].append({
        #             "logical_name": logical_name,
        #             "action": "update",
        #             "properties": resource["properties"],
        #         })
        # elif resource_type == "team":
        #     # Get the team from the state file
        #     team = Team(id=state.get_id(logical_name, resource_type)).get()
        #     # Compare the properties of the team in the configuration file to the properties in the state file
        #     if team.properties != resource["properties"]:
        #         # Add the team to the list of changes for the team resource type
        #         changes[resource_type].append({
        #             "logical_name": logical_name,
        #             "action": "update",
        #             "properties": resource["properties"],
        #         })
        # elif resource_type == "folder":
        #     # Get the folder from the state file
        #     folder = Folder(id=state.get_id(logical_name, resource_type)).get()
        #     # Compare the properties of the folder in the configuration file to the properties in the state file
        #     if folder.properties != resource["properties"]:
        #         # Add the folder to the list of changes for the folder resource type
        #         changes[resource_type].append({
        #             "logical_name": logical_name,
        #             "action": "update",
        #             "properties": resource["properties"],
        #         })
        # elif resource_type == "acl":
        #     # Get the ACL from the state file
        #     acl = ACL(id=state.get_id(logical_name, resource_type)).get()
        #     # Compare the grants in the ACL in the configuration file to the grants in the state file
        #     if acl.grants != resource["grants"]:
        #         # Add the ACL to the list of changes for the ACL resource type
        #         changes[resource_type].append({
        #             "logical_name": logical_name,
        #             "action": "update",
        #             "grants": resource["grants"],
        #         })

    # Loop through the resources in the state file and compare them to the configuration file to determine if any need to be deleted
    # for resource in resources:
    #     resource_type = resource["resource_type"]
    #     logical_name = resource["logical_name"]
    #     if resource_type not in config:
    #         # Add the resource to the list of changes for the resource type
    #         changes[resource_type].append({
    #             "logical_name": logical_name,
    #             "action": "delete",
    #         })

    return changes


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def get_resources(resource_config: dict) -> dict:
    """
    Given a configuration dictionary, returns a dictionary of resources organized by resource type and logical name.

    Args:
        config (dict): A configuration dictionary

    Returns:
        dict: A dictionary of resources organized by resource type and logical name
    """
    resources = defaultdict(list)
    for name, res_dict in resource_config.items():
        resources[res_dict["type"]].append(
            {"name": name, "properties": res_dict["properties"]}
        )
    return resources


def apply_config(config_path):
    """Executes API calls to reconcile drift.
    Updates the state.json file with the new resource IDs and metadata.
    """
    config = load_config(config_path)
    my_agent = "synapseformation/0.0.0"
    syn = Synapse(user_agent=my_agent)
    syn.login()
    state = State()
    resources = get_resources(resource_config=config["resources"])

    # 1. Teams
    for team in resources.get("team", []):
        ensure_team(logical_name=team["name"], props=team["properties"], state=state)

    # 2. Projects
    for project in resources.get("project", []):
        ensure_project(
            logical_name=project["name"], props=project["properties"], state=state
        )

    # 3. Folders (topologically sorted). Projects must be created first, then the ordering of
    # folders being stored matters, so get the correct ordering of folders.
    folder_order = sort_folders(resources.get("folder", []))
    for folder_logical_name in folder_order:
        props = config["resources"][folder_logical_name]["properties"]
        ensure_folder(logical_name=folder_logical_name, props=props, state=state)

    # 4. Access Controls have to come last since they depend on other resources
    for acl in resources.get("access_control", []):
        apply_acl(acl=acl, state=state)


def export():
    """Reads Synapse resources and dumps them into YAML."""
    pass


def destroy():
    """Deletes Synapse resources created by synapseformation."""
    pass
