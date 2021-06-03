"""Utility functions"""
import yaml


# def read_yaml_config(template_path: str) -> dict:
#     """Get yaml synapse formation template

#     Args:
#         template_path: Path to yaml synapse formation template

#     Returns:
#         dict for synapse configuration
#     """
#     with open(template_path, "r") as template_f:
#         template = yaml.safe_load(template_f)
#     return template


# def read_json_config(template_path):
#     """Get json synapse formation template

#     Args:
#         template_path: Path to yaml synapse formation template

#     Returns:
#         dict for synapse configuration
#     """
#     with open(template_path, "r") as template_f:
#         template = json.load(template_f)
#     return template


def read_config(template_path: str):
    """Read in yaml or json configuration"""
    # JSON is technically yaml but not the other way around.
    # yaml.safe_load can actually read in json files.
    with open(template_path, "r") as template_f:
        config = yaml.safe_load(template_f)
    return config

# class Ref(yaml.YAMLObject):
#     yaml_loader = yaml.SafeLoader
#     yaml_tag = '!Ref'
#     def __init__(self, val):
#         self.val = val

#     @classmethod
#     def from_yaml(cls, loader, node):
#         return cls(node.value)
# # yaml.safe_load('Foo: !Ref bar')
