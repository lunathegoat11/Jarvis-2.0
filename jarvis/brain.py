"""Everything that talks to Claude."""

import time
from datetime import datetime

import anthropic

from .config import config
from .tools import TOOLS, run_tool

# With "default", a request Claude's safety checks decline is retried on
# another model inside the same call instead of failing outright.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

DICTATE_SYSTEM = """\
You clean up dictated speech so it can be pasted straight into a document, \
message or text field. Remove filler words (um, uh, like, you know), false \
starts and repeated words. Fix punctuation, capitalisation and obvious \
transcription mistakes. When the speaker corrects themselves ("at 3, no, \
at 4"), keep only the correction. Keep their wording, tone and meaning; do \
not add content, answer questions in the text, or summarise. Reply with the \
cleaned text only."""

ASK_SYSTEM = """\
You are Jarvis, a voice assistant on the user's computer. The user is asking \
about what is on their screen; a screenshot is attached. Your reply is read \
aloud, so answer in a few plain spoken sentences with no markdown, lists or \
code blocks unless they ask for code."""

COMMAND_SYSTEM = """\
You are Jarvis, a voice assistant that controls the user's computer. The user \
speaks commands; you carry them out with your tools, then say briefly what you \
did. Your reply is read aloud, so keep it to one or two plain sentences with no \
markdown. If a request is unclear or no tool can do it, say so rather than \
guessing. Search the web when a question needs current information."""

# Command-mode conversations are forgotten after this much idle time.
COMMAND_MEMORY_SECONDS = 15 * 60


class Brain:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self._command_history: list = []
        self._last_command_at = 0.0

    def _create(self, **kwargs):
        response = self.client.beta.messages.create(
            model=config.model,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            **kwargs,
        )
        return response

    @staticmethod
    def _text(response) -> str:
        if response.stop_reason == "refusal":
            return "Sorry, I can't help with that one."
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def clean_dictation(self, transcript: str) -> str:
        response = self._create(
            system=DICTATE_SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": transcript}],
        )
        return self._text(response) or transcript

    def ask_about_screen(self, question: str, screenshot_b64: str) -> str:
        response = self._create(
            system=ASK_SYSTEM,
            output_config={"effort": "medium"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {"type": "text", "text": question},
                    ],
                }
            ],
        )
        return self._text(response)

    def run_command(self, command: str) -> str:
        now = time.monotonic()
        if now - self._last_command_at > COMMAND_MEMORY_SECONDS:
            self._command_history = []
        self._last_command_at = now

        stamp = datetime.now().strftime("%A %d %B %Y, %H:%M")
        messages = self._command_history
        messages.append({"role": "user", "content": f"[{stamp}] {command}"})

        while True:
            response = self._create(
                system=COMMAND_SYSTEM,
                output_config={"effort": "medium"},
                tools=TOOLS,
                messages=messages,
            )
            # Keep the whole content list (thinking and tool blocks included);
            # the API expects it back unchanged on the next request.
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "pause_turn":
                continue
            if response.stop_reason != "tool_use":
                return self._text(response)

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                try:
                    output = run_tool(block.name, block.input)
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": output}
                    )
                except Exception as error:
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Failed: {error}",
                            "is_error": True,
                        }
                    )
            messages.append({"role": "user", "content": results})
