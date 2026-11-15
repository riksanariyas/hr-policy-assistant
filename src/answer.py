import re

from src import store
from src.llm import ask_llm

SCORE_THRESHOLD = 0.40
FALLBACK = "This is not in the policy, please contact HR."
PERSONAL_REPLY = (
    "I can't look up personal information like your leave balance, hours or "
    "salary yet. Please contact HR for that."
)
DISCLAIMER = "Note: This is general information, not legal advice."

PERSONAL_PATTERNS = [
    r"\bmy (leave balance|balance|salary|payslip|attendance|performance|hours|bonus)\b",
    r"\bhow many (hours|days|leaves).{0,25}\b(did|have) i\b",
]

PROMPT = """You are an HR policy assistant for a small company.
Answer the employee's question using ONLY the numbered policy sections below.
Rules:
- Do not use any outside knowledge.
- If the sections do not clearly answer the question, reply with exactly: NOT_IN_POLICY
- Keep the answer short and clear.
- On the last line, write USED: followed by the numbers of the sections you used, for example USED: 1,3

POLICY SECTIONS:
{context}

QUESTION: {question}
"""


def _is_personal(question):
    q = question.lower()
    return any(re.search(p, q) for p in PERSONAL_PATTERNS)


def _hr_contact():
    hits = store.search("How do I contact HR?", k=1)
    return hits[0]["text"] if hits else ""


def _fallback(used_llm=False):
    contact = _hr_contact()
    text = FALLBACK
    if contact:
        text += "\n\n" + contact
    return {"answer": text, "sources": [], "fallback": True, "used_llm": used_llm}


def answer_question(question):
    """Return {'answer', 'sources', 'fallback', 'used_llm'}."""
    # 1. Personal data is not supported in v1
    if _is_personal(question):
        return {"answer": PERSONAL_REPLY, "sources": [], "fallback": True, "used_llm": False}

    # 2. Find the closest policy sections
    hits = store.search(question, k=3)
    if not hits or hits[0]["score"] < SCORE_THRESHOLD:
        return _fallback(used_llm=False)

    # 3. Ask the LLM, using only those sections
    context = "\n\n".join(f"[{i}] {h['text']}" for i, h in enumerate(hits, 1))
    reply = ask_llm(PROMPT.format(context=context, question=question)).strip()

    if "NOT_IN_POLICY" in reply:
        return _fallback(used_llm=True)

    # 4. Find which sections the LLM actually used
    used = []
    match = re.search(r"USED:\s*([\d,\s]+)", reply)
    if match:
        used = [int(n) for n in re.findall(r"\d+", match.group(1)) if 1 <= int(n) <= len(hits)]
        reply = reply[: match.start()].strip()
    if not used:
        used = [1]  # safe default: the best match
    used_hits = [hits[i - 1] for i in dict.fromkeys(used)]

    # 5. Sources, and the disclaimer only if a rights section was used
    sources = [f'{h["source"]} - {h["section"]}' for h in used_hits]
    if any(h["source"] == "employee_rights.txt" for h in used_hits):
        reply += "\n\n" + DISCLAIMER
    return {"answer": reply, "sources": sources, "fallback": False, "used_llm": True}