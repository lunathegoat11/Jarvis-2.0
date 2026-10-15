# Jarvis 2.0

Jarvis is a voice assistant that runs on your own computer (Mac, Windows or Linux). On a Mac, hold **right Option**, talk, and let go. Jarvis works out what you want from what you say:

| Say | What happens |
| --- | --- |
| "type ..." or "write ...", e.g. "type see you at six" | **Dictation.** The words after "type" are tidied up (no "um"s, proper punctuation) and typed into whatever text box you're in. |
| Something about your screen, e.g. "what does this error mean?" or "summarise this page" | **Ask.** Jarvis takes a screenshot, answers, and reads the answer out loud. |
| A change to selected text, e.g. "make this more formal", "fix the grammar", "translate this into Spanish" | **Edit.** Jarvis rewrites the text you've selected and puts the new version in its place. ⌘Z brings the old text back. In code editors that copy the whole line when nothing is selected, select the text first. |
| Anything else, e.g. "open a new tab", "play the latest MrBeast video", "check my email" | **Command.** Jarvis does it: opens apps, websites and tabs, searches, controls music and volume, reads your email, and can take over the mouse for tasks that need clicking. It remembers the conversation for 15 minutes, so follow-ups like "now open the second one" work. |

**Talking over Jarvis:** press right Option while Jarvis is talking, thinking or using your screen and it stops straight away and listens to your next request. A quick tap just stops it. Esc stops it too.

A quick tap of right Option is ignored, and so is a hold where you press another key too, so shortcuts keep working. On Windows and Linux, press `Ctrl+Alt+J`, talk, and press it again.

If you'd rather have a separate key for each mode (fn to dictate, right Command to ask, right Option for commands), set `JARVIS_ONE_KEY=0`.

## Download the apps

You don't need Terminal or Python to use Jarvis. GitHub builds the Mac app (`Jarvis.dmg`) and the Android app (`Jarvis.apk`) for you. Open the repository's **Actions** tab, pick **Build Mac app** or **Build Android app**, press **Run workflow**, wait for it to finish (the green tick), then open the run and download the file at the bottom. Pushing a tag like `v2.0.1` builds both and attaches them to a release.

Everyone who installs Jarvis uses their own AI key. The first time the app opens, it asks which AI to use and for the key, and saves it only on that device.

### Android

1. Download **Jarvis-android** from the build and unzip it to get `Jarvis.apk`.
2. Copy it to the phone (email it to yourself, or use a USB cable or Google Drive) and tap it. Android asks you to allow installing apps from this source; say yes. It's "unknown" only because it didn't come from the Play Store.
3. Open Jarvis, pick your AI and paste your key.
4. **Tap the orb to talk.** Tap it again to stop.
5. For Jarvis to open apps and tap for you, open settings (the gear) and turn on **Control the phone**; Android takes you to Accessibility, where you switch Jarvis on. **Floating bubble** puts a Jarvis button over your other apps.

The Android app is close to full control: with the accessibility permission it can open apps, read the screen, tap, type and swipe, so it can carry out things like "play the latest MrBeast video" step by step.

### iPhone

Apple doesn't allow this. iPhones can only install apps from the App Store (or TestFlight, which needs a paid Apple Developer account), there's no way to "download a file that becomes an app", and no app is allowed to control the rest of the phone or draw in the Dynamic Island the way this needs. So there's no iPhone version. On an iPhone you can still use Jarvis through the Mac, or reach it from any browser if you later host it yourself.

### Mac

The Mac app is built by GitHub:

1. Download **Jarvis-mac** from the build and unzip it to get `Jarvis.dmg`.
2. Open the .dmg and drag Jarvis into Applications.
3. The first time, macOS says it can't check the app for malware, because it isn't signed with a paid Apple Developer certificate. Open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to Jarvis.
4. Jarvis asks which AI to use and for your key, saved only on that Mac in `~/.jarvis/.env`.
5. Give **Jarvis** (not Terminal) access to the Microphone, Accessibility, Input Monitoring and Screen Recording in Privacy & Security.

To share either app, send people the file. The repository is private, so others can't download it from GitHub themselves. The Mac app writes what it's doing to `~/.jarvis/jarvis.log`, which is the place to look if something goes wrong.

## TVs, speakers and the smart home

Jarvis finds these on your Wi-Fi by itself:

| Device | What Jarvis can do |
| --- | --- |
| Chromecast, Google TV, Nest speakers | Play, pause, skip, volume, mute, stop |
| Sonos | Play, pause, skip, volume, mute (whole groups follow the main speaker) |
| Roku TVs and sticks | All of the above with the remote's buttons, plus open apps ("open Netflix on the living room TV") and search ("find Stranger Things on the TV") |

Say things like "pause the kitchen speaker", "turn the living room TV up" or "what speakers do I have?". Set `JARVIS_DEVICES=0` to turn this off.

**Home Assistant** connects everything else: lights, plugs, thermostats, locks, Samsung and LG TVs, Apple TV, and Amazon Echo devices. If you use it, make a long-lived access token on your Home Assistant profile page and add:

