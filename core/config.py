import json
from pathlib import Path


CONFIG_PATH = Path(
    "config/qc_threshold.json"
)


def load_qc_config():

    with open(
        CONFIG_PATH,
        "r"
    ) as f:

        return json.load(f)
