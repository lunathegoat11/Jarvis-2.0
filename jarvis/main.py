"""Jarvis entry point: listens for hotkeys and runs the three voice modes."""

import threading
import time
import traceback

from . import contact, desktop, habits, prefs, quick, remote, router, timers, tools, voice
from .audio import Recorder, Transcriber
from .brain import make_brain
from . import config as settings
from .config import config
from .hotkeys import start_listener
from .hud import make_hud, reply_seconds

try:
    from .notch import NotchHUD
except ImportError:  # not a Mac, or PyObjC isn't installed

    class NotchHUD:  # stand-in so the isinstance check below still works
        pass


# Dictation this short is typed as Whisper heard it, without an AI tidy-up.
SHORT_DICTATION_WORDS = 8

# Seconds of recording kept after the talk key is let go.
RECORDING_TAIL = 0.3


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


# Held open for the whole run so a second Jarvis can't start; the OS releases
# it automatically when this process exits.
_instance_lock = None


def acquire_single_instance(wait_seconds: float = 3.0) -> bool:
    """True if this is the only Jarvis running. False means one already is.

    Retries briefly so the app's own restart after setup can hand the lock
    over as the old copy exits, while a genuine second launch still fails.
    """
    global _instance_lock
    try:
        import fcntl

        config.data_dir.mkdir(parents=True, exist_ok=True)
        # Open without truncating (another copy may be using this file), so
        # the lock still works and startup never fails over the lock file.
        lock_file = open(config.data_dir / "jarvis.lock", "a")
    except Exception:
        # No fcntl (Windows), or a read-only home: don't block startup.
        return True
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _instance_lock = lock_file  # only on success, so losers leak nothing
            return True
        except OSError:
            if time.monotonic() >= deadline:
                lock_file.close()
                return False
            time.sleep(0.25)


def learn_habit(text: str, calls: list) -> None:
    """Notes a finished request so Jarvis can learn habits. Never gets in
    the way of the request itself."""
    try:
        habits.record(text, calls)
    except Exception as error:
        log(f"Couldn't note that for habits: {error}")


def chime() -> None:
    """A short sound before Jarvis speaks up on its own."""
    if not config.is_mac:
        return
    import subprocess

    try:
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


