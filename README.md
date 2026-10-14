# Jarvis 2.0

Jarvis is a voice assistant that runs on your own computer (Mac, Windows or Linux). Press a hotkey, talk, press it again, and Jarvis does one of three things depending on which hotkey you used.

| Hotkey | Mode | What happens |
| --- | --- | --- |
| `Ctrl+Alt+D` | Dictate | Your speech is cleaned up (no "um"s, proper punctuation, self-corrections applied) and typed into whatever text box you're in. |
| `Ctrl+Alt+A` | Ask | Jarvis takes a screenshot, answers your question about it, and reads the answer out loud. "What does this error mean?" works well. |
| `Ctrl+Alt+J` | Command | Jarvis acts on what you say: opens apps and websites, types for you, reads your clipboard, saves and reads back notes, and searches the web. It remembers the conversation for 15 minutes, so follow-ups like "now open the second one" work. |

Speech-to-text runs locally with [Whisper](https://github.com/SYSTRAN/faster-whisper), so your voice recordings stay on your computer. The text Jarvis heard, and the screenshot in Ask mode, are sent to Claude.

## What it costs

The code is yours and free. Claude is a paid API, billed per request through your own [Anthropic Console](https://console.anthropic.com) account. Dictation and short commands are cheap; Ask mode costs more because it sends an image. You can set a monthly spending limit in the Console.

## Setup

You need Python 3.10 or newer.

```bash
git clone https://github.com/lunathegoat11/Jarvis-2.0.git
cd Jarvis-2.0
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

Open `.env` and paste your API key after `ANTHROPIC_API_KEY=`.

Then start it:

```bash
python -m jarvis
```

The first time you use a hotkey, Whisper downloads its speech model (about 150 MB for `base.en`), so the first transcription is slow.

### Mac permissions

macOS will block the hotkeys, typing and screenshots until you allow them. In System Settings → Privacy & Security, give your terminal app (Terminal, iTerm, or VS Code) access under **Microphone**, **Accessibility**, **Input Monitoring** and **Screen Recording**, then restart the terminal.

### Linux notes

Install PortAudio and a clipboard tool first: `sudo apt install libportaudio2 xclip espeak`. Global hotkeys and typing need an X11 session; under Wayland they may not work.

## Settings

Everything is set in `.env`; see `.env.example` for the full list. The common ones:

- `JARVIS_WHISPER_MODEL`: `tiny.en` is faster, `small.en` hears you more accurately.
- `JARVIS_SPEAK=0` turns off reading replies aloud. Replies still show as notifications and in the terminal.
- `JARVIS_DICTATE_KEY`, `JARVIS_ASK_KEY`, `JARVIS_COMMAND_KEY` change the hotkeys, written like `<ctrl>+<shift>+j`.

Notes you save in Command mode go in `~/.jarvis/notes.json`.

## Adding your own commands

Command mode's abilities live in `jarvis/tools.py`. To add one, put a new entry in `TOOLS` (a name, a description Claude reads to decide when to use it, and the inputs it takes) and handle that name in `run_tool`. Claude starts using it as soon as you restart Jarvis.

## Code layout

| File | Job |
| --- | --- |
| `jarvis/main.py` | Hotkeys and the dictate / ask / command flow |
| `jarvis/audio.py` | Microphone recording and Whisper transcription |
| `jarvis/brain.py` | Requests to Claude |
| `jarvis/tools.py` | What Command mode can do |
| `jarvis/desktop.py` | Typing, clipboard, screenshots, speech, opening apps |
| `jarvis/config.py` | Settings |

Run the tests with `pip install pytest && python -m pytest`.
