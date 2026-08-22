import json

from core.resource_paths import application_resource_path


CONFIG_PATH = application_resource_path("config", "qc_threshold.json")


def load_qc_config():

    with CONFIG_PATH.open("r", encoding="utf-8") as f:

        return json.load(f)
