"""Everything that talks to the AI model.

There are two backends: Anthropic's API for Claude, and the OpenAI
chat-completions format, which NVIDIA, Ollama and most other providers
accept. They differ only in how a request and its messages are shaped, so
each backend implements four small methods (_step, _user, _results,
_prune) and the dictate / ask / command / screen-control logic is shared.
make_brain() picks a backend from JARVIS_PROVIDER.
"""

import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from . import config as settings
from .config import config
from .tools import WEB_SEARCH_TOOL, command_tools, run_tool, to_openai

DICTATE_SYSTEM = """\
You clean up dictated speech so it can be pasted straight into a document, \
message or text field. Remove filler words (um, uh, like, you know), false \
starts and repeated words. Fix punctuation, capitalisation and obvious \
transcription mistakes. When the speaker corrects themselves ("at 3, no, \
at 4"), keep only the correction. Keep their wording, tone and meaning; do \
not add content, answer questions in the text, or summarise. Reply with the \
cleaned text only."""

EDIT_SYSTEM = """\
You rewrite a piece of text the user has selected, following their spoken \
instruction (for example "make this more formal", "fix the grammar", \
"translate this into Spanish", "turn this into bullet points"). Keep anything \
the instruction doesn't ask you to change. Reply with only the new text, ready \
to paste in place of the old: no quotes around it and no comments."""

ASK_SYSTEM = """\
You are Jarvis, a voice assistant on the user's computer. The user is asking \
about what is on their screen; a screenshot is attached. Your reply is read \
aloud, so answer in a few plain spoken sentences with no markdown, lists or \
code blocks unless they ask for code."""

COMMAND_SYSTEM = """\
You are Jarvis, a voice assistant that controls the user's computer. The user \
speaks commands; you carry them out with your tools, then say briefly what you \
did. Your reply is read aloud, so keep it to one or two plain sentences with no \
markdown. You can open apps, websites and browser tabs, search the web in the \
browser, press keyboard shortcuts, control music and volume, type text, read \
the clipboard, and save or read notes. When email tools are available you can \
check and read the user's email and open drafts for them to send; you can't \
send email yourself. On a Mac you can check the calendar, add events (always \
read the details back and wait for a yes first) and add reminders. You can \
text and call the user's own phone. Usually that's when they ask, but you may \
also do it on your own when something genuinely urgent or time-sensitive comes \
up while you're helping (a deadline in minutes, a reply that needs them now, \
something that can't wait until they next look at the screen). Text by default; \
only call for something that truly can't wait. Don't contact them for ordinary \
or routine things, and never more than once for the same thing. You can control TVs and \
speakers on the Wi-Fi by name (list_devices shows them), and \
the smart home and Alexa through Home Assistant when it's connected. When a \
task needs looking at the screen and clicking \
(finding and playing a particular video, working through a website or app), \
use use_screen with the whole task. Use several tools in a row when a request \
needs it. If a request is unclear or no tool can do it, say so rather than \
guessing."""

WEB_SEARCH_HINT = " Search the web when a question needs current information."

SCREEN_SYSTEM = """\
You control the user's computer by looking at screenshots and using the mouse \
and keyboard, to finish the task you're given. Each screenshot is scaled down; \
always give coordinates in that screenshot's pixels. {grid}\

Work in small steps: do one or two actions, then look at the new screenshot \
before going on. Click the middle of what you're aiming at. Prefer open_url \
when you know the web address (for a YouTube channel's newest videos, open \
https://www.youtube.com/@ChannelName/videos). Before each action, say in a few \
words what you're doing; the user sees it.

Don't buy anything, send messages or email, post, delete things, change \
passwords or accept terms unless the task explicitly asks for exactly that. \
If you need a password or the task looks risky, call done and say why. When \
the task is finished, or you're stuck after a few tries, call done with a \
one-sentence summary."""

GRID_HINT = (
    "A faint magenta grid is drawn every 100 pixels with its coordinates "
    "labelled along the top and left edges; use it to read positions."
)

REFUSAL_REPLY = "Sorry, I can't help with that one."
EMPTY_REPLY = "I didn't get an answer back from the AI. Try again, or try a different model."

# Command-mode conversations are forgotten after this much idle time.
COMMAND_MEMORY_SECONDS = 15 * 60

# A model that keeps calling tools without finishing gets stopped here.
MAX_TOOL_ROUNDS = 10

# Screen control keeps this many of the latest screenshots in the
# conversation for providers where old ones are trimmed.
KEEP_SCREENSHOTS = 2


@dataclass
class Call:
    id: str
    name: str
    args: dict | None  # None when the model's arguments weren't valid JSON


