"""Documentation stays in sync with the code: tests list, counts, links."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    tests = sorted(path.name for path in (ROOT / "tests").glob("test_*.py"))
    count = len(tests)

    ru_testing = (ROOT / "docs" / "testing.md").read_text(encoding="utf-8")
    en_testing = (ROOT / "docs" / "en" / "testing.md").read_text(encoding="utf-8")
    missing_ru = [name for name in tests if name not in ru_testing]
    missing_en = [name for name in tests if name not in en_testing]
    check("all suites are listed in docs/testing.md", not missing_ru, str(missing_ru))
    check("all suites are listed in docs/en/testing.md", not missing_en, str(missing_en))

    ru_count = re.search(r"Всего\s+(\d+)\s+набор", ru_testing)
    en_count = re.search(r"There are\s+(\d+)\s+suites", en_testing)
    check("Russian testing count matches", bool(ru_count) and int(ru_count.group(1)) == count,
          ru_count.group(0) if ru_count else "not found")
    check("English testing count matches", bool(en_count) and int(en_count.group(1)) == count,
          en_count.group(0) if en_count else "not found")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    ru_readme_count = re.search(r"(\d+)\s+набор", readme)
    en_readme_count = re.search(r"(\d+)\s+suites", readme_en)
    check("README count matches", bool(ru_readme_count) and int(ru_readme_count.group(1)) == count,
          ru_readme_count.group(0) if ru_readme_count else "not found")
    check("README.en count matches", bool(en_readme_count) and int(en_readme_count.group(1)) == count,
          en_readme_count.group(0) if en_readme_count else "not found")

    broken = []
    for markdown in [ROOT / "README.md", ROOT / "README.en.md"] + list((ROOT / "docs").rglob("*.md")):
        text = markdown.read_text(encoding="utf-8")
        for target in re.findall(r"\]\((?!https?:)([^)#]+\.md)\)", text):
            if not (markdown.parent / target).resolve().exists():
                broken.append(f"{markdown.relative_to(ROOT)} -> {target}")
    check("relative markdown links resolve", not broken, str(broken[:6]))

    en_names = {item.name for item in (ROOT / "docs" / "en").glob("*.md")}
    missing_en_docs = [
        path.name
        for path in (ROOT / "docs").glob("*.md")
        if path.name != "crewai-api-notes.md" and path.name not in en_names
    ]
    check("English docs mirror the Russian ones", not missing_en_docs, str(missing_en_docs))

    for markdown in [ROOT / "README.md", ROOT / "README.en.md"] + list((ROOT / "docs").rglob("*.md")):
        text = markdown.read_text(encoding="utf-8")
        check(f"no published default password in {markdown.name}",
              "admin / 123admin!" not in text and "admin/123admin!" not in text)

    print("\nDOCS RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
