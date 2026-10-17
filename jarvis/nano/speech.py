"""Jarvis Nano's voice: replies spoken through the robot's speaker."""

import queue
import threading

from .. import voice


class RobotVoice:
    """Speaks a reply through the robot sentence by sentence while the AI is
    still writing it, like desktop Jarvis does through the computer's
    speakers. The next sentence is turned into audio here while the robot
    plays the current one."""

    def __init__(self, body, on_start=None, render=None, log=print):
        self.body = body
        self.render = render or voice.render_wav
        self.on_start = on_start
        self.log = log
        self.heard = ""  # everything fed in, to tell what was already said
        self.spoke = False
        self._buffer = ""
        self._stopped = False
        self._finished = False
        self._sentences: queue.Queue = queue.Queue()
        self._audio: queue.Queue = queue.Queue()
        threading.Thread(target=self._render_all, daemon=True).start()
        self._player = threading.Thread(target=self._play_all, daemon=True)
        self._player.start()

    def feed(self, text: str) -> None:
        self.heard += text
        self._buffer += text
        *done, self._buffer = voice.SPEAKABLE_END.split(self._buffer)
        for sentence in done:
            self._put(sentence)

    def finish(self, wait: bool = True) -> None:
        if not self._finished:
            self._finished = True
            self._put(self._buffer)
            self._buffer = ""
            self._sentences.put(None)
        if wait:
            self._player.join()

    def stop(self) -> None:
        """Goes quiet straight away (when you say "Hey Jarvis" over it)."""
        self._stopped = True
        self.body.stop_speaking()

    def _put(self, sentence: str) -> None:
        if sentence.strip():
            self._sentences.put(sentence)

    def _render_all(self) -> None:
        while (sentence := self._sentences.get()) is not None:
            if self._stopped:
                continue
            text = voice.clean_for_speech(sentence)
            if not text:
                continue
            try:
                self._audio.put(self.render(text))
            except Exception as error:
                self.log(f"Couldn't make speech: {error}")
        self._audio.put(None)

    def _play_all(self) -> None:
        while (wav := self._audio.get()) is not None:
            if self._stopped or not wav:
                continue
            if not self.spoke:
                self.spoke = True
                if self.on_start:
                    self.on_start()
            try:
                self.body.say(wav)
            except RuntimeError as error:
                self.log(f"The robot couldn't play that: {error}")
                self._stopped = True
