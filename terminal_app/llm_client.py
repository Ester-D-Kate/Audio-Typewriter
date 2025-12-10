import os
import threading
import time
from typing import Callable, List, Optional

from groq import Groq


class GroqRateLimitError(RuntimeError):
    """Raised when all Groq keys are cooling down or exhausted."""
    pass

RATE_LIMIT_TOKENS = ("rate limit", "429", "limit", "quota", "too many", "overloaded")


class KeyManager:
    def __init__(self, cooldown_seconds: int = 300) -> None:
        # Collect all env keys that start with GROQ_API_KEY
        self.keys: List[str] = [
            value
            for key, value in sorted(os.environ.items())
            if key.startswith("GROQ_API_KEY") and value
        ]
        if not self.keys:
            raise RuntimeError("No GROQ_API_KEY* env vars found")
        print(f"[KeyManager] Loaded {len(self.keys)} API keys")
        self.cooldown_seconds = cooldown_seconds
        self.cooldown_until: dict[str, float] = {}
        self.lock = threading.Lock()
        self.cursor = 0

    def _is_available(self, key: str, now: float) -> bool:
        return self.cooldown_until.get(key, 0.0) <= now

    def next_key(self) -> Optional[str]:
        now = time.time()
        with self.lock:
            for _ in range(len(self.keys)):
                idx = self.cursor % len(self.keys)
                key = self.keys[idx]
                self.cursor = (self.cursor + 1) % len(self.keys)
                if self._is_available(key, now):
                    return key
            return None

    def backoff(self, key: str) -> None:
        with self.lock:
            self.cooldown_until[key] = time.time() + self.cooldown_seconds


