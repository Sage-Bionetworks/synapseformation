"""Synapse Formation client"""
import json
from pathlib import Path
from collections import defaultdict, deque

from synapseclient import Synapse
from synapseclient.models import Project, Folder, Team
from synapseclient.operations import get


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
        """Retrieve the Synapse resource ID for a given logical name and resource type.

        Args:
            logical_name (str): The logical name of the resource as defined in the configuration.
            resource_type (str): The type of the resource (e.g., 'project', 'folder', 'team', 'acl').

        Returns:
            str: The Synapse ID of the resource if found, otherwise None.
        """
        for r in self.resources:
            if r["name"] == logical_name and r["type"] == resource_type:
                return r["id"]
        return None

    def add(
        self,
        resource_type: str,
        logical_name: str,
        resource_id: str,
        properties: dict = None,
    ):
        """
        Adds a new resource to the internal resources list and saves the updated list.

        Args:
            resource_type (str): The type of the resource (e.g., 'database', 'storage').
            logical_name (str): A unique logical name to identify the resource.
            resource_id (str): The unique identifier of the resource.
            properties (dict, optional): Additional properties for the resource. Defaults to an empty dictionary if not provided.
        """
        self.resources.append(
            {
                "type": resource_type,
                "name": logical_name,
                "id": resource_id,
                "properties": properties or {},
            }
        )
        self.save()

    def update_properties(
        self, logical_name: str, resource_type: str, properties: dict = None
    ):
        """
        Updates the properties of a resource identified by logical name and resource type.

        Args:
            logical_name (str): The logical name of the resource as defined in the configuration.
            resource_type (str): The type of the resource (e.g., 'project', 'folder', 'team', 'acl').
            properties (dict, optional): The new properties to set for the resource. Defaults to None.
        """
        for r in self.resources:
            if r["name"] == logical_name and r["type"] == resource_type:
                r["properties"] = properties
                break
        self.save()

    def clear(self) -> str:
        """Clear the state"""
        self.resources = []
        self.save()


def apply_acl(acl: dict, state: State) -> str:
    """
    Applies an access control list (ACL) to a specified resource and updates the state accordingly.

    Args:
        acl (dict): A dictionary representing the ACL to apply. Must contain a "name" and "properties" with "resource" and "grants".
        state (State): The current state object used to resolve resource and principal IDs, and to track applied ACLs.

    Raises:
        KeyError: If required keys are missing in the ACL or state.
        AttributeError: If the resource type is unsupported or missing required methods.

    Returns:
        str: The ID of the resource to which the ACL was applied.
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
        # grant["principal"] = principal_id
    state.add("acl", acl["name"], res_id, properties)
    return res_id


def apply_project(logical_name: str, props: dict, state: State) -> Project:
    """
    Ensures that a project with the given logical name and properties exists in Synapse.

    If the project does not exist, it is created with the given properties. If it does exist, the existing project is returned.

    Args:
        logical_name (str): The logical name of the project.
        props (dict): The properties of the project.
        state (State): The state object to store the created project.

    Returns:
        Project: The created or existing Synapse project.
    """
    project_id = state.get_id(logical_name, "project")
    if project_id:
        return Project(id=project_id).get()
    else:
        project = Project(name=props["name"]).store()
        state.add("project", logical_name, project.id, props)
        return project


def apply_folder(logical_name: str, props: dict, state: State) -> Folder:
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
        if props.get("jsonschema_uri") is not None:
            folder.bind_schema(
                json_schema_uri=props.get("jsonschema_uri"),
                enable_derived_annotations=True,
            )
        state.add("folder", logical_name, folder.id, props)
        return folder


def apply_team(logical_name: str, props: dict, state: State) -> Team:
    """
    Creates or retrieves a Team object based on the provided logical name.

    If a team with the given logical name exists in the state, retrieves and returns the corresponding Team object.
    Otherwise, creates a new Team using the provided properties, adds it to the state, and returns the new Team object.

    Args:
        logical_name (str): The logical identifier for the team.
        props (dict): Properties used to create the team (must include 'name').
        state (State): The state object used to track created teams and their IDs.

    Returns:
        Team: The retrieved or newly created Team object.
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


def initialize():
    """initialize .synapseformation directory with state.json for one project"""
    pass


