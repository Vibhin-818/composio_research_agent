import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI

from config import MODEL, NVIDIA_BASE_URL, NVIDIA_MAX_TOKENS, NVIDIA_TIMEOUT


def _load_env() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()
_api_key = os.environ.get("NVIDIA_API_KEY", "")
_client = OpenAI(
    base_url=NVIDIA_BASE_URL,
    api_key=_api_key or "not-configured",
    timeout=NVIDIA_TIMEOUT,
    max_retries=0,
)


def _parse_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
        content = re.sub(r"\s*```$", "", content)
    return json.loads(content)


def chat_json(
    system: str,
    user: str,
    schema: Optional[dict[str, Any]] = None,
    model: str = MODEL,
) -> dict[str, Any]:
    if not _api_key:
        raise RuntimeError("NVIDIA_API_KEY is missing. Add it to .env.")

    system_prompt = (
        f"{system}\nReturn exactly one valid JSON object without Markdown fences."
    )
    if schema is not None:
        system_prompt += f"\nThe JSON object must follow this schema:\n{json.dumps(schema)}"

    response = _client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        top_p=0.95,
        max_tokens=NVIDIA_MAX_TOKENS,
        extra_body={
            "reasoning_budget": -1,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        stream=False,
    )
    content = response.choices[0].message.content or ""
    return _parse_json(content)