class GroqLLM:
    def __init__(
        self,
        chat_model: str = "llama-3.3-70b-versatile",
        whisper_model: str = "whisper-large-v3-turbo",
        cooldown_seconds: int = 300,
    ) -> None:
        self.chat_model = chat_model
        self.whisper_model = whisper_model
        self.key_manager = KeyManager(cooldown_seconds=cooldown_seconds)

    def _with_key(self, fn: Callable[[Groq], str]) -> str:
        errors: List[str] = []
        tried = 0
        max_tries = len(self.key_manager.keys)
        while tried < max_tries:
            key = self.key_manager.next_key()
            if not key:
                print(f"[KeyManager] No available keys (all cooling down)")
                break
            key_preview = key[:8] + "..."
            client = Groq(api_key=key)
            try:
                result = fn(client)
                print(f"[KeyManager] Success with key {key_preview}")
                return result
            except Exception as exc:  # Broad catch to rotate keys on failures
                msg = str(exc).lower()
                if any(token in msg for token in RATE_LIMIT_TOKENS):
                    self.key_manager.backoff(key)
                    print(f"[KeyManager] Key {key_preview} rate-limited, cooling down 5min")
                    errors.append(f"{key[:5]}*** rate-limited; cooling down")
                    tried += 1
                    continue
                print(f"[KeyManager] Key {key_preview} failed: {exc}")
                errors.append(f"{key[:5]}*** failed: {exc}")
                tried += 1
                continue
        raise GroqRateLimitError(
            "All Groq keys failed or are cooling down: " + "; ".join(errors)
        )

    def transcribe(self, audio_path: str, language: str = "en") -> str:
        def _call(client: Groq) -> str:
            with open(audio_path, "rb") as fh:
                resp = client.audio.transcriptions.create(
                    file=fh,
                    model=self.whisper_model,
                    prompt="Lightly clean filler words; preserve meaning.",
                    response_format="json",
                    language=language,
                    temperature=0.0,
                )
            return getattr(resp, "text", "") or ""

        return self._with_key(_call)

    def format_text(self, raw_text: str) -> str:
        def _call(client: Groq) -> str:
            resp = client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict text corrector. You receive messy speech-to-text and return ONLY the corrected version.\n\n"
                            "ABSOLUTE RULES (violating any = failure):\n"
                            "1. NEVER answer questions. If user says 'what is the weather', output: 'What is the weather?'\n"
                            "2. NEVER add new information, opinions, or conversation.\n"
                            "3. NEVER greet, apologize, or add commentary.\n"
                            "4. Output ONLY the cleaned text, nothing else.\n\n"
                            "WHAT YOU FIX:\n"
                            "- Grammar and spelling mistakes\n"
                            "- Sentence structure and word order\n"
                            "- Punctuation: commas, periods, colons, semicolons, hyphens, parentheses\n"
                            "- Filler words (um, uh, like, you know) → remove\n"
                            "- Repeated words → remove duplicates\n"
                            "- Capitalization\n\n"
                            "FORMATTING RULES:\n"
                            "- Use '* ' bullets (one per line) when 3+ items are listed\n"
                            "- Use commas for 2 items in a sentence\n"
                            "- Use semicolons to join related thoughts\n"
                            "- Use colons before lists or explanations\n"
                            "- Use parentheses for clarifications like (optional)\n"
                            "- Use hyphens for compound words (time-box, multi-step)\n\n"
                            "EXAMPLES:\n\n"
                            "Input: 'hey john uh i was wondering if you could help me with something'\n"
                            "Output: Hey John, I was wondering if you could help me with something.\n\n"
                            "Input: 'so like the meeting is at 3 pm and we need to discuss the budget and timeline and resources'\n"
                            "Output:\n"
                            "The meeting is at 3 PM. We need to discuss:\n"
                            "* Budget\n"
                            "* Timeline\n"
                            "* Resources\n\n"
                            "Input: 'i think we should we should probably cancel the event its not gonna work out'\n"
                            "Output: I think we should probably cancel the event; it's not going to work out.\n\n"
                            "Input: 'can you send me the file the one from yesterday'\n"
                            "Output: Can you send me the file from yesterday?\n\n"
                            "Input: 'the options are pizza or pasta or salad let me know what you want'\n"
                            "Output:\n"
                            "The options are:\n"
                            "* Pizza\n"
                            "* Pasta\n"
                            "* Salad\n\n"
                            "Let me know what you want.\n\n"
                            "CRITICAL: You are not a chatbot. You do not converse. You only return corrected text."
                        ),
                    },
                    {
                        "role": "user",
                        "content": raw_text,
                    },
                ],
                temperature=0.0,
            )
            return resp.choices[0].message.content.strip()

        return self._with_key(_call)

    def generate_prompt(self, prompt_text: str) -> str:
        def _call(client: Groq) -> str:
            resp = client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a content generator. User speaks a task and you produce ONLY the requested content.\n\n"
                            "ABSOLUTE RULES:\n"
                            "1. Output ONLY the final content (email, report, message, etc.)\n"
                            "2. NO prefaces like 'Here is...' or 'Sure, I can...'\n"
                            "3. NO meta-commentary, apologies, or safety disclaimers\n"
                            "4. NO sending instructions like 'You can send this to...'\n"
                            "5. Use plain text only (no markdown fences, no headings)\n\n"
                            "FORMAT RULES:\n"
                            "- Emails: greeting, blank line, body paragraphs, blank line, closing, name\n"
                            "- Reports: title line, blank line, content paragraphs\n"
                            "- Lists: use '* ' bullets on new lines\n"
                            "- Match the tone user requests (formal, casual, etc.)\n\n"
                            "EXAMPLES:\n\n"
                            "User: 'write an email to ashwath saying i need leave tomorrow because i have an exam'\n"
                            "Output:\n"
                            "Dear Ashwath,\n\n"
                            "I am writing to request leave tomorrow as I have a scheduled exam. I will complete any pending work beforehand and catch up on anything I miss.\n\n"
                            "Please let me know if there is anything urgent I should handle before I leave.\n\n"
                            "Thank you for your understanding.\n\n"
                            "Best regards\n\n"
                            "User: 'um write a message to my team saying the deadline is extended to friday'\n"
                            "Output:\n"
                            "Hi team,\n\n"
                            "Just wanted to let you know that the deadline has been extended to Friday. Let me know if you have any questions.\n\n"
                            "Thanks\n\n"
                            "CRITICAL: Output the content directly. No conversation. No prefaces. No 'here is your email'."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt_text,
                    },
                ],
                temperature=0.0,
            )
            return resp.choices[0].message.content.strip()

        return self._with_key(_call)
