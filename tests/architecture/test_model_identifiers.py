"""DC12 / ADR-016: model identifiers are configuration, never literals in source code.

Patterns and why each is forbidden under src/:
- `claude-<x>`: Anthropic model ids all start with "claude-". A hard-coded id ties business logic to
  one model version and hides which model produced a result.
- `convaiinnovations/`: the Hugging Face organisation that publishes Laya. A hard-coded repo id pins
  the model outside the reproducibility record.
Model choices belong in validated files under configs/, which this scan does not cover.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_ID_PATTERNS = {
    "anthropic-model-id": re.compile(r"\bclaude-[a-z0-9]", re.IGNORECASE),
    "laya-hf-repo": re.compile(r"\bconvaiinnovations/", re.IGNORECASE),
}


def model_identifier_findings(source_root: Path) -> list[tuple[str, int, str]]:
    """Return (file, line number, pattern name) for every model-id literal under source_root."""
    findings: list[tuple[str, int, str]] = []
    for path in sorted(p for p in source_root.rglob("*") if p.is_file()):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            findings.extend(
                (str(path.relative_to(source_root)), line_number, name)
                for name, pattern in MODEL_ID_PATTERNS.items()
                if pattern.search(line)
            )
    return findings


def test_anthropic_model_id_literal_is_reported(tmp_path: Path) -> None:
    (tmp_path / "client.py").write_text('MODEL = "claude-opus-5-5"\n')

    assert model_identifier_findings(tmp_path) == [("client.py", 1, "anthropic-model-id")]


def test_laya_repository_literal_is_reported(tmp_path: Path) -> None:
    (tmp_path / "settings.toml").write_text('repo = "convaiinnovations/laya"\n')

    assert model_identifier_findings(tmp_path) == [("settings.toml", 1, "laya-hf-repo")]


def test_plain_mentions_of_the_models_are_not_reported(tmp_path: Path) -> None:
    (tmp_path / "doc.py").write_text('"""Claude and Laya are optional feature producers."""\n')

    assert model_identifier_findings(tmp_path) == []


def test_real_source_tree_has_no_model_identifiers() -> None:
    assert model_identifier_findings(REPO_ROOT / "src") == []