def _detect_team_drift(state_resource: dict, syn: Synapse, state: State) -> list:
    """Detect drift for team resources."""
    drift_results = []
    synapse_team = Team(id=state_resource["id"]).get()

    if synapse_team.name != state_resource["properties"]["name"]:
        drift_results.append(
            {
                "type": state_resource["type"],
                "name": state_resource["name"],
                "synapse_properties": {"name": synapse_team.name},
                "properties": state_resource["properties"],
            }
        )

    return drift_results


def _detect_project_drift(state_resource: dict, syn: Synapse, state: State) -> list:
    """Detect drift for project resources."""
    drift_results = []
    synapse_project = Project(id=state_resource["id"]).get()

    if synapse_project.name != state_resource["properties"]["name"]:
        drift_results.append(
            {
                "type": state_resource["type"],
                "name": state_resource["name"],
                "synapse_properties": {"name": synapse_project.name},
                "properties": state_resource["properties"],
            }
        )

    return drift_results


def _detect_folder_drift(state_resource: dict, syn: Synapse, state: State) -> list:
    """Detect drift for folder resources."""
    drift_results = []
    synapse_folder = Folder(id=state_resource["id"]).get()

    if synapse_folder.name != state_resource["properties"]["name"]:
        drift_results.append(
            {
                "type": state_resource["type"],
                "name": state_resource["name"],
                "synapse_properties": {"name": synapse_folder.name},
                "properties": state_resource["properties"],
            }
        )

    return drift_results


def _detect_acl_drift(state_resource: dict, syn: Synapse, state: State) -> list:
    """Detect drift for ACL resources."""
    drift_results = []
    acls_drifted = []

    for grants in state_resource["properties"]["grants"]:
        # Resolve logical principal name to actual ID
        # TODO: support when the principal is not specified in the config
        principal_ref = grants["principal"].split(".")  # e.g. "team.data_scientists"
        principal_type, principal_logical_name = principal_ref[0], principal_ref[1]
        principal_id = state.get_id(principal_logical_name, principal_type)

        if principal_id is None:
            print(
                f"Warning: Could not resolve principal {grants['principal']} to actual ID"
            )
            continue

        try:
            entity = get(state_resource["id"])
            actual_acl = entity.get_acl(principal_id=principal_id)
            if set(actual_acl) != set(grants["access_type"]):
                acls_drifted.append(
                    {
                        "principal": grants[
                            "principal"
                        ],  # Keep logical name for readability
                        "principal_id": principal_id,  # Include resolved ID for reference
                        "expected_access_type": grants["access_type"],
                        "actual_access_type": actual_acl,
                    }
                )
        except Exception as e:
            print(f"Error checking ACL for principal {grants['principal']}: {e}")
            continue

    if acls_drifted:
        drift_results.append(
            {
                "type": state_resource["type"],
                "name": state_resource["name"],
                "synapse_properties": acls_drifted,
                "properties": state_resource["properties"],
            }
        )

    return drift_results


# Registry of drift detection functions for each resource type
DRIFT_DETECTORS = {
    "team": _detect_team_drift,
    "project": _detect_project_drift,
    "folder": _detect_folder_drift,
    "acl": _detect_acl_drift,
}


def detect_synapse_drift(config: dict, syn: Synapse, state: State) -> list:
    """Detect drift between state file and actual Synapse resources.

    Args:
        config (dict): Configuration dictionary with resources
        syn (Synapse): Synapse client for API calls
        state (State): State object for resolving resource references and accessing resources

    Returns:
        list: List of drift detection results
    """
    drift_detection = []

    for state_resource in state.resources:
        # Skip resources that are deleted from config (handled in plan_config)
        if state_resource["name"] not in config["resources"]:
            continue

        resource_type = state_resource["type"]
        drift_detector = DRIFT_DETECTORS.get(resource_type)

        if drift_detector:
            try:
                drift_results = drift_detector(state_resource, syn, state)
                drift_detection.extend(drift_results)
            except Exception as e:
                # Log error and continue with other resources
                print(
                    f"Error detecting drift for {resource_type} '{state_resource['name']}': {e}"
                )
        else:
            print(f"No drift detector available for resource type: {resource_type}")

    return drift_detection


