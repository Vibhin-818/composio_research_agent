import time
from typing import Any

from agent import llm
from schema import AppResearch

SYSTEM = (
    "You audit a research row against documentation excerpts. "
    "Return supported=true if the auth, access tier, and API claims are broadly consistent "
    "with the excerpts (details need not appear verbatim). "
    "Return supported=false only when you find a clear contradiction. "
    "Keep each issue short. Confidence is between 0 and 1."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "corrected_access": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["supported", "issues", "confidence"],
}


def verify(
    app: dict[str, Any], research: AppResearch, docs: dict[str, Any]
) -> dict[str, Any]:
    user = (
        f"Claims:\n{research.model_dump_json(indent=2)}\n\n"
        f"Evidence excerpts:\n{docs.get('text', '')}\n"
    )
    failures: list[str] = []
    for attempt in range(2):
        try:
            return llm.chat_json(SYSTEM, user, schema=SCHEMA)
        except Exception as exc:
            failures.append(f"attempt {attempt + 1}: {type(exc).__name__}: {exc}")
            if attempt == 0:
                time.sleep(1)
    return {
        "supported": False,
        "issues": ["NVIDIA verification failed after retries: " + " | ".join(failures)],
        "confidence": 0.0,
    }
