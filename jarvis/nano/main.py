"""Jarvis Nano's main loop: hear "Hey Jarvis", listen, think, answer."""

import threading
import time
import traceback

from .. import contact, habits, memory, prefs, timers
from ..config import config
from .body import Body
from .speech import RobotVoice
from .tools import NANO_SYSTEM, ROBOT_TOOL_NAMES, run_robot_tool, tools_for
from .wake import Endpointer


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def fit_brain(brain, body, log=log):
    """Turns a Jarvis brain into Jarvis Nano's: robot tools instead of the
    desktop ones, and instructions for living in a robot. Everything else
    (the AI, memory, learning, streaming) is the same brain."""
    brain._command_tools = lambda: tools_for(brain)
    brain._command_system = lambda: (
        NANO_SYSTEM + brain.COMMAND_HINT + memory.prompt_section() + habits.prompt_section()
    )
    desktop_tool = brain._run_command_tool

    def run_tool(call):
        if call.name not in ROBOT_TOOL_NAMES:
            return desktop_tool(call)
        if call.args is None:
            return "Failed: the arguments were not valid JSON.", True
        try:
            return run_robot_tool(call.name, call.args, body, brain), False
        except Exception as error:
            log(f"{call.name} failed: {error}")
            return f"Failed: {error}", True

    brain._run_command_tool = run_tool
    return brain


class Nano:
    def __init__(self, body, brain, transcriber, wake, endpointer=None, log=log):
        self.body = body
        self.brain = brain
        self.transcriber = transcriber
        self.wake = wake
        self.endpointer = endpointer or Endpointer()
        self.log = log
        self.listening = False
        self.busy = False
        self.voice: RobotVoice | None = None
        # Each request gets a number; saying "Hey Jarvis" again bumps it and
        # the older request goes quiet.
        self.job = 0

    # ---- hearing ----------------------------------------------------------------

    def on_frame(self, frame) -> None:
        """Called with every 80 ms of the robot's microphone."""
        if self.listening:
            if self.endpointer.add(frame):
                self.listening = False
                audio = self.endpointer.audio()
                job = self.job
                threading.Thread(target=self._run_job, args=(audio, job), daemon=True).start()
            return
        if not self.busy:
            self.endpointer.background(frame)
        if self.wake.heard(frame, speaking=self.busy):
            self.on_wake()

    def on_wake(self) -> None:
        self.log('Heard "Hey Jarvis".')
        self.interrupt()
        self.endpointer.start()
        self.listening = True
        self.body.mood("listening")
        threading.Thread(target=self._beep, daemon=True).start()

    def _beep(self) -> None:
        from .. import voice

        try:
            self.body.say(voice.beep_wav())
        except RuntimeError:
            pass

    def interrupt(self) -> None:
        """Stops whatever Jarvis Nano is saying or doing."""
        self.job += 1
        if self.voice is not None:
            self.voice.stop()
        if self.busy:
            self.brain.cancel()
            try:
                self.body.stop()  # the wheels too, if it was driving
            except RuntimeError:
                pass
        self.busy = False

    # ---- answering ---------------------------------------------------------------

    def _run_job(self, audio, job: int) -> None:
        current = lambda: job == self.job  # noqa: E731
        self.busy = True
        try:
            self.body.mood("thinking")
            text = self.transcriber.transcribe(audio, str(prefs.get("vocabulary") or ""))
            if not current():
                return
            if not text:
                self.log("Didn't catch that.")
                self.say("Sorry, I didn't catch that.", job)
                return
            self.log(f"Heard: {text!r}")
            voice = RobotVoice(self.body, on_start=lambda: self.body.mood("speaking"), log=self.log)
            self.voice = voice
            try:
                reply = self.brain.run_command(text, on_text=voice.feed)
                if not current():
                    return
                self.log(f"Reply: {reply!r}")
                # A reply that wasn't streamed (a refusal, "too many steps")
                # still gets said.
                if " ".join(reply.split()) not in " ".join(voice.heard.split()):
                    voice.feed(" " + reply)
            finally:
                voice.finish(wait=current())
            try:
                habits.record(text, list(getattr(self.brain, "last_calls", [])))
            except Exception as error:
                self.log(f"Couldn't note that for habits: {error}")
        except Exception as error:
            if current():
                self.log("Something went wrong:")
                traceback.print_exc()
                self.say(f"Something went wrong. {error}", job)
        finally:
            if current():
                self.busy = False
                self.body.mood("idle")

    def say(self, text: str, job: int | None = None) -> None:
        voice = RobotVoice(self.body, on_start=lambda: self.body.mood("speaking"), log=self.log)
        if job is not None and job == self.job:
            self.voice = voice
        voice.feed(text)
        voice.finish()

    def announce(self, text: str) -> None:
        """Timers and reminders: said by the robot, and sent to the phone."""
        self.log(f"Announcing: {text!r}")

        def run():
            deadline = time.monotonic() + 90
            while (self.busy or self.listening) and time.monotonic() < deadline:
                time.sleep(0.5)
            if config.alerts_to_phone and contact.ntfy_configured():
                try:
                    contact.text_me(text)
                except Exception as error:
                    self.log(f"Couldn't send that to your phone: {error}")
            self.body.mood("happy")
            self.say(text)
            self.body.mood("idle")

        threading.Thread(target=run, daemon=True).start()

    def run(self) -> None:
        for frame in self.body.mic_frames(log=self.log):
            try:
                self.on_frame(frame)
            except Exception:
                traceback.print_exc()


def main() -> None:
    from ..audio import Transcriber
    from ..brain import make_brain
    from ..main import acquire_single_instance
    from .wake import WakeWord

    if not acquire_single_instance():
        print("Jarvis Nano is already running.")
        return
    body = Body()
    brain = fit_brain(make_brain(), body)
    transcriber = Transcriber()
    transcriber.warm_up()
    print("Getting the wake word ready (downloads once)...", flush=True)
    nano = Nano(body, brain, transcriber, WakeWord())
    timers.start(nano.announce)
    print(f"Jarvis Nano is running, using {config.provider} ({brain.model}).")
    print(f"  robot: {body.url}")
    print(f"  speech recognition: {transcriber.model_name}")
    print('Say "Hey Jarvis" near the robot. Press Ctrl+C here to quit.', flush=True)
    try:
        body.mood("idle")
        nano.run()
    except KeyboardInterrupt:
        pass
    try:
        body.stop()
        body.mood("sleepy")
    except RuntimeError:
        pass
    print("\nBye.")
