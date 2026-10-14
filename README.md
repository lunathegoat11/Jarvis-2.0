# Jarvis 2.0

Jarvis is a voice assistant that runs on your own computer (Mac, Windows or Linux). Press a hotkey, talk, press it again, and Jarvis does one of three things depending on which hotkey you used.

| Hotkey | Mode | What happens |
| --- | --- | --- |
| `Ctrl+Alt+D` | Dictate | Your speech is cleaned up (no "um"s, proper punctuation, self-corrections applied) and typed into whatever text box you're in. |
| `Ctrl+Alt+A` | Ask | Jarvis takes a screenshot, answers your question about it, and reads the answer out loud. "What does this error mean?" works well. |
| `Ctrl+Alt+J` | Command | Jarvis acts on what you say: opens apps, websites and browser tabs, searches, presses keyboard shortcuts, controls music and volume, types for you, reads your clipboard, and saves and reads back notes. It remembers the conversation for 15 minutes, so follow-ups like "now open the second one" work. |

On a Mac, `Alt` is the Option key.

## The notch

On a Mac, Jarvis lives in the notch at the top of the screen. When you press a hotkey, a black panel grows out of the notch with a live waveform of your voice and the mode you're in (blue for Dictate, purple for Ask, orange for Command). While Jarvis works, the waveform pulses, and a Liquid Glass card drops down underneath showing what it heard and then its reply. Everything slides back into the notch once Jarvis has finished speaking.

Liquid Glass needs macOS 26 (Tahoe) or newer. On older macOS the card uses the frosted blur from earlier versions instead. On Macs without a notch, or on an external display, the panel appears as a small pill at the top centre of the screen. Set `JARVIS_NOTCH=0` to turn the panel off and use the terminal and notifications instead.

Speech-to-text runs locally with [Whisper](https://github.com/SYSTRAN/faster-whisper), so your voice recordings stay on your computer. The text Jarvis heard, and the screenshot in Ask mode, go to whichever AI provider you choose.

## Quick commands

These everyday commands run straight away, without waiting for the AI:

| Say | What happens |
| --- | --- |
| "new tab", "close tab", "reopen tab", "next tab", "previous tab" | Browser tabs (your browser needs to be in front) |
| "go back", "go forward", "refresh" | Browser navigation |
| "open YouTube", "go to bbc.co.uk" | Opens the website |
| "open Spotify", "launch Notes" | Opens the app |
| "search for ...", "search YouTube for ...", "play ... on YouTube" | Opens the search in your browser |
| "pause", "play", "next song", "previous song" | Music and video |
| "volume up", "volume down", "set volume to 40", "mute", "unmute" | Volume |
| "what time is it", "what's the date" | Tells you |
| "remember that ...", "read my notes" | Saves or reads notes |

Anything else, such as "open a new tab and go to Gmail", goes to the AI, which has the same abilities plus typing and reading the clipboard, and can chain several steps together. Quick commands are in `jarvis/quick.py` if you want to add your own.

## AI providers

Set `JARVIS_PROVIDER` in `.env` to one of these:

| Provider | What you need | Cost | Notes |
| --- | --- | --- | --- |
| `anthropic` (default) | `ANTHROPIC_API_KEY` from [console.anthropic.com](https://console.anthropic.com) | Paid per request | Uses Claude. The only provider with web search in Command mode. |
| `nvidia` | `NVIDIA_API_KEY` from [build.nvidia.com](https://build.nvidia.com) | NVIDIA gives free credits to start; check your account for limits | Uses Llama 3.3 70B for dictation and commands, and Llama 3.2 90B Vision for Ask mode. |
| `ollama` | [Ollama](https://ollama.com) installed and a model downloaded | Free; runs on your computer | Nothing leaves your computer. Set `JARVIS_MODEL` to the model's name exactly as `ollama list` shows it. |
| `custom` | `JARVIS_BASE_URL`, `JARVIS_API_KEY` and `JARVIS_MODEL` | Depends on the service | For any other service with an OpenAI-compatible API, such as OpenRouter, Groq, Together or LM Studio. |

To use a different model from the same provider, set `JARVIS_MODEL`; Ask mode then uses the same model. Ask mode needs a model that can read images, so if yours can't, set `JARVIS_VISION_MODEL` to one that can.

Command mode depends on the model being good at tool calling. Large models handle it well. Small local models sometimes pick the wrong tool or answer without acting, so if commands misbehave on Ollama, try a bigger model such as `llama3.1:70b` or `qwen2.5:14b`.

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

Open `.env`, set `JARVIS_PROVIDER`, and fill in what that provider needs (see the table above). For Ollama, for example, run `ollama list` to get your model's exact name, then:

```
JARVIS_PROVIDER=ollama
JARVIS_MODEL=the-name-from-ollama-list
```

Keep the Ollama app open while you use Jarvis.

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
- `JARVIS_SPEAK=0` turns off reading replies aloud. Replies stay on screen for a few seconds instead.
- `JARVIS_NOTCH=0` turns off the notch panel on a Mac.
- `JARVIS_THINKING=1` lets Ollama models think before answering. It's off by default because it makes replies much slower.
- `JARVIS_CLEAN_DICTATION=0` pastes what Whisper heard without asking the AI to tidy it. Dictation gets much faster on local models, but "um"s and false starts stay in.
- `JARVIS_SCREENSHOT_WIDTH` sets how big Ask mode's screenshot is. Local models are much quicker with smaller images; the default is 1024 for them and 1568 for Claude.

### Speed on Ollama

Local models run on your Mac's GPU, so it sits near 100% while Jarvis thinks. If replies are slow, try a smaller model. Gemma 4's `e4b` and `e2b` sizes respond noticeably faster than `12b` and can still read images: run `ollama pull gemma4:e4b`, then set `JARVIS_MODEL=gemma4:e4b`. Ollama also unloads a model after five idle minutes, which makes the next request slow while it reloads. To keep it loaded for an hour, run `launchctl setenv OLLAMA_KEEP_ALIVE 1h` and restart the Ollama app.
- `JARVIS_DICTATE_KEY`, `JARVIS_ASK_KEY`, `JARVIS_COMMAND_KEY` change the hotkeys, written like `<ctrl>+<shift>+j`.

Notes you save in Command mode go in `~/.jarvis/notes.json`.

## Adding your own commands

Command mode's abilities live in `jarvis/tools.py`. To add one, put a new entry in `TOOLS` (a name, a description the AI reads to decide when to use it, and the inputs it takes) and handle that name in `run_tool`. Jarvis can use it as soon as you restart it.

## Code layout

| File | Job |
| --- | --- |
| `jarvis/main.py` | The dictate / ask / command flow |
| `jarvis/hotkeys.py` | Global hotkeys |
| `jarvis/hud.py` | What Jarvis shows while it works; terminal fallback |
| `jarvis/notch.py` | The notch panel and Liquid Glass card (macOS) |
| `jarvis/notch_layout.py` | Where the notch panel and card sit on screen |
| `jarvis/audio.py` | Microphone recording and Whisper transcription |
| `jarvis/brain.py` | Requests to the AI provider (Anthropic, or any OpenAI-compatible API) |
| `jarvis/tools.py` | What the AI can do in Command mode |
| `jarvis/quick.py` | Quick commands that skip the AI |
| `jarvis/desktop.py` | Typing, clipboard, screenshots, speech, opening apps |
| `jarvis/config.py` | Settings |

Run the tests with `pip install pytest && python -m pytest`.
