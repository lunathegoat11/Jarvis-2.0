import pytest

from jarvis import habits, macs, memory
from jarvis.config import Config


@pytest.fixture(autouse=True)
def private_data(tmp_path, monkeypatch):
    """Keeps what tests learn (memories, habits) out of the real ~/.jarvis."""
    data = tmp_path / "jarvis-data"
    monkeypatch.setattr(habits, "config", Config(data_dir=data))
    monkeypatch.setattr(memory, "config", Config(data_dir=data))
    monkeypatch.setattr(macs, "config", Config(data_dir=data, mac_name="", ntfy_macs_topic=""))
    return data
