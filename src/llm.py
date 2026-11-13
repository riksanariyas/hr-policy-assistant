import os
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_ATTEMPTS = 5

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not found. Check your .env file.")
        _client = genai.Client(api_key=api_key)
    return _client


def ask_llm(prompt):
    """Send a prompt to Gemini and return the text. Retries on busy (503) or limit (429)."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            reply = _get_client().models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            return reply.text
        except Exception as e:
            code = getattr(e, "code", None)
            retryable = code in (429, 503)
            if retryable and attempt < MAX_ATTEMPTS:
                wait = attempt * 5
                print(f"  (model busy, retrying in {wait}s, attempt {attempt})")
                time.sleep(wait)
                continue
            raise