@dataclass
class Step:
    """One reply from the model, in a provider-neutral shape."""

    text: str
    calls: list[Call]
    assistant: dict  # the reply as a message to add to the conversation
    paused: bool = False
    refused: bool = False


def _run_tool_safely(name: str, args: dict) -> tuple[str, bool]:
    """Returns (output, failed)."""
    try:
        return run_tool(name, args), False
    except Exception as error:
        return f"Failed: {error}", True


class _QuietHUD:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class Brain:
    model: str
    vision_model: str

    def __init__(self):
        self._command_history: list = []
        self._last_command_at = 0.0
        self.hud = _QuietHUD()
        # Set (by pressing Esc) to stop screen control between steps.
        self.stop_event = threading.Event()
        # Bumped by cancel(); work started under an older number stops.
        self._generation = 0
        self._turn_start = 0

    def cancel(self) -> None:
        """Abandons whatever is in progress, e.g. when the user interrupts.

        A request that's waiting on the AI can't be pulled back, so its
        thread is left to finish on its own; it works on a conversation list
        that's no longer used, and any screen control stops at its next step.
        """
        self._generation += 1
        self.stop_event.set()
        # Keep the finished turns; drop the one that was cut off.
        self._command_history = list(self._command_history[: self._turn_start])

    def attach(self, hud) -> None:
        self.hud = hud

    # ---- what each backend provides -----------------------------------------

    def _step(self, system: str, messages: list, tools: list, model: str, effort: str) -> Step:
        raise NotImplementedError

    def _user(self, text: str, image_b64: str | None = None) -> list:
        raise NotImplementedError

    def _results(self, results: list[tuple[Call, str, bool]], image_b64=None, note="") -> list:
        raise NotImplementedError

    def _prune(self, messages: list) -> None:
        """Drops old screenshots where the provider needs it. Default: keep all."""

    def _command_tools(self) -> list:
        return command_tools(can_see_screen=bool(self.vision_model))

    def _command_system(self) -> str:
        return COMMAND_SYSTEM

    # ---- shared behaviour ---------------------------------------------------

    def _start_command(self, command: str) -> list:
        """Returns the command history with the new command added."""
        now = time.monotonic()
        if now - self._last_command_at > COMMAND_MEMORY_SECONDS:
            self._command_history = []
        self._last_command_at = now
        self._turn_start = len(self._command_history)
        stamp = datetime.now().strftime("%A %d %B %Y, %H:%M")
        self._command_history.extend(self._user(f"[{stamp}] {command}"))
        return self._command_history

    @staticmethod
    def _context(app: str = "", vocabulary: str = "") -> str:
        notes = ""
        if app:
            notes += (
                f"\n\nThe text is going into {app}. Format it the way people write "
                "there (a chat message reads differently from an email or a document), "
                "without changing what the speaker said."
            )
        if vocabulary:
            notes += f"\n\nSpell these names and terms exactly like this: {vocabulary}."
        return notes

    def clean_dictation(self, transcript: str, app: str = "", vocabulary: str = "") -> str:
        system = DICTATE_SYSTEM + self._context(app, vocabulary)
        step = self._step(system, self._user(transcript), [], self.model, "low")
        if step.refused:
            return transcript
        return step.text or transcript

    def edit_text(self, instruction: str, text: str, app: str = "", vocabulary: str = "") -> str:
        system = EDIT_SYSTEM + self._context(app, vocabulary)
        prompt = f"Instruction: {instruction}\n\nSelected text:\n{text}"
        step = self._step(system, self._user(prompt), [], self.model, "low")
        if step.refused or not step.text:
            raise RuntimeError("The AI didn't send back a rewrite.")
        return step.text

    def ask_about_screen(self, question: str, screenshot_b64: str) -> str:
        step = self._step(
            ASK_SYSTEM, self._user(question, screenshot_b64), [], self.vision_model, "medium"
        )
        if step.refused:
            return REFUSAL_REPLY
        return step.text or EMPTY_REPLY

    def _run_command_tool(self, call: Call) -> tuple[str, bool]:
        if call.args is None:
            return "Failed: the arguments were not valid JSON.", True
        if call.name == "look_at_screen":
            from . import desktop

            try:
                shot = desktop.screenshot_png_base64(config.screenshot_width)
                return self.ask_about_screen(call.args["question"], shot), False
            except Exception as error:
                return f"Failed: {error}", True
        if call.name == "use_screen":
            try:
                return self.operate(call.args["task"]), False
            except Exception as error:
                return f"Failed: {error}", True
        return _run_tool_safely(call.name, call.args)

    def run_command(self, command: str) -> str:
        history = self._start_command(command)
        tools = self._command_tools()

        for _ in range(MAX_TOOL_ROUNDS):
            step = self._step(self._command_system(), history, tools, self.model, "medium")
            history.append(step.assistant)
            if step.paused:
                continue
            if step.refused:
                return REFUSAL_REPLY
            if not step.calls:
                return step.text or EMPTY_REPLY
            results = [(call, *self._run_command_tool(call)) for call in step.calls]
            history.extend(self._results(results))

        return "That took too many steps, so I stopped."

    def operate(self, task: str) -> str:
        """Screen control: look, act, look again, until the task is done."""
        from . import screen

        self.stop_event.clear()
        mine = self._generation

        def stopped() -> bool:
            return self.stop_event.is_set() or self._generation != mine

        system = SCREEN_SYSTEM.format(grid=GRID_HINT if config.screen_grid else "")
        self.hud.status("Working on it", task)
        shot = screen.capture(config.screen_control_width)
        messages = self._user(
            f"Task: {task}\nThis screenshot is {shot.width}x{shot.height} pixels.", shot.png_b64
        )
        try:
            for _ in range(config.max_screen_steps):
                if stopped():
                    return "Stopped."
                self._prune(messages)
                step = self._step(system, messages, screen.SCREEN_TOOLS, self.vision_model, "low")
                messages.append(step.assistant)
                if step.paused:
                    continue
                if step.refused:
                    return REFUSAL_REPLY
                if step.text:
                    self.hud.status("Working on it", step.text)
                if not step.calls:
                    return step.text or "I couldn't finish that."

                results = []
                for call in step.calls:
                    if call.name == "done" and call.args is not None:
                        return call.args.get("summary") or "Done."
                    if call.args is None:
                        results.append((call, "Failed: the arguments were not valid JSON.", True))
                    elif stopped():
                        results.append((call, "Skipped: the user stopped the task.", True))
                    else:
                        try:
                            output = screen.run_screen_tool(call.name, call.args, shot, self.hud)
                            results.append((call, output, False))
                        except Exception as error:
                            results.append((call, f"Failed: {error}", True))

                time.sleep(0.6)  # let the page react before looking again
                shot = screen.capture(config.screen_control_width)
                messages.extend(
                    self._results(
                        results,
                        shot.png_b64,
                        f"The screen now ({shot.width}x{shot.height} pixels).",
                    )
                )
            return "That took too many steps, so I stopped."
        finally:
            self.hud.pointer_hide()


