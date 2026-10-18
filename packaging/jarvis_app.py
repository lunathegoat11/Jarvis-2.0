"""What Jarvis.app runs when opened.

Output goes to ~/.jarvis/jarvis.log, since an app opened from Finder has no
terminal. `Jarvis --selftest` imports everything the app needs and exits;
the build runs it to catch anything missing from the bundle.
"""

import sys
from pathlib import Path


def selftest() -> None:
    import importlib

    modules = [
        "jarvis.main", "jarvis.notch", "jarvis.app", "jarvis.voice", "jarvis.audio",
        "jarvis.brain", "jarvis.screen", "jarvis.mail", "jarvis.macapps", "jarvis.setup",
        "jarvis.devices", "jarvis.contact", "jarvis.remote", "jarvis.imessage", "jarvis.macs",
        "jarvis.memory", "jarvis.habits", "jarvis.timers", "jarvis.info", "jarvis.browser",
        "jarvis.computer", "jarvis.quick", "jarvis.router", "jarvis.prefs", "jarvis.hotkeys",
        "jarvis.holdkeys",
        "faster_whisper", "ctranslate2", "onnxruntime", "kokoro_onnx", "sounddevice",
        "pynput.keyboard", "pynput.mouse", "mss", "PIL", "anthropic", "openai",
        "AppKit", "WebKit", "Quartz", "PyObjCTools.AppHelper",
    ]
    failed = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as error:  # noqa: BLE001 - report every failure
            failed.append(f"{name}: {error}")
    from jarvis import app

    if not app.HTML.exists():
        failed.append(f"missing {app.HTML}")
    if failed:
        print("Self-test FAILED:\n  " + "\n  ".join(failed))
        sys.exit(1)
    print("Self-test passed.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    log_dir = Path.home() / ".jarvis"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "jarvis.log", "a", buffering=1)
    sys.stdout = sys.stderr = log

    from jarvis.main import main

    main()
