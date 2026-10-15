import pytest

from jarvis import devices
from jarvis.config import Config
from jarvis.devices import Device


def test_ssdp_location_is_read():
    reply = "HTTP/1.1 200 OK\r\nCache-Control: max-age=3600\r\nST: roku:ecp\r\nLOCATION: http://192.168.1.20:8060/\r\n\r\n"
    assert devices.parse_ssdp(reply) == "http://192.168.1.20:8060/"
    assert devices.parse_ssdp("HTTP/1.1 200 OK\r\n\r\n") is None


DEVICES = [
    Device("Living Room TV", "roku", "http://tv:8060"),
    Device("Kitchen", "sonos"),
    Device("Bedroom speaker", "chromecast"),
]


@pytest.mark.parametrize(
    "said, expected",
    [
        ("living room tv", "Living Room TV"),
        ("the living room TV", "Living Room TV"),
        ("kitchen", "Kitchen"),
        ("bedroom", "Bedroom speaker"),
        ("TV", "Living Room TV"),
    ],
)
def test_find_by_name(said, expected):
    assert devices.find(said, DEVICES).name == expected


def test_unknown_device_lists_what_exists():
    with pytest.raises(RuntimeError, match="Living Room TV, Kitchen"):
        devices.find("garage", DEVICES)


def test_roku_keys_and_apps(monkeypatch):
    sent = []
    monkeypatch.setattr(devices, "_roku", lambda device, path: sent.append(path))
    tv = DEVICES[0]
    devices.control(tv, "volume_up")
    devices.control(tv, "next")
    devices.open_app(tv, "Netflix")
    devices.open_app(tv, "", search="Stranger Things")
    assert sent == [
        "/keypress/VolumeUp",
        "/keypress/Fwd",
        "/launch/12",
        "/search/browse?keyword=Stranger+Things&launch=true",
    ]
    with pytest.raises(RuntimeError):
        devices.control(tv, "set_volume", 30)


def test_sonos_volume_goes_to_the_speaker(monkeypatch):
    class Speaker:
        volume, mute, group = 20, False, None
        played = False

        def play(self):
            self.played = True

    speaker = Speaker()
    sonos = Device("Kitchen", "sonos", speaker)
    devices.control(sonos, "set_volume", 140)
    devices.control(sonos, "play")
    assert speaker.volume == 100 and speaker.played


def test_home_assistant_sentence(monkeypatch):
    monkeypatch.setattr(devices, "config", Config(home_assistant_url="http://ha:8123/", home_assistant_token="t"))
    calls = []

    def fake(path, body=None):
        calls.append((path, body))
        return {"response": {"speech": {"plain": {"speech": "Turned off the lights."}}}}

    monkeypatch.setattr(devices, "_ha_request", fake)
    assert devices.home_command("turn off the lights") == "Turned off the lights."
    devices.alexa_announce("Dinner's ready", "Kitchen Echo")
    assert calls[0] == ("/api/conversation/process", {"text": "turn off the lights", "language": "en"})
    assert calls[1][0] == "/api/services/notify/alexa_media_kitchen_echo"


def test_home_assistant_needs_setting_up(monkeypatch):
    monkeypatch.setattr(devices, "config", Config(home_assistant_url="", home_assistant_token=""))
    with pytest.raises(RuntimeError, match="HOME_ASSISTANT_URL"):
        devices.home_command("lights off")
