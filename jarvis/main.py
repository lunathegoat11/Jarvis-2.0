"""Jarvis entry point: listens for hotkeys and runs the three voice modes."""

import queue
import threading

from . import desktop
from .audio import Recorder, Transcriber
from .brain import make_brain
from .config import config


class Jarvis:
    def __init__(self):
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.brain = make_brain()
        self.mode: str | None = None
        # Work runs on one background thread so the hotkey listener never blocks.
        self.jobs: queue.Queue = queue.Queue()

    def toggle(self, mode: str) -> None:
        if self.recorder.recording:
            if mode != self.mode:
                return  # a different hotkey while listening; ignore it
            audio = self.recorder.stop()
            self.jobs.put((mode, audio))
            print(f"Stopped listening ({mode}).")
            self.mode = None
        else:
            self.mode = mode
            self.recorder.start()
            print(f"Listening ({mode})... press the same keys again to stop.")

    def handle(self, mode: str, audio) -> None:
        text = self.transcriber.transcribe(audio)
        if not text:
            print("Didn't catch anything.")
            return
        print(f"You said: {text}")

        if mode == "dictate":
            desktop.paste_text(self.brain.clean_dictation(text))
        elif mode == "ask":
            answer = self.brain.ask_about_screen(text, desktop.screenshot_png_base64())
            desktop.notify("Jarvis", answer)
            desktop.speak(answer)
        elif mode == "command":
            reply = self.brain.run_command(text)
            desktop.notify("Jarvis", reply)
            desktop.speak(reply)

    def worker(self) -> None:
        while True:
            mode, audio = self.jobs.get()
            try:
                self.handle(mode, audio)
            except Exception as error:
                desktop.notify("Jarvis hit a problem", str(error))

    def run(self) -> None:
        from pynput import keyboard

        threading.Thread(target=self.worker, daemon=True).start()
        hotkeys = {
            config.dictate_hotkey: lambda: self.toggle("dictate"),
            config.ask_hotkey: lambda: self.toggle("ask"),
            config.command_hotkey: lambda: self.toggle("command"),
        }
        print("Jarvis is running.")
        print(f"  {config.dictate_hotkey}  dictate into any text field")
        print(f"  {config.ask_hotkey}  ask about what's on your screen")
        print(f"  {config.command_hotkey}  give a command")
        print("Press Ctrl+C here to quit.")
        with keyboard.GlobalHotKeys(hotkeys) as listener:
            listener.join()


def main() -> None:
    try:
        Jarvis().run()
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