class Jarvis:
    def __init__(self):
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.brain = make_brain()
        self.hud = make_hud()
        self.hud.set_level_source(lambda: self.recorder.level)
        self.brain.attach(self.hud)
        if config.app_window:
            self.hud.attach_app(
                {
                    "provider": config.provider,
                    "model": self.brain.model,
                    "vision_model": self.brain.vision_model,
                }
            )
        self.mode: str | None = None
        # Each request runs on its own thread and gets a number. Pressing the
        # key again bumps the number, and older requests go quiet.
        self._job = 0
        self._busy = False
        # A habit Jarvis just offered: saying "yes" soon after does it.
        self.offer: dict | None = None

    def interrupt(self) -> None:
        """Stops everything Jarvis is doing so a new request can start."""
        self._job += 1
        voice.stop()
        if self._busy:
            # Only when something is running, so an idle press doesn't throw
            # away the last finished turn of the conversation.
            self.brain.cancel()
            self.hud.pointer_hide()
            log("Interrupted.")
        self._busy = False

    def _current(self, job: int) -> bool:
        return job == self._job

    def start(self, mode: str) -> None:
        if self.recorder.recording:
            return
        # Talking over Jarvis stops whatever it was saying or doing.
        self.interrupt()
        log(f"Listening ({mode})...")
        try:
            self.recorder.start()
        except Exception as problem:
            log(f"Couldn't open the microphone: {problem}")
            self.hud.error(
                "I couldn't open the microphone. Check System Settings > Sound > Input, "
                "then try again."
            )
            return
        self.mode = mode
        self.hud.listening(mode)

    def stop(self, mode: str) -> None:
        if not self.recorder.recording or mode != self.mode:
            return
        self.mode = None
        self.hud.thinking("")
        self._busy = True
        job = self._job
        threading.Thread(target=self._finish_recording, args=(mode, job), daemon=True).start()

    def _finish_recording(self, mode: str, job: int) -> None:
        # People tend to let go of the key just before their last word ends,
        # so keep listening a moment longer.
        time.sleep(RECORDING_TAIL)
        audio = self.recorder.stop()
        log("Stopped listening.")
        self._run_job(mode, audio, job)

    def cancel(self, mode: str) -> None:
        """Throws the recording away, e.g. when the key was only tapped."""
        if not self.recorder.recording or mode != self.mode:
            return
        self.recorder.stop()
        log("Too short, or another key was pressed; ignored.")
        self.mode = None
        self.hud.hide()

    def _escape(self) -> None:
        # Ignore the Esc that Jarvis itself just pressed while working.
        if time.monotonic() - desktop.last_keys_at < 0.5:
            return
        self.brain.stop_event.set()
        if self._busy:
            self.interrupt()
            self.hud.flash("Stopped")

    def toggle(self, mode: str) -> None:
        if self.recorder.recording:
            self.stop(mode)  # a different hotkey while listening is ignored
        else:
            self.start(mode)

    def handle(self, mode: str, audio, job: int = 0) -> None:
        current = lambda: self._current(job)  # noqa: E731
        started = time.monotonic()
        seconds = len(audio) / config.sample_rate
        # How loud the recording actually was. Near-zero means the microphone
        # gave us silence, almost always a permission or input-device problem
        # rather than unclear speech.
        import numpy as np

        peak = float(np.abs(audio).max()) if len(audio) else 0.0
        log(f"Got {seconds:.1f}s of audio (peak {peak:.4f}), transcribing...")
        vocabulary = str(prefs.get("vocabulary") or "")
        text = self.transcriber.transcribe(audio, vocabulary)
        if not current():
            return
        # Only blame the microphone when Whisper heard nothing AND the audio
        # was flat. Quiet Mac mics can peak low and still be perfectly usable.
        if not text and seconds >= 0.3 and peak < 0.001:
            log("The microphone gave silence. Is Jarvis allowed to use it?")
            self.hud.error(
                "I can't hear your microphone. Allow Terminal (or Jarvis, if you use the "
                "app) under System Settings > Privacy & Security > Microphone, then quit "
                "and reopen it."
            )
            return
        if not text:
            log("Heard nothing.")
            self.hud.flash("Didn't catch that")
            return
        log(f"Heard: {text!r} ({time.monotonic() - started:.1f}s)")
        offer = getattr(self, "offer", None)
        if offer and time.monotonic() < offer["until"] and habits.is_yes(text):
            log(f"Yes to the offer: {offer['said']!r}")
            text, mode = offer["said"], "command"
        self.offer = None
        if mode == "auto":
            mode, text = router.route(text)
            log(f"Treating that as: {mode}")
            if not text:
                self.hud.flash("Didn't catch that")
                return
        self.hud.thinking(text)

        if mode == "edit":
            selection = desktop.selected_text()
            if not current():
                return
            if selection.strip():
                log(f"Rewriting {len(selection)} selected characters...")
                rewritten = self.brain.edit_text(
                    text, selection, desktop.frontmost_app(), vocabulary
                )
                if not current():
                    return
                desktop.paste_text(rewritten)  # replaces the selection
                self.hud.flash("Rewritten · ⌘Z undoes")
                return
            log("Nothing selected, so treating it as a question about the screen.")
            mode = "ask"

        if mode == "dictate":
            # Whisper already punctuates; short bits don't need the AI's
            # tidy-up, which saves a round trip.
            if prefs.get("clean_dictation") and len(text.split()) > SHORT_DICTATION_WORDS:
                text = self.brain.clean_dictation(text, desktop.frontmost_app(), vocabulary)
            if not current():
                return
            desktop.paste_text(text)
            self.hud.flash("Typed")
            return

        asked_at = time.monotonic()
        # Jarvis starts talking as soon as the first sentence of the reply
        # arrives, instead of waiting for the whole thing.
        stream = None
        if prefs.get("speak_replies"):
            stream = voice.SpeechStream(on_start=lambda: self.hud.speaking(True))
        on_text = stream.feed if stream else None
        try:
            calls: list = []
            if mode == "ask":
                log(f"Asking {self.brain.vision_model} about the screen...")
                shot = desktop.screenshot_png_base64(config.screenshot_width)
                reply = self.brain.ask_about_screen(text, shot, on_text=on_text)
            else:
                quick_command = quick.match(text)
                if quick_command:
                    log(f"Quick command: {quick_command.action}")
                    reply = quick.run(quick_command)
                    calls = [(quick_command.action, quick_command.args)]
                else:
                    log(f"Asking {self.brain.model}...")
                    reply = self.brain.run_command(text, on_text=on_text)
                    calls = list(getattr(self.brain, "last_calls", []))
            if not current():
                log("(Dropped the reply to an interrupted request.)")
                return
            log(f"Reply: {reply!r} ({time.monotonic() - asked_at:.1f}s)")
            learn_habit(text, calls)
            shown = voice.clean_for_speech(reply, keep_links=True)
            self.hud.reply(shown, heard=text)
            if stream:
                try:
                    stream.finish()  # returns once said, or when interrupted
                    # Replies that weren't streamed (quick commands, refusals,
                    # "too many steps") are said now.
                    if current() and " ".join(reply.split()) not in " ".join(stream.heard.split()):
                        self.hud.speaking(True)
                        desktop.speak(reply)
                finally:
                    if current():
                        self.hud.speaking(False)
                if current():
                    self.hud.hide(after=2.0)
            else:
                self.hud.hide(after=reply_seconds(shown))
        finally:
            if stream:
                stream.finish(wait=False)

    def offer_habit(self) -> None:
        """Called each minute: offers to do something the user usually asks
        for around now (see habits.py)."""
        if not config.habit_suggestions or self._busy or self.recorder.recording:
            return
        habit = habits.due_suggestion()
        if habit is None:
            return
        self.offer = {"said": habit["said"], "until": time.monotonic() + 180}
        self.announce(
            f'You usually ask me "{habit["said"]}" around now. Want me to? Just say yes.',
            to_phone=False,
        )

    def announce(self, text: str, to_phone: bool = True) -> None:
        """Says a timer, reminder or briefing out loud (after a chime), shows
        it in the notch, and sends it to the phone when ntfy is set up."""
        log(f"Announcing: {text!r}")

        def run():
            # Let whatever Jarvis is in the middle of (or you are saying) finish first.
            deadline = time.monotonic() + 90
            while (self._busy or self.recorder.recording) and time.monotonic() < deadline:
                time.sleep(0.5)
            if to_phone and config.alerts_to_phone and contact.ntfy_configured():
                try:
                    contact.text_me(text)
                except Exception as error:
                    log(f"Couldn't send that to your phone: {error}")
            chime()
            shown = voice.clean_for_speech(text, keep_links=True)
            self.hud.reply(shown)
            if prefs.get("speak_replies"):
                self.hud.speaking(True)
                try:
                    desktop.speak(text)
                finally:
                    self.hud.speaking(False)
                self.hud.hide(after=2.0)
            else:
                self.hud.hide(after=reply_seconds(shown))

        threading.Thread(target=run, daemon=True).start()

    def briefing(self) -> None:
        """The daily briefing, at JARVIS_BRIEFING_TIME."""

        def run():
            deadline = time.monotonic() + 300
            while self._busy and time.monotonic() < deadline:
                time.sleep(1)
            log("Time for the daily briefing.")
            self._busy = True
            job = self._job  # pressing the key to talk cancels the briefing
            try:
                reply = self.brain.run_command("Good morning. Give me my briefing.")
            except Exception as error:
                log(f"The briefing failed: {error}")
                return
            finally:
                if self._current(job):
                    self._busy = False
            if self._current(job):
                self.announce(reply)

        threading.Thread(target=run, daemon=True).start()

    def phone_message(self, text: str) -> None:
        """A message typed on the phone (see remote.py): run it like a spoken
        command and send the answer back to the phone."""
        log(f"From your phone: {text!r}")
        self.interrupt()
        self._busy = True
        job = self._job
        threading.Thread(target=self._run_phone_job, args=(text, job), daemon=True).start()

    def _run_phone_job(self, text: str, job: int) -> None:
        current = lambda: self._current(job)  # noqa: E731
        documents_before = len(tools.made_documents)
        try:
            self.hud.thinking(text)
            quick_command = quick.match(text)
            if quick_command:
                reply = quick.run(quick_command)
            else:
                note = (
                    "[Typed on the user's phone while they're away from the Mac. Your reply "
                    "goes back to their phone by itself, so keep it to a sentence or two and "
                    "don't use text_me or call_me to answer. For anything long they ask for, "
                    "like notes or a study sheet, use write_document; the file is sent to "
                    "their phone too."
                )
                if contact.last_alert:
                    note += f' Your last alert to their phone said: "{contact.last_alert}"'
                reply = self.brain.run_command(f"{note}]\n{text}")
            if not current():
                return
            log(f"Reply: {reply!r}")
            learn_habit(
                text,
                [(quick_command.action, quick_command.args)] if quick_command
                else list(getattr(self.brain, "last_calls", [])),
            )
            shown = voice.clean_for_speech(reply, keep_links=True)
            self.hud.reply(shown, heard=text)
            self.hud.hide(after=reply_seconds(shown))
            documents = tools.made_documents[documents_before:]
            if documents:
                for document in documents:
                    contact.send_file(document, shown)
            else:
                contact.text_me(shown)
        except Exception as error:
            log("A message from your phone failed:")
            traceback.print_exc()
            if current():
                self.hud.error(str(error))
            try:
                contact.text_me(f"That didn't work: {error}")
            except Exception:
                pass
        finally:
            if current():
                self._busy = False

    def _run_job(self, mode: str, audio, job: int) -> None:
        try:
            self.handle(mode, audio, job)
        except Exception as error:
            if self._current(job):
                log("Something went wrong:")
                traceback.print_exc()
                self.hud.error(str(error))
        finally:
            if self._current(job):
                self._busy = False

    def run(self) -> None:
        voice.warm_up()
        self.transcriber.warm_up()
        print(f"Jarvis is running, using {config.provider} ({self.brain.model}).")
        print(f"  speech recognition: {self.transcriber.model_name}"
              + (" on the GPU" if self.transcriber.engine == "mlx" else ""))
        timers.start(self.announce, self.briefing, every_minute=self.offer_habit)
        if config.briefing_time:
            print(f"  daily briefing at {config.briefing_time}")
        if remote.configured():
            remote.listen(self.phone_message, log=log)
            print("  messages from your phone are on (ntfy)")
        elif config.ntfy_reply_topic:
            print("  NTFY_REPLY_TOPIC must be different from NTFY_TOPIC; phone messages are off.")

        # Hold-to-talk needs the macOS event loop, which the notch panel runs.
        if config.hold_keys and isinstance(self.hud, NotchHUD):
            from . import holdkeys

            if config.one_key:
                bindings = {config.jarvis_hold: "auto"}
            else:
                bindings = {
                    config.dictate_hold: "dictate",
                    config.ask_hold: "ask",
                    config.command_hold: "command",
                }
            tracker = holdkeys.HoldTracker(
                bindings, start=self.start, stop=self.stop, cancel=self.cancel
            )
            # Esc stops screen control between steps.
            self._monitors = holdkeys.install(tracker, on_escape=self._escape)
            if config.one_key:
                print(f"  hold {config.jarvis_hold} and talk:")
                print('    "type see you at six"         types it where you are')
                print('    "what does this error mean"   answers about your screen')
                print('    anything else                 a command')
            else:
                print(f"  hold {config.dictate_hold}  dictate into any text field")
                print(f"  hold {config.ask_hold}  ask about what's on your screen")
                print(f"  hold {config.command_hold}  give a command")
            print("Talk while holding the key; let go to send. Esc stops Jarvis using your screen.")
            print("Press Ctrl+C here to quit.")
            self.hud.run(lambda: None)
            return

        if config.one_key:
            hotkeys = {config.command_hotkey: lambda: self.toggle("auto")}
        else:
            hotkeys = {
                config.dictate_hotkey: lambda: self.toggle("dictate"),
                config.ask_hotkey: lambda: self.toggle("ask"),
                config.command_hotkey: lambda: self.toggle("command"),
            }
        system = "mac" if config.is_mac else "windows" if config.is_windows else "linux"
        listener = start_listener(hotkeys, system)
        if config.one_key:
            print(f"  {config.command_hotkey}  talk to Jarvis (say \"type ...\" to dictate)")
        else:
            print(f"  {config.dictate_hotkey}  dictate into any text field")
            print(f"  {config.ask_hotkey}  ask about what's on your screen")
            print(f"  {config.command_hotkey}  give a command")
        print("Press once to start talking and again to send.")
        print("Press Ctrl+C here to quit.")
        self.hud.run(listener.join)


def main() -> None:
    if not acquire_single_instance():
        print("Jarvis is already running. Quit the other copy first (menu-bar icon > Quit).")
        return
    try:
        jarvis = Jarvis()
    except (SystemExit, Exception) as problem:
        # The downloadable app has no terminal to show this in, so it opens a
        # setup screen instead of just vanishing (missing or wrong key, unknown
        # provider, a mangled .env line, a provider that won't load, ...).
        if config.is_mac and settings.IS_APP:
            from .setup import run_setup_window

            run_setup_window(str(problem) or problem.__class__.__name__)
            return
        # Running from the terminal: print it plainly so the cause is visible.
        traceback.print_exc()
        raise SystemExit(str(problem) or problem.__class__.__name__)
    try:
        jarvis.run()
    except KeyboardInterrupt:
        pass
    print("\nBye.")


if __name__ == "__main__":
    main()
