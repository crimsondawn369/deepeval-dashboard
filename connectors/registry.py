import os

import yaml

from connectors.magnolai_stream import MagnolaiStreamConnector

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "connectors.yaml")


def load_registry(config_path: str = _CONFIG_PATH) -> dict[str, MagnolaiStreamConnector]:
    with open(config_path) as f:
        config = yaml.safe_load(f)
    registry: dict[str, MagnolaiStreamConnector] = {}
    for stream in config.get("streams", []):
        registry[stream["id"]] = MagnolaiStreamConnector(stream)
    return registry


CONNECTORS: dict[str, MagnolaiStreamConnector] = load_registry()


def get_connector(stream_id: str) -> MagnolaiStreamConnector:
    if stream_id not in CONNECTORS:
        valid = ", ".join(sorted(CONNECTORS.keys()))
        raise KeyError(
            f"Unknown stream id '{stream_id}'. Valid ids: {valid}"
        )
    return CONNECTORS[stream_id]
