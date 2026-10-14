"""Everything that talks to the AI model.

There are two backends: Anthropic's API for Claude, and the OpenAI
chat-completions format, which NVIDIA, Ollama and most other providers
accept. make_brain() picks one from JARVIS_PROVIDER.
"""

import json
import time
from datetime import datetime

from .config import config
from .tools import ANTHROPIC_TOOLS, OPENAI_TOOLS, run_tool

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
guessing."""

WEB_SEARCH_HINT = " Search the web when a question needs current information."

REFUSAL_REPLY = "Sorry, I can't help with that one."

# Command-mode conversations are forgotten after this much idle time.
COMMAND_MEMORY_SECONDS = 15 * 60

# A model that keeps calling tools without finishing gets stopped here.
MAX_TOOL_ROUNDS = 10


def _run_tool_safely(name: str, args: dict) -> tuple[str, bool]:
    """Returns (output, failed)."""
    try:
        return run_tool(name, args), False
    except Exception as error:
        return f"Failed: {error}", True


class Brain:
    def __init__(self):
        self._command_history: list = []
        self._last_command_at = 0.0

    def _start_command(self, command: str) -> list:
        """Returns the command history with the new command added."""
        now = time.monotonic()
        if now - self._last_command_at > COMMAND_MEMORY_SECONDS:
            self._command_history = []
        self._last_command_at = now
        stamp = datetime.now().strftime("%A %d %B %Y, %H:%M")
        self._command_history.append({"role": "user", "content": f"[{stamp}] {command}"})
        return self._command_history

    def clean_dictation(self, transcript: str) -> str:
        raise NotImplementedError

    def ask_about_screen(self, question: str, screenshot_b64: str) -> str:
        raise NotImplementedError

    def run_command(self, command: str) -> str:
        raise NotImplementedError


class AnthropicBrain(Brain):
    # With "default", a request Claude's safety checks decline is retried on
    # another model inside the same call instead of failing outright.
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self):
        import anthropic

        super().__init__()
        self.client = anthropic.Anthropic()

    def _create(self, **kwargs):
        return self.client.beta.messages.create(
            max_tokens=16000,
            betas=[self.FALLBACK_BETA],
            fallbacks="default",
            **kwargs,
        )

    @staticmethod
    def _text(response) -> str:
        if response.stop_reason == "refusal":
            return REFUSAL_REPLY
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def clean_dictation(self, transcript: str) -> str:
        response = self._create(
            model=config.model,
            system=DICTATE_SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": transcript}],
        )
        return self._text(response) or transcript

    def ask_about_screen(self, question: str, screenshot_b64: str) -> str:
        response = self._create(
            model=config.vision_model,
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
        messages = self._start_command(command)

        for _ in range(MAX_TOOL_ROUNDS):
            response = self._create(
                model=config.model,
                system=COMMAND_SYSTEM + WEB_SEARCH_HINT,
                output_config={"effort": "medium"},
                tools=ANTHROPIC_TOOLS,
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
                output, failed = _run_tool_safely(block.name, block.input)
                result = {"type": "tool_result", "tool_use_id": block.id, "content": output}
                if failed:
                    result["is_error"] = True
                results.append(result)
            messages.append({"role": "user", "content": results})

        return "That took too many steps, so I stopped."


class OpenAICompatibleBrain(Brain):
    """For NVIDIA, Ollama and any other provider with an OpenAI-style API."""

    def __init__(self):
        from openai import OpenAI

        super().__init__()
        if not config.api_key:
            raise SystemExit(
                f"No API key for provider {config.provider!r}. "
                "Set it in .env (see .env.example)."
            )
        if not config.model:
            raise SystemExit("Set JARVIS_MODEL in .env to the model you want to use.")
        self.client = OpenAI(base_url=config.base_url or None, api_key=config.api_key)

    def _create(self, **kwargs):
        return self.client.chat.completions.create(max_tokens=4096, **kwargs)

    @staticmethod
    def _text(response) -> str:
        message = response.choices[0].message
        if getattr(message, "refusal", None):
            return REFUSAL_REPLY
        return (message.content or "").strip()

    def clean_dictation(self, transcript: str) -> str:
        response = self._create(
            model=config.model,
            messages=[
                {"role": "system", "content": DICTATE_SYSTEM},
                {"role": "user", "content": transcript},
            ],
        )
        return self._text(response) or transcript

    def ask_about_screen(self, question: str, screenshot_b64: str) -> str:
        response = self._create(
            model=config.vision_model,
            messages=[
                {"role": "system", "content": ASK_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                        },
                    ],
                },
            ],
        )
        return self._text(response)

    def run_command(self, command: str) -> str:
        history = self._start_command(command)

        for _ in range(MAX_TOOL_ROUNDS):
            response = self._create(
                model=config.model,
                messages=[{"role": "system", "content": COMMAND_SYSTEM}, *history],
                tools=OPENAI_TOOLS,
            )
            message = response.choices[0].message
            calls = message.tool_calls or []
            if not calls:
                history.append({"role": "assistant", "content": message.content or ""})
                return self._text(response)

            history.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in calls
                    ],
                }
            )
            for call in calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    output = "Failed: the arguments were not valid JSON."
                else:
                    output, _ = _run_tool_safely(call.function.name, args)
                history.append({"role": "tool", "tool_call_id": call.id, "content": output})

        return "That took too many steps, so I stopped."


def make_brain() -> Brain:
    if config.provider == "anthropic":
        return AnthropicBrain()
    return OpenAICompatibleBrain()