class AnthropicBrain(Brain):
    # With "default", a request Claude's safety checks decline is retried on
    # another model inside the same call instead of failing outright.
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self):
        import os

        import anthropic

        super().__init__()
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise SystemExit(
                f"Jarvis is set to use Claude, but there's no ANTHROPIC_API_KEY in {settings.ENV_FILE}.\n"
                "To use Ollama instead, put JARVIS_PROVIDER=ollama and JARVIS_MODEL=<model> in that file."
            )
        self.client = anthropic.Anthropic()
        self.model = config.model
        self.vision_model = config.vision_model

    def _create(self, **kwargs):
        return self.client.beta.messages.create(
            max_tokens=16000,
            betas=[self.FALLBACK_BETA],
            fallbacks="default",
            **kwargs,
        )

    def _command_tools(self) -> list:
        return super()._command_tools() + [WEB_SEARCH_TOOL]

    def _command_system(self) -> str:
        return COMMAND_SYSTEM + WEB_SEARCH_HINT

    def _step(self, system, messages, tools, model, effort) -> Step:
        kwargs = {}
        if tools:
            kwargs["tools"] = tools
        response = self._create(
            model=model,
            system=system,
            output_config={"effort": effort},
            messages=messages,
            **kwargs,
        )
        return Step(
            text="".join(b.text for b in response.content if b.type == "text").strip(),
            calls=[Call(b.id, b.name, b.input) for b in response.content if b.type == "tool_use"],
            # Keep the whole content list (thinking and tool blocks included);
            # the API expects it back unchanged on the next request.
            assistant={"role": "assistant", "content": response.content},
            paused=response.stop_reason == "pause_turn",
            refused=response.stop_reason == "refusal",
        )

    @staticmethod
    def _image(image_b64: str) -> dict:
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
        }

    def _user(self, text, image_b64=None) -> list:
        if image_b64 is None:
            return [{"role": "user", "content": text}]
        return [{"role": "user", "content": [self._image(image_b64), {"type": "text", "text": text}]}]

    def _results(self, results, image_b64=None, note="") -> list:
        content = []
        for call, output, failed in results:
            block = {"type": "tool_result", "tool_use_id": call.id, "content": output}
            if failed:
                block["is_error"] = True
            content.append(block)
        if image_b64 is not None:
            content += [self._image(image_b64), {"type": "text", "text": note}]
        return [{"role": "user", "content": content}]


