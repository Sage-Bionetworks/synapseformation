"""Utility functions"""
import yaml


def read_config(template_path: str) -> dict:
    """Read in yaml or json configuration

    Args:
        template_path: Path to yaml or json configuration

    Returns:
        Configuration
    """
    # JSON is technically yaml but not the other way around.
    # yaml.safe_load can actually read in json files.
    with open(template_path, "r") as template_f:
        config = yaml.safe_load(template_f)
    return config
