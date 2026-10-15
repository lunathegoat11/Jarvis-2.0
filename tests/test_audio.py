import sys
import types

import numpy as np

from jarvis import audio
from jarvis.audio import Recorder, pick_device

DEVICES = [
    {"name": "Shlok's AirPods", "max_input_channels": 1, "default_samplerate": 24000},
    {"name": "Shlok's AirPods", "max_input_channels": 0, "default_samplerate": 48000},
    {"name": "MacBook Air Microphone", "max_input_channels": 1, "default_samplerate": 48000},
]


def test_auto_prefers_the_macbook_mic_over_airpods():
    assert pick_device(DEVICES, "auto") == 2
    assert pick_device(DEVICES, "airpods") == 0
    assert pick_device(DEVICES, "default") is None
    assert pick_device(DEVICES, "nothing like it") is None


def _fake_sounddevice(refuse_rates, stale=False):
    sd = types.SimpleNamespace(opened=[], resets=0)

    class PortAudioError(Exception):
        pass

    class InputStream:
        def __init__(self, device, samplerate, channels, dtype, callback):
            if sd.stale and not sd.resets:
                raise PortAudioError("Invalid Property Value")
            if samplerate in refuse_rates:
                raise PortAudioError("Invalid Property Value")
            sd.opened.append((device, samplerate))

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            pass

    def query_devices(device=None, kind=None):
        if device is None and kind is None:
            return DEVICES
        return DEVICES[device if device is not None else 0]

    def reset():
        sd.resets += 1

    sd.PortAudioError = PortAudioError
    sd.InputStream = InputStream
    sd.query_devices = query_devices
    sd._terminate = reset
    sd._initialize = lambda: None
    sd.stale = stale
    return sd


def test_a_mic_that_refuses_16khz_records_at_its_own_rate(monkeypatch):
    sd = _fake_sounddevice(refuse_rates={16000})
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    recorder = Recorder()
    recorder.start()
    assert sd.opened == [(2, 48000)]
    recorder._on_audio(np.ones((4800, 1), dtype=np.float32), 4800, None, None)
    result = recorder.stop()
    # A tenth of a second at 48 kHz becomes a tenth of a second at 16 kHz.
    assert result.size == 1600 and result.dtype == np.float32


def test_a_stale_device_list_is_refreshed_and_retried(monkeypatch):
    sd = _fake_sounddevice(refuse_rates=set(), stale=True)
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    Recorder().start()
    assert sd.resets == 1
    assert sd.opened == [(2, 16000)]
