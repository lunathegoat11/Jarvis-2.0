"""Jarvis entry point: listens for hotkeys and runs the three voice modes."""

import queue
import threading

from . import desktop
from .audio import Recorder, Transcriber
from .brain import make_brain
from .config import config
from .hotkeys import start_listener
from .hud import make_hud, reply_seconds


class Jarvis:
    def __init__(self):
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.brain = make_brain()
        self.hud = make_hud()
        self.hud.set_level_source(lambda: self.recorder.level)
        self.mode: str | None = None
        # Work runs on one background thread so the hotkey listener never blocks.
        self.jobs: queue.Queue = queue.Queue()

    def toggle(self, mode: str) -> None:
        if self.recorder.recording:
            if mode != self.mode:
                return  # a different hotkey while listening; ignore it
            audio = self.recorder.stop()
            self.mode = None
            self.hud.thinking("")
            self.jobs.put((mode, audio))
        else:
            self.mode = mode
            self.recorder.start()
            self.hud.listening(mode)

    def handle(self, mode: str, audio) -> None:
        text = self.transcriber.transcribe(audio)
        if not text:
            self.hud.flash("Didn't catch that")
            return
        self.hud.thinking(text)

        if mode == "dictate":
            desktop.paste_text(self.brain.clean_dictation(text))
            self.hud.flash("Typed")
            return

        if mode == "ask":
            reply = self.brain.ask_about_screen(text, desktop.screenshot_png_base64())
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
        hotkeys = {
            config.dictate_hotkey: lambda: self.toggle("dictate"),
            config.ask_hotkey: lambda: self.toggle("ask"),
            config.command_hotkey: lambda: self.toggle("command"),
        }
        system = "mac" if config.is_mac else "windows" if config.is_windows else "linux"
        listener = start_listener(hotkeys, system)

        print(f"Jarvis is running, using {config.provider} ({config.model}).")
        print(f"  {config.dictate_hotkey}  dictate into any text field")
        print(f"  {config.ask_hotkey}  ask about what's on your screen")
        print(f"  {config.command_hotkey}  give a command")
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
