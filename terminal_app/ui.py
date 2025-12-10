import math
import queue
import threading
import tkinter as tk
from typing import Callable, Dict, Optional


class WaveformWindow:
    def __init__(
        self,
        amplitude_queue: "queue.Queue[float]",
        width: int = 360,
        height: int = 180,
        callbacks: Optional[Dict[str, Callable[[], None]]] = None,
    ) -> None:
        self.queue = amplitude_queue
        self.width = width
        self.height = height
        self.callbacks = callbacks or {}
        self._running = False
        self._thread: threading.Thread | None = None
        self.root: tk.Tk | None = None
        self._status = "idle"
        self._status_lock = threading.Lock()
        self._buttons: Dict[str, tk.Button] = {}
        self._phase = 0.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def update_status(self, text: str) -> None:
        with self._status_lock:
            self._status = text
        mode_key = text.split(" ")[0] if text else "idle"
        if hasattr(self, "status_label"):
            self._set_mode_colors(mode_key)

    def _run(self) -> None:
        self.root = tk.Tk()
        self.root.title("Audio Visual")
        self.root.geometry(f"{self.width}x{self.height}+40+40")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#050910")
        self.root.overrideredirect(True)

        shell = tk.Frame(self.root, bg="#050910", padx=8, pady=8)
        shell.pack(fill=tk.BOTH, expand=True)

        chrome = tk.Frame(shell, bg="#0c1624", highlightthickness=0, bd=0)
        chrome.pack(fill=tk.BOTH, expand=True)
        chrome.pack_propagate(False)

        # Header / controls
        header = tk.Frame(chrome, bg="#0c1624", padx=12, pady=10)
        header.pack(fill=tk.X)
        title = tk.Label(
            header,
            text="Audio-Typewriter",
            fg="#e9f0ff",
            bg="#0c1624",
            font=("Segoe UI", 12, "bold"),
        )
        title.pack(side=tk.LEFT)

        # Icon-style buttons with hover/active feedback
        pill = {"bd": 0, "highlightthickness": 0}
        controls = tk.Frame(chrome, bg="#0c1624", padx=10, pady=8, **pill)
        controls.pack(fill=tk.X)
        noop = lambda: None
        self._buttons["start"] = self._make_icon_button(controls, "⏺", self.callbacks.get("start", noop))
        self._buttons["pause"] = self._make_icon_button(controls, "⏸", self.callbacks.get("pause", noop))
        self._buttons["resume"] = self._make_icon_button(controls, "▶", self.callbacks.get("resume", noop))
        self._buttons["stop"] = self._make_icon_button(controls, "⏹", self.callbacks.get("stop", noop))
        self._buttons["cancel"] = self._make_icon_button(controls, "✖", self.callbacks.get("cancel", noop))

        status_frame = tk.Frame(chrome, bg="#0c1624")
        status_frame.pack(fill=tk.X, padx=12, pady=(2, 6))
        self.status_label = tk.Label(
            status_frame,
            text="idle",
            fg="#c8d6e8",
            bg="#122033",
            anchor="w",
            padx=10,
            pady=6,
            font=("Segoe UI", 10, "bold"),
        )
        self.status_label.pack(fill=tk.X)

        self.canvas = tk.Canvas(chrome, width=self.width, height=self.height - 90, bg="#0c1624", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

        self._enable_drag()
        self._tick()
        self.root.mainloop()

    def _make_icon_button(self, parent: tk.Widget, text: str, command: Callable[[], None]) -> tk.Button:
        base = {
            "bg": "#122033",
            "fg": "#e9f0ff",
            "activebackground": "#1b2d44",
            "activeforeground": "#e9f0ff",
            "bd": 0,
            "padx": 12,
            "pady": 12,
            "font": ("Segoe UI Symbol", 12, "bold"),
            "relief": tk.FLAT,
            "highlightthickness": 0,
        }

        btn = tk.Button(parent, text=text, command=command, **base)
        btn.pack(side=tk.LEFT, padx=4)

        def on_enter(_):
            btn.configure(bg="#1b2d44")

        def on_leave(_):
            btn.configure(bg="#122033")

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    def _enable_drag(self) -> None:
        assert self.root
        self._drag_data: dict[str, int] = {"x": 0, "y": 0}

        def start(event: tk.Event) -> None:
            self._drag_data["x"] = event.x
            self._drag_data["y"] = event.y

        def drag(event: tk.Event) -> None:
            x = event.x_root - self._drag_data["x"]
            y = event.y_root - self._drag_data["y"]
            self.root.geometry(f"+{x}+{y}")

        self.root.bind("<ButtonPress-1>", start)
        self.root.bind("<B1-Motion>", drag)

    def _mix_color(self, c1: str, c2: str, t: float) -> str:
        t = max(0.0, min(1.0, t))
        def to_rgb(hex_color: str) -> tuple[int, int, int]:
            return tuple(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))

        def to_hex(rgb: tuple[int, int, int]) -> str:
            return "#" + "".join(f"{min(255, max(0, v)):02x}" for v in rgb)

        a = to_rgb(c1)
        b = to_rgb(c2)
        mixed = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
        return to_hex(mixed)

    def _draw_background(self, pulse: float) -> None:
        if not hasattr(self, "canvas"):
            return
        base = self._mix_color("#0b1420", "#0f1d30", 0.35 + 0.25 * pulse)
        glow_x = (self._phase * 90) % (self.width + 140) - 140
        self.canvas.create_rectangle(0, 0, self.width, self.height, fill=base, outline="")
        self.canvas.create_rectangle(glow_x, 0, glow_x + 140, self.height, fill="#1a2f46", outline="")

    def _tick(self) -> None:
        if not self.root:
            return
        amplitudes = []
        while not self.queue.empty():
            try:
                amplitudes.append(float(self.queue.get_nowait()))
            except queue.Empty:
                break
        level = max(amplitudes) if amplitudes else 0.0
        self._draw(level)
        with self._status_lock:
            current_status = self._status
        if hasattr(self, "status_label"):
            self.status_label.config(text=current_status)
        self.root.after(50, self._tick)

    def _draw(self, level: float) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        self._phase = (self._phase + 0.14) % (2 * math.pi)
        level = max(0.0, min(level, 1.0))
        pulse = 0.55 + 0.45 * math.sin(self._phase)
        baseline = 0.08
        effective = max(level, baseline)
        bar_count = 28
        bar_width = self.width / bar_count

        self._draw_background(pulse)

        for i in range(bar_count):
            scale = effective * (0.35 + 0.65 * (i / bar_count))
            h = scale * (self.height - 90)
            x0 = i * bar_width + 3
            y0 = (self.height - 90) - h
            x1 = x0 + bar_width - 6
            y1 = (self.height - 90) - 4
            shade = 0.55 + 0.45 * math.sin(self._phase + i * 0.35)
            color = self._mix_color("#3aa0ff", "#7ae1ff", shade)
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

    def _set_mode_colors(self, mode: str) -> None:
        palette = {
            "idle": ("#c8d6e8", "#122033"),
            "recording": ("#ffd166", "#2d1f0f"),
            "paused": ("#8cd3ff", "#102235"),
            "processing": ("#7ae1ff", "#0f1d2d"),
        }
        fg, bg = palette.get(mode, ("#9fb3c8", "#1b222d"))
        self.status_label.configure(fg=fg, bg=bg)

        def tint(btn: Optional[tk.Button], active_color: str) -> None:
            if not btn:
                return
            btn.configure(bg=active_color)

        # reset all
        for btn in self._buttons.values():
            btn.configure(bg="#1b222d")

        if mode.startswith("recording"):
            tint(self._buttons.get("start"), "#3b1f24")
        elif mode == "paused":
            tint(self._buttons.get("pause"), "#2f2a1d")
        elif mode == "processing":
            tint(self._buttons.get("stop"), "#1f2e36")
        else:
            tint(self._buttons.get("cancel"), "#1b222d")
