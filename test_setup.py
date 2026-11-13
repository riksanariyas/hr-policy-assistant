import os
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("GEMINI_API_KEY not found. Check your .env file.")

client = genai.Client(api_key=api_key)

for attempt in range(1, 6):
    try:
        reply = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents="Say hello in one line.",
        )
        print(reply.text)
        break
    except Exception as e:
        print(f"Attempt {attempt} failed: {str(e)[:120]}")
        time.sleep(attempt * 5)
else:
    print("Still failing. Try again later or try another model.")