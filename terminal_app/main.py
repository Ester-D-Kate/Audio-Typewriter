import queue
import sys
import time
from pathlib import Path

import keyboard
from dotenv import load_dotenv

if __package__ in (None, ""):
    # Allow running as `python terminal_app/main.py` without -m
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from terminal_app.audio import OverlapAudioManager
    from terminal_app.config import load_config
    from terminal_app.inserter import safe_insert
    from terminal_app.llm_client import GroqLLM, GroqRateLimitError
    from terminal_app.ui import WaveformWindow
else:
    from .audio import OverlapAudioManager
    from .config import load_config
    from .inserter import safe_insert
    from .llm_client import GroqLLM, GroqRateLimitError
    from .ui import WaveformWindow


def ensure_env_loaded() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


def main() -> None:
    ensure_env_loaded()

    cfg = load_config()
    hk_start = cfg.get("hotkeys", {}).get("start", "ctrl+shift+l")
    hk_stop = cfg.get("hotkeys", {}).get("stop", "ctrl+alt+s")
    hk_pause = cfg.get("hotkeys", {}).get("pause", "ctrl+shift+space")
    hk_cancel = cfg.get("hotkeys", {}).get("cancel", "ctrl+shift+esc")
    hk_prompt = cfg.get("hotkeys", {}).get("prompt", "ctrl+shift+alt+p")
    workers = int(cfg.get("transcription", {}).get("workers", 2))
    max_retries = int(cfg.get("transcription", {}).get("max_retries", 3))
    workers = max(2, min(5, workers))  # clamp between 2 and 5

    amplitude_queue: queue.Queue[float] = queue.Queue()
    transcript_path = Path(__file__).parent / "transcripts.log"
    formatted_log_path = Path(__file__).parent / "formatted.log"

    try:
        llm = GroqLLM()
    except Exception as exc:
        print(f"Groq init failed: {exc}")
        sys.exit(1)

    recorder = OverlapAudioManager(
        llm=llm,
        transcript_path=transcript_path,
        amplitude_queue=amplitude_queue,
        max_workers=workers,
        max_retries=max_retries,
    )
    visual = WaveformWindow(
        amplitude_queue,
        width=int(cfg.get("ui", {}).get("width", 360)),
        height=int(cfg.get("ui", {}).get("height", 140)),
    )

    status = {"recording": False, "paused": False, "last_formatted": "", "mode": "transcribe"}

    def start_recording(mode: str = "transcribe") -> None:
        if status["recording"] and status["paused"]:
            recorder.resume()
            status["paused"] = False
            visual.update_status("recording" + (" prompt" if status["mode"] == "prompt" else ""))
            print("Resumed recording")
            return
        if status["recording"]:
            print(f"Already recording ({status['mode']})")
            return
        status["mode"] = mode
        # start() clears old files and transcript automatically
        recorder.start()
        status["recording"] = True
        status["paused"] = False
        label = "recording" if mode == "transcribe" else "recording prompt"
        visual.update_status(label)
        print(f"[hotkey] Recording started in {mode} mode ({hk_stop} to stop)")

    def pause_recording() -> None:
        if not status["recording"]:
            print("Not recording; cannot pause")
            return
        if status["paused"]:
            print("Already paused")
            return
        recorder.pause()
        status["paused"] = True
        visual.update_status("paused")
        print("Recording paused")

    def stop_and_process() -> None:
        if not status["recording"]:
            print("Not recording; ignoring stop")
            return
        print("Stopping and processing...")
        visual.update_status("processing")
        # stop() transcribes all audio sequentially, then returns
        recorder.stop()
        status["recording"] = False
        status["paused"] = False
        mode = status.get("mode", "transcribe")
        raw_text = recorder.read_transcript().strip()
        if not raw_text:
            print("No transcript captured")
            visual.update_status("idle")
            status["mode"] = "transcribe"
            return
        try:
            if mode == "prompt":
                formatted = llm.generate_prompt(raw_text)
            else:
                formatted = llm.format_text(raw_text)
            status["last_formatted"] = formatted
            with open(formatted_log_path, "a", encoding="utf-8") as fh:
                fh.write(formatted + "\n\n")
        except GroqRateLimitError:
            print("All Groq keys are cooling down (rate limited). Please wait ~5 minutes and try again.")
            visual.update_status("idle")
            status["mode"] = "transcribe"
            return
        except Exception as exc:
            msg = str(exc)
            if "network" in msg.lower():
                print("Network error: please check your connection and try again.")
            else:
                print(f"LLM formatting failed: {exc}")
            visual.update_status("idle")
            status["mode"] = "transcribe"
            return
        error = safe_insert(formatted)
        if error:
            print(f"Insert failed: {error}")
        else:
            print("Formatted text inserted at cursor")
        visual.update_status("idle")
        status["mode"] = "transcribe"

    def cancel_all() -> None:
        if not status["recording"] and not status["paused"]:
            print("Nothing to cancel")
            return
        recorder.cancel()
        status["recording"] = False
        status["paused"] = False
        status["mode"] = "transcribe"
        visual.update_status("idle")
        print("Recording and pending transcriptions cancelled; transcript cleared.")

    keyboard.add_hotkey(hk_start, start_recording)
    keyboard.add_hotkey(hk_stop, stop_and_process)
    keyboard.add_hotkey(hk_pause, pause_recording)
    keyboard.add_hotkey(hk_cancel, cancel_all)
    keyboard.add_hotkey(hk_prompt, lambda: start_recording("prompt"))

    visual.callbacks.update(
        {
            "start": start_recording,
            "pause": pause_recording,
            "resume": start_recording,
            "stop": stop_and_process,
            "cancel": cancel_all,
        }
    )
    visual.start()

    print(
        f"Ready. {hk_start} start/resume (transcription), {hk_prompt} start/resume (prompt mode), {hk_pause} pause, {hk_stop} stop & send, {hk_cancel} cancel."
    )
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Exiting...")
        recorder.stop()


if __name__ == "__main__":
    main()