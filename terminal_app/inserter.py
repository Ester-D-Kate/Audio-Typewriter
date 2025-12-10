import time
from typing import Optional

import pyautogui
import pyperclip


def insert_text_at_cursor(text: str, delay: float = 0.2, paste: bool = True) -> None:
    if not text:
        return
    # Copy then paste to avoid per-character latency
    if paste:
        pyperclip.copy(text)
        time.sleep(delay)
        pyautogui.hotkey("ctrl", "v")
    else:
        pyautogui.typewrite(text, interval=0.01)


def safe_insert(text: str) -> Optional[str]:
    try:
        insert_text_at_cursor(text)
        return None
    except Exception as exc:
        return str(exc)
