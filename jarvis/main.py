"""Jarvis entry point: listens for hotkeys and runs the three voice modes."""

import queue
import threading
import time

from . import desktop, quick
from .audio import Recorder, Transcriber
from .brain import make_brain
from .config import config
from .hotkeys import start_listener
from .hud import make_hud, reply_seconds

try:
    from .notch import NotchHUD
except ImportError:  # not a Mac, or PyObjC isn't installed

    class NotchHUD:  # stand-in so the isinstance check below still works
        pass


class Jarvis:
    def __init__(self):
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.brain = make_brain()
        self.hud = make_hud()
        self.hud.set_level_source(lambda: self.recorder.level)
        self.brain.attach(self.hud)
        self.mode: str | None = None
        # Work runs on one background thread so the hotkey listener never blocks.
        self.jobs: queue.Queue = queue.Queue()

    def start(self, mode: str) -> None:
        if self.recorder.recording:
            return
        self.mode = mode
        self.recorder.start()
        self.hud.listening(mode)

    def stop(self, mode: str) -> None:
        if not self.recorder.recording or mode != self.mode:
            return
        audio = self.recorder.stop()
        self.mode = None
        self.hud.thinking("")
        self.jobs.put((mode, audio))

    def cancel(self, mode: str) -> None:
        """Throws the recording away, e.g. when the key was only tapped."""
        if not self.recorder.recording or mode != self.mode:
            return
        self.recorder.stop()
        self.mode = None
        self.hud.hide()

    def _escape(self) -> None:
        # Ignore the Esc that Jarvis itself just pressed while working.
        if time.monotonic() - desktop.last_keys_at > 0.5:
            self.brain.stop_event.set()

    def toggle(self, mode: str) -> None:
        if self.recorder.recording:
            self.stop(mode)  # a different hotkey while listening is ignored
        else:
            self.start(mode)

    def handle(self, mode: str, audio) -> None:
        text = self.transcriber.transcribe(audio)
        if not text:
            self.hud.flash("Didn't catch that")
            return
        self.hud.thinking(text)

        if mode == "dictate":
            if config.clean_dictation:
                text = self.brain.clean_dictation(text)
            desktop.paste_text(text)
            self.hud.flash("Typed")
            return

        if mode == "ask":
            reply = self.brain.ask_about_screen(text, desktop.screenshot_png_base64(config.screenshot_width))
        else:
            quick_command = quick.match(text)
            if quick_command:
                reply = quick.run(quick_command)
            else:
                reply = self.brain.run_command(text)
        self.hud.reply(reply, heard=text)
        if config.speak_replies:
            desktop.speak(reply)  # returns once it has finished talking
            self.hud.hide(after=2.0)
        else:
            self.hud.hide(after=reply_seconds(reply))

    def worker(self) -> None:
        while True:
            mode, audio = self.jobs.get()
            try:
                self.handle(mode, audio)
            except Exception as error:
                self.hud.error(str(error))

    def run(self) -> None:
        threading.Thread(target=self.worker, daemon=True).start()
        print(f"Jarvis is running, using {config.provider} ({self.brain.model}).")

        # Hold-to-talk needs the macOS event loop, which the notch panel runs.
        if config.hold_keys and isinstance(self.hud, NotchHUD):
            from . import holdkeys

            tracker = holdkeys.HoldTracker(
                {
                    config.dictate_hold: "dictate",
                    config.ask_hold: "ask",
                    config.command_hold: "command",
                },
                start=self.start,
                stop=self.stop,
                cancel=self.cancel,
            )
            # Esc stops screen control between steps.
            self._monitors = holdkeys.install(tracker, on_escape=self._escape)
            print(f"  hold {config.dictate_hold}  dictate into any text field")
            print(f"  hold {config.ask_hold}  ask about what's on your screen")
            print(f"  hold {config.command_hold}  give a command")
            print("Talk while holding the key; let go to send. Esc stops Jarvis using your screen.")
            print("Press Ctrl+C here to quit.")
            self.hud.run(lambda: None)
            return

        hotkeys = {
            config.dictate_hotkey: lambda: self.toggle("dictate"),
            config.ask_hotkey: lambda: self.toggle("ask"),
            config.command_hotkey: lambda: self.toggle("command"),
        }
        system = "mac" if config.is_mac else "windows" if config.is_windows else "linux"
        listener = start_listener(hotkeys, system)
        print(f"  {config.dictate_hotkey}  dictate into any text field")
        print(f"  {config.ask_hotkey}  ask about what's on your screen")
        print(f"  {config.command_hotkey}  give a command")
        print("Press once to start talking and again to send.")
        print("Press Ctrl+C here to quit.")
        self.hud.run(listener.join)


def main() -> None:
    try:
        Jarvis().run()
    except KeyboardInterrupt:
        pass
    print("\nBye.")


if __name__ == "__main__":
    main()