```
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=your-token
```

Jarvis then passes sentences like "turn off the bedroom lights" or "is the front door locked?" to Home Assistant's Assist.

**Alexa:** Amazon doesn't let other apps control Echo devices directly. Install the **Alexa Media Player** integration in Home Assistant (through HACS) and Jarvis can control Echos through it and make them announce things ("tell the kitchen Echo dinner's ready").

## The notch

On a Mac, Jarvis lives in the notch at the top of the screen. When you hold right Option, a black panel grows out of the notch with a live waveform of your voice. While Jarvis works, the waveform pulses, and a Liquid Glass card drops down underneath showing what it heard and then its reply. Everything slides back into the notch once Jarvis has finished speaking.

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

## The Jarvis app

On a Mac, Jarvis also opens a small window of its own. When nothing is happening it shows a glowing orb of light and threads that slowly turns and breathes; it turns blue and swells with your voice while you talk, spins up while thinking, and ripples while speaking. When Jarvis is busy, the orb moves up and a feed shows what you said, each step it took, and its replies.

The gear button opens settings, which take effect straight away and are remembered:

- **Voice** and **speaking speed**, with a button to hear a sample
- **Speak replies** on or off
- **Tidy up dictation** on or off (off is faster)

Closing the window just hides it. Open it again from the Jarvis icon in the menu bar, which also has Quit. Set `JARVIS_APP=0` to start without the window.

## Using your screen

Ask for something that needs looking and clicking, such as "play the latest MrBeast video" or "turn on dark mode in System Settings", and Jarvis takes over the mouse and keyboard. It takes a screenshot, decides what to do, does it, and looks again, until the task is done. An orange ring shows where it's about to click. Press **Esc** at any time to stop it.

Jarvis won't buy anything, send messages, post, delete things or type passwords unless you asked for exactly that; it stops and tells you instead. Its own notch panel and pointer are hidden from its screenshots.

How well this works depends on the model. Claude is built for it and is the most reliable. Open models on NVIDIA or Ollama can do it too, with a coordinate grid drawn on their screenshots to help them aim, but they miss more often. Screen control uses the vision model (`JARVIS_VISION_MODEL`), which has to support both images and tool calling.

## Voice

Out of the box Jarvis speaks with your computer's built-in voice. For a much more natural one, install Kokoro, a free open-source AI voice that runs on your computer:

```bash
pip install --ignore-requires-python kokoro-onnx
```

