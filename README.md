# Audio-Typewriter

A hotkey-driven, always-on-top mini audio recorder that streams overlapping mic segments to Groq Whisper, formats the resulting text via Groq chat, and pastes the cleaned prompt at your current cursor. Includes a draggable waveform mini-window for visual feedback.

## Features
- Global hotkeys (no window focus needed): `Ctrl+Shift+L` start recording (transcribe/format), `Ctrl+Shift+Alt+P` start recording in prompt mode (speak a task, it drafts it), `Ctrl+Shift+S` stop + process + paste.
- Overlapping audio capture: new 15s segment every 12s to avoid gaps; each segment transcribed immediately to reduce latency and appended to a rolling log until you stop.
- Groq key rotation: up to 5+ keys picked from env vars beginning with `GROQ_API_KEY`; rate-limited keys are cooled down for 5 minutes before reuse.
- Whisper transcription (Groq `whisper-large-v3-turbo`) and chat formatting (`llama-3.3-70b-versatile`) to clean grammar, structure, and clarity while preserving meaning.
- Cursor injection via clipboard + paste (pyautogui/pyperclip) so output appears at the active cursor location.
- Tiny draggable Tk waveform with Start/Pause/Resume/Stop buttons; stays on top even when the app is not focused.

## Setup
1) Python 3.10+ recommended. Create/activate a venv.
2) Install deps:
   ```bash
   pip install groq sounddevice soundfile numpy keyboard python-dotenv pyautogui pyperclip
   ```
   - Windows: `keyboard` global hotkeys may require admin privileges. Ensure PortAudio-compatible mic input for `sounddevice`.
3) Environment: create `.env` in repo root (or set system env vars). Keys are discovered if their names start with `GROQ_API_KEY`:
   ```env
   GROQ_API_KEY=your_primary_key
   GROQ_API_KEY_ALT_1=your_alt_key
   GROQ_API_KEY_ALT_2=...
   GROQ_API_KEY_ALT_3=...
   GROQ_API_KEY_ALT_4=...
   ```
   Additional keys with the same prefix are picked up automatically.

4) Hotkeys / UI config: edit `config.json` (auto-created default values are baked-in). Example:
```json
{
   "hotkeys": {
      "start": "ctrl+shift+l",
      "stop": "ctrl+alt+s",
      "pause": "ctrl+shift+space",
      "cancel": "ctrl+shift+esc",
      "prompt": "ctrl+shift+alt+p"
   },
   "transcription": {"workers": 2, "max_retries": 3},
   "ui": {"width": 360, "height": 140}
}
```

## Running
From repo root:
```bash
python -m terminal_app.main
```
You’ll see the waveform window appear with Start/Pause/Resume/Stop buttons; hotkeys work globally.

## How it works
- `main.py`: wires hotkeys/UI, lifecycle, and orchestrates record → transcribe → format → paste.
- `audio.py`: manages overlapping `RecordingSegment` threads (15s max, spawned every 12s). Each segment writes a temp WAV, runs Groq Whisper, and appends text to `transcripts.log`. Manual stop ends all segments and transcribes what’s recorded; pause halts scheduling without clearing the log.
- `llm_client.py`: round-robin key selection across all `GROQ_API_KEY*` env vars. On rate-limit-like errors (429/“limit” etc.), the key is cooled down for 5 minutes. Provides `transcribe()`, `format_text()`, and `generate_prompt()` wrappers.
- `inserter.py`: copies formatted text to clipboard and pastes at the active cursor (pyautogui), with a fallback to typing if desired.
- `ui.py`: draggable always-on-top Tk canvas showing bar-style RMS levels, plus Start/Pause/Resume/Stop buttons.
- `config.py`: loads `config.json` or defaults for hotkeys and UI sizing.

## Hotkey flow
1) Start (`Ctrl+Shift+L` by default or UI Start): clear previous transcript, start overlapping capture.
2) Pause (`Ctrl+Shift+Space` or UI Pause): halt new segments; resume with Start/Resume.
3) Stop + Send (`Ctrl+Shift+S` or UI Stop + Send): stop all segments, transcribe in-flight audio, combine transcript, send to Groq chat for formatting (or prompt drafting if you started with `Ctrl+Shift+Alt+P`), copy to clipboard, and paste at the cursor.
4) Cancel (`Ctrl+Shift+Esc` or UI Cancel): stop, discard pending transcription queue, and clear transcript.
5) Prompt-to-Type (`Ctrl+Shift+Alt+P`): start recording in “prompt” mode. Speak the task (e.g., “Draft an apology email about the delay”). When you stop, the transcript is fed to the prompt generator and the draft is pasted at your cursor.

## Notes & limits
- Clipboard-based paste is fastest; the formatted result is first copied, then pasted—so you can re-paste if needed.
- Recording continues indefinitely until you stop; segments roll every 12/15s, are queued in start-time order, and transcribed sequentially by 2–5 workers (configurable) with retries (rate-limit retries back off ~5s, other errors ~1s). Completed transcripts are appended in order before formatting.
- Network failures are surfaced clearly; rate-limited keys auto cool-down for 5 minutes and rotate to the next available key. If all keys are cooling down, you’ll be told to wait and retry.
- Tk window must stay open for visuals; close app with Ctrl+C in the terminal if needed.
- Rate limits: if a key is rate-limited, it is cooled down for 5 minutes and the next key is tried. If all keys are cooling down, you’ll see a message to wait and try again. Groq free-tier doesn’t expose remaining quota, so pre-emptive 90% checks aren’t possible.
