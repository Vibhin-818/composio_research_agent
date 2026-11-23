import csv
import json
from collections import defaultdict

from config import SAMPLE_CSV, VERIFICATION

REQUIRED_COLUMNS = {
    "app_id",
    "app",
    "field",
    "pass1_value",
    "pass2_value",
    "correct_value",
    "source_url",
    "notes",
}


def _normalize(field: str, value: str) -> tuple[str, ...] | str:
    value = " ".join(str(value).strip().casefold().split())
    if field == "auth_methods":
        return tuple(sorted(part.strip() for part in value.split(";") if part.strip()))
    return value


def main() -> None:
    with SAMPLE_CSV.open(encoding="utf-8-sig", newline="") as sample_file:
        reader = csv.DictReader(sample_file)
        missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            raise SystemExit(
                "verification_sample.csv is missing columns: "
                + ", ".join(sorted(missing_columns))
            )
        rows = list(reader)

    if not rows:
        raise SystemExit("verification_sample.csv has no hand-checked rows yet")

    checks: list[dict[str, object]] = []
    first_pass_misses: list[dict[str, str]] = []
    misses: list[dict[str, str]] = []
    by_app: dict[str, list[bool]] = defaultdict(list)
    pass1_correct = 0
    pass2_correct = 0
    improved = 0
    regressed = 0

    for row in rows:
        for field in ("app_id", "app", "field", "correct_value", "source_url"):
            if not row.get(field, "").strip():
                raise SystemExit(f"verification row is missing required value: {field}")

        field = row["field"].strip()
        pass1_ok = _normalize(field, row["pass1_value"]) == _normalize(
            field, row["correct_value"]
        )
        pass2_ok = _normalize(field, row["pass2_value"]) == _normalize(
            field, row["correct_value"]
        )
        pass1_correct += pass1_ok
        pass2_correct += pass2_ok
        improved += not pass1_ok and pass2_ok
        regressed += pass1_ok and not pass2_ok
        by_app[row["app_id"]].append(pass2_ok)

        check = {
            "app_id": row["app_id"],
            "app": row["app"],
            "field": field,
            "pass1_value": row["pass1_value"],
            "pass2_value": row["pass2_value"],
            "correct_value": row["correct_value"],
            "pass1_ok": pass1_ok,
            "pass2_ok": pass2_ok,
            "source_url": row["source_url"],
            "notes": row["notes"],
        }
        checks.append(check)
        if not pass1_ok:
            first_pass_misses.append(check)
        if not pass2_ok:
            misses.append(check)

    count = len(rows)
    pass1_accuracy = round(100 * pass1_correct / count, 1)
    pass2_accuracy = round(100 * pass2_correct / count, 1)
    out = {
        "sample_size": len(by_app),
        "fields_checked": count,
        "pass1_accuracy": pass1_accuracy,
        "pass2_accuracy": pass2_accuracy,
        "delta": round(pass2_accuracy - pass1_accuracy, 1),
        "improved_fields": improved,
        "regressed_fields": regressed,
        "per_app_accuracy": {
            app_id: round(100 * sum(values) / len(values), 1)
            for app_id, values in by_app.items()
        },
        "checks": checks,
        "first_pass_misses": first_pass_misses,
        "misses": misses,
    }
    VERIFICATION.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"Wrote {VERIFICATION}: pass 1 {pass1_accuracy}% -> "
        f"pass 2 {pass2_accuracy}% ({out['delta']:+.1f} pts) across "
        f"{len(by_app)} apps / {count} fields; "
        f"{improved} improved, {regressed} regressed"
    )


if __name__ == "__main__":
    main()
