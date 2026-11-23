import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader

from config import DIST, PATTERNS, REPORT_DIR, RESULTS, VERIFICATION


def _load(path: Path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def main() -> None:
    results = _load(RESULTS) or []
    patterns = _load(PATTERNS) or {}
    verification = _load(VERIFICATION)

    env = Environment(
        loader=FileSystemLoader(str(REPORT_DIR)),
        autoescape=True,
    )
    template = env.get_template("template.html")
    html = template.render(
        results=results,
        patterns=patterns,
        verification=verification,
    )
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"

    DIST.mkdir(parents=True, exist_ok=True)
    (DIST / "index.html").write_text(html, encoding="utf-8")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built {DIST / 'index.html'} ({len(results)} apps)")


if __name__ == "__main__":
    main()