THINK_TAGS = re.compile(r"<think>.*?</think>", re.DOTALL)


class OpenAICompatibleBrain(Brain):
    """For NVIDIA, Ollama and any other provider with an OpenAI-style API."""

    def __init__(self):
        from openai import OpenAI

        super().__init__()
        if not config.api_key:
            raise SystemExit(
                f"No API key for provider {config.provider!r}. "
                f"Set it in {settings.ENV_FILE} (see .env.example)."
            )
        if not config.model:
            raise SystemExit("Set JARVIS_MODEL in .env to the model you want to use.")
        self.client = OpenAI(base_url=config.base_url or None, api_key=config.api_key)
        # Thinking models (Gemma 4, Nemotron, Qwen 3...) reason silently
        # before every answer. That makes a voice assistant slow, and on some
        # servers the thinking uses up the whole reply so nothing comes back.
        self._thinking_off = {} if config.thinking else self.THINKING_OFF.get(config.provider, {})
        self.model = config.model
        self.vision_model = config.vision_model
        self._check_models()

    # How each provider is asked to skip thinking.
    THINKING_OFF = {
        "ollama": {"reasoning_effort": "none"},
        "nvidia": {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
    }

    def _check_models(self):
        """Swaps retired default models for ones the provider offers today."""
        from .models import PREFERENCES, list_models, pick

        try:
            available = list_models(self.client)
        except Exception:
            return  # can't tell; try the configured models anyway
        if not available:
            return
        preferences = PREFERENCES.get(config.provider, {})

        if self.model not in available:
            replacement = None if config.model_chosen else pick(available, preferences.get("text", []))
            if replacement:
                print(f"{self.model} isn't offered any more; using {replacement} instead.")
                self.model = replacement
            else:
                print(
                    f"Warning: {config.provider} doesn't list {self.model}. "
                    "Run `python -m jarvis models` to see what it offers."
                )
        if self.vision_model not in available:
            replacement = (
                None if config.vision_model_chosen else pick(available, preferences.get("vision", []))
            )
            if replacement:
                print(f"{self.vision_model} isn't offered any more; Ask mode will use {replacement}.")
                self.vision_model = replacement

    def _create(self, **kwargs):
        if self._thinking_off:
            from openai import BadRequestError

            try:
                return self.client.chat.completions.create(
                    max_tokens=8192, **self._thinking_off, **kwargs
                )
            except BadRequestError:
                # This server or model rejects the setting; carry on without it.
                self._thinking_off = {}
        return self.client.chat.completions.create(max_tokens=8192, **kwargs)

    def _step(self, system, messages, tools, model, effort) -> Step:
        kwargs = {}
        if tools:
            kwargs["tools"] = to_openai(tools)
        response = self._create(
            model=model,
            messages=[{"role": "system", "content": system}, *messages],
            **kwargs,
        )
        message = response.choices[0].message
        text = THINK_TAGS.sub("", message.content or "").strip()

        calls = []
        for tool_call in message.tool_calls or []:
            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = None
            calls.append(Call(tool_call.id, tool_call.function.name, args))

        assistant = {"role": "assistant", "content": message.content or ""}
        if calls:
            assistant["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in message.tool_calls
            ]
        return Step(
            text=text,
            calls=calls,
            assistant=assistant,
            refused=bool(getattr(message, "refusal", None)),
        )

    @staticmethod
    def _image(image_b64: str) -> dict:
        return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}

    def _user(self, text, image_b64=None) -> list:
        if image_b64 is None:
            return [{"role": "user", "content": text}]
        return [{"role": "user", "content": [{"type": "text", "text": text}, self._image(image_b64)]}]

    def _results(self, results, image_b64=None, note="") -> list:
        messages = [
            {"role": "tool", "tool_call_id": call.id, "content": output}
            for call, output, _ in results
        ]
        # Tool messages can't carry images here, so the new screenshot goes
        # in a user message after them.
        if image_b64 is not None:
            messages += self._user(note, image_b64)
        return messages

    def _prune(self, messages: list) -> None:
        """Keeps only the latest screenshots; open models have small contexts."""
        seen = 0
        for message in reversed(messages):
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            if any(part.get("type") == "image_url" for part in content):
                seen += 1
                if seen > KEEP_SCREENSHOTS:
                    message["content"] = [
                        part if part.get("type") != "image_url"
                        else {"type": "text", "text": "[older screenshot removed]"}
                        for part in content
                    ]


def make_brain() -> Brain:
    if config.provider == "anthropic":
        return AnthropicBrain()
    return OpenAICompatibleBrain()
