import json
from pathlib import Path

import yaml


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as file_obj:
        data = yaml.safe_load(file_obj)
    if not isinstance(data, dict):
        raise ValueError("YAML root must be a mapping/object")
    return data


def write_output(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(obj, file_obj, indent=2)


def write_yaml(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_obj:
        yaml.dump(obj, file_obj, default_flow_style=False, sort_keys=False, allow_unicode=True)