(`--ignore-requires-python` is needed on Python 3.14, which Kokoro works with but doesn't list yet.) Restart Jarvis and it switches to Kokoro by itself. The first time, it downloads the voice files (about 350 MB) into `~/.jarvis/kokoro`.

The default is `bm_george`, a British man. Other voices: `bm_daniel`, `bm_lewis` and `bm_fable` (British men), `bf_emma`, `bf_alice`, `bf_isabella` and `bf_lily` (British women), and American voices such as `am_michael`, `am_adam`, `af_heart` and `af_bella`. Set one with `JARVIS_VOICE=bm_lewis`, and the pace with `JARVIS_VOICE_SPEED=1.1`.

To use a built-in Mac voice instead, set `JARVIS_VOICE_ENGINE=system` and, optionally, `JARVIS_VOICE=Daniel`. The best built-in voices are the "Premium" and "Enhanced" ones, which you can download in System Settings → Accessibility → Spoken Content → System Voice → Manage Voices.

## Dictionary

If Jarvis keeps mishearing a name or word, add it to your dictionary: say "add Kai and Brokering to my dictionary", or type the words into Dictionary in the app's settings. Whisper is told to listen for them, and dictation and edits spell them exactly as you wrote them.

Dictation also adapts to the app you're in, so a message in a chat app reads like a chat message and the same words in Mail read like an email.

## Calendar and Reminders

On a Mac, Jarvis uses the Calendar and Reminders apps, so any account you've added there (iCloud, Google, Exchange) works with no extra setup. Try "what's on my calendar today?", "add dentist on Friday at 3pm" or "remind me to call Mum at 6". Before adding a calendar event Jarvis reads the details back and waits for you to say yes. The first time, macOS asks whether Terminal may control Calendar and Reminders; allow it. New events go in the first calendar you can edit, or set `JARVIS_CALENDAR` to a calendar's name.

Repeating events may not show up when Jarvis checks your calendar, because of a limit in how Calendar answers these requests.

## Texting and calling you

Jarvis can send you a text or ring your phone when you ask ("text me the address", "call me in five minutes", "text me when it's done"). Put your number in the app's settings (the gear) under **Your phone number**, or set `JARVIS_MY_NUMBER` in `.env`.

On a Mac this uses **your own** iMessage and FaceTime: a text comes from you, and a call is a FaceTime audio call placed from your Mac to your number, so it rings your phone. Jarvis doesn't get its own number this way. The first time it texts, macOS asks to let Jarvis control Messages — allow it in System Settings > Privacy & Security > Automation.

For Jarvis to have its own separate number that can SMS and call any phone (not just through your Apple ID), set up a free [Twilio](https://www.twilio.com) trial: buy a number, then add to `.env`:

```
TWILIO_SID=ACxxxxxxxx
TWILIO_TOKEN=your-auth-token
TWILIO_FROM=+1your-twilio-number
```

Jarvis then texts and calls through that number. Twilio charges a small amount per message and per minute.

## Email

Jarvis can read your inbox and write emails for you. It never sends anything itself: it opens a filled-in draft in your mail app, and you press Send. Try "check my email", "read the one from Sam", or "reply to Sam saying I'll be there at 6".

To set it up you need an app password, which is a separate password just for Jarvis that you can delete at any time:

- **Gmail:** turn on 2-Step Verification, then make one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
- **iCloud:** make one at [account.apple.com](https://account.apple.com) under Sign-In and Security → App-Specific Passwords.

Then add these lines to `.env`:

```
EMAIL_ADDRESS=you@gmail.com
EMAIL_APP_PASSWORD=abcd efgh ijkl mnop
```

Jarvis reads your mail without marking it as read. Other providers work if they offer IMAP and app passwords; set `EMAIL_IMAP_HOST` if Jarvis doesn't know your provider's server. Outlook.com has moved away from app passwords for this, so it may not work.

## AI providers

Set `JARVIS_PROVIDER` in `.env` to one of these:

| Provider | What you need | Cost | Notes |
| --- | --- | --- | --- |
| `anthropic` (default) | `ANTHROPIC_API_KEY` from [console.anthropic.com](https://console.anthropic.com) | Paid per request | Uses Claude. The only provider with web search in Command mode. |
| `nvidia` | `NVIDIA_API_KEY` from [build.nvidia.com](https://build.nvidia.com) | NVIDIA gives free credits to start; check your account for limits | Uses Llama 4 Maverick for everything. NVIDIA retires models over time, so if a default is gone Jarvis picks a current model at startup and says which. `python -m jarvis models` lists what's on offer. |
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
- `JARVIS_HOLD` chooses the Mac key (default `right_option`). With `JARVIS_ONE_KEY=0`, `JARVIS_DICTATE_HOLD`, `JARVIS_ASK_HOLD` and `JARVIS_COMMAND_HOLD` choose one key per mode instead: `fn`, `right_cmd`, `right_option`, `right_ctrl` or `right_shift`. `JARVIS_HOLD_KEYS=0` switches a Mac to the press-twice hotkeys instead.
- `JARVIS_DICTATE_KEY`, `JARVIS_ASK_KEY`, `JARVIS_COMMAND_KEY` change the press-twice hotkeys, written like `<ctrl>+<shift>+j`.

Notes you save in Command mode go in `~/.jarvis/notes.json`.

## Adding your own commands

Command mode's abilities live in `jarvis/tools.py`. To add one, put a new entry in `TOOLS` (a name, a description the AI reads to decide when to use it, and the inputs it takes) and handle that name in `run_tool`. Jarvis can use it as soon as you restart it.

## Code layout

| File | Job |
| --- | --- |
| `jarvis/main.py` | The dictate / ask / command flow |
| `jarvis/router.py` | Working out dictate / ask / command from what you said |
| `jarvis/hotkeys.py` | Press-twice hotkeys |
| `jarvis/holdkeys.py` | Hold-to-talk keys on a Mac |
| `jarvis/hud.py` | What Jarvis shows while it works; terminal fallback |
| `jarvis/notch.py` | The notch panel and Liquid Glass card (macOS) |
| `jarvis/notch_layout.py` | Where the notch panel and card sit on screen |
| `jarvis/audio.py` | Microphone recording and Whisper transcription |
| `jarvis/brain.py` | Requests to the AI provider (Anthropic, or any OpenAI-compatible API) |
| `jarvis/tools.py` | What the AI can do in Command mode |
| `jarvis/screen.py` | Screenshots, the coordinate grid, mouse and keyboard for screen control |
| `jarvis/mail.py` | Reading email and opening drafts |
| `jarvis/macapps.py` | Calendar and Reminders (Mac) |
| `jarvis/contact.py` | Texting and calling you (iMessage/FaceTime, or Twilio) |
| `jarvis/devices.py` | TVs, speakers, Home Assistant and Alexa |
| `jarvis/setup.py` | First-run setup in the Mac app |
| `packaging/` | Building Jarvis.app and Jarvis.dmg |
| `jarvis/voice.py` | Jarvis's speaking voice, and stripping symbols from what it says |
| `jarvis/app.py`, `jarvis/app.html` | The Jarvis app window, orb and settings |
| `jarvis/prefs.py` | Settings changed in the app |
| `jarvis/models.py` | Picking a model the provider still offers |
| `jarvis/quick.py` | Quick commands that skip the AI |
| `jarvis/desktop.py` | Typing, clipboard, screenshots, speech, opening apps |
| `jarvis/config.py` | Settings |

Run the tests with `pip install pytest && python -m pytest`.