def plan_config(config: dict, syn: Synapse):
    """Reads the configuration file and compares it to the state file to determine what changes need to be made to reconcile any drift.

    Returns:
        dict: A dictionary containing the changes that need to be made to reconcile any drift.
            The keys are the resource types and the values are lists of dictionaries containing the changes for each resource.
            Each dictionary in the list has the following keys:
                - logical_name: The logical name of the resource.
                - action: The action to take for the resource (create, update, delete).
                - properties: The properties for the resource.
    """
    # Read the state file
    state = State()

    # Create a dictionary to store the changes that need to be made to reconcile any drift
    changes = []

    # Loop through the configuration file and compare it to the state file to determine what changes need to be made
    for logical_name, config_resource in config["resources"].items():
        # changes[config_resource['type']] = []
        # for resource in resources:
        #     logical_name = resource["logical_name"]
        resource_id = state.get_id(logical_name, config_resource["type"])
        if resource_id:
            # Resource exists, check for updates
            state_resource = next(
                (r for r in state.resources if r["name"] == logical_name), None
            )
            if (
                state_resource
                and state_resource["properties"] != config_resource["properties"]
            ):
                changes.append(
                    {
                        "type": config_resource["type"],
                        "name": logical_name,
                        "action": "update",
                        "properties": config_resource["properties"],
                    }
                )
        else:
            # Resource does not exist, mark for creation
            changes.append(
                {
                    "type": config_resource["type"],
                    "name": logical_name,
                    "action": "create",
                    "properties": config_resource["properties"],
                }
            )

    # Check for resources deleted from the config file
    for state_resource in state.resources:
        if state_resource["name"] not in config["resources"]:
            changes.append(
                {
                    "type": state_resource["type"],
                    "name": state_resource["name"],
                    "action": "delete",
                }
            )

    # Detect drift
    drift_detection = detect_synapse_drift(config, syn, state)

    return {"changes": changes, "drift": drift_detection}


def apply_config(config: dict):
    """Executes API calls to reconcile drift.
    Updates the state.json file with the new resource IDs and metadata.
    """
    state = State()
    resources = get_resources(resource_config=config["resources"])

    # 1. Teams
    for team in resources.get("team", []):
        apply_team(logical_name=team["name"], props=team["properties"], state=state)

    # 2. Projects
    for project in resources.get("project", []):
        apply_project(
            logical_name=project["name"], props=project["properties"], state=state
        )

    # 3. Folders (topologically sorted). Projects must be created first, then the ordering of
    # folders being stored matters, so get the correct ordering of folders.
    folder_order = sort_folders(resources.get("folder", []))
    for folder_logical_name in folder_order:
        props = config["resources"][folder_logical_name]["properties"]
        apply_folder(logical_name=folder_logical_name, props=props, state=state)

    # 4. Access Controls have to come last since they depend on other resources
    for acl in resources.get("acl", []):
        apply_acl(acl=acl, state=state)


def destroy_resources(syn: Synapse):
    """Deletes Synapse resources created by synapseformation through the state file."""
    state = State()
    resources = defaultdict(list)
    for resource in state.resources:
        resources[resource["type"]].append(resource)
    # Must delete ACLs first to be able to delete teams (in case there are ACLs provided to teams)
    resources_acl = resources.get("acl", [])
    for resource in resources_acl:
        id = resource["id"]
        for grants in resource["properties"]["grants"]:
            # Resolve logical principal name to actual ID (same pattern as apply_acl)
            principal_ref = grants["principal"].split(
                "."
            )  # e.g. "team.data_scientists"
            principal_type, principal_logical_name = principal_ref[0], principal_ref[1]
            principal_id = state.get_id(principal_logical_name, principal_type)

            if principal_id:
                syn.setPermissions(entity=id, principalId=principal_id, accessType=[])
            else:
                print(
                    f"Warning: Could not resolve principal {grants['principal']} for cleanup"
                )

    projects = resources.get("project", [])
    for resource in projects:
        Project(id=resource["id"]).delete()

    teams = resources.get("team", [])
    for resource in teams:
        Team(id=resource["id"]).delete()
    state.clear()


def export():
    """Reads Synapse resources and dumps them into YAML."""
    pass


def sync_drift():
    """Sync the drift detected and align the state file with what is on Synapse"""
    pass
