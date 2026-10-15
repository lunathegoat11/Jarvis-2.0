"""Only one Jarvis may run at a time, so it can't spawn copies of itself."""

from jarvis import main
from jarvis.config import Config


def test_second_launch_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "config", Config(data_dir=tmp_path))
    main._instance_lock = None

    assert main.acquire_single_instance(wait_seconds=0) is True
    first = main._instance_lock

    # A second attempt, as if another Jarvis started, can't get the lock.
    main._instance_lock = None
    assert main.acquire_single_instance(wait_seconds=0.3) is False

    # After the first exits (closes its lock), a new launch succeeds.
    first.close()
    main._instance_lock = None
    assert main.acquire_single_instance(wait_seconds=0) is True
    main._instance_lock.close()
