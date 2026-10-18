from pathlib import Path
import re


SKILL_DIR = (
    Path(__file__).resolve().parents[1]
    / ".agents"
    / "skills"
    / "fiofilter-task-context"
)


def _skill_parts():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, metadata, body = text.split("---\n", 2)
    return metadata, body


def test_skill_has_codex_discoverable_manifest_and_explicit_policy():
    metadata, _ = _skill_parts()
    assert re.search(r"(?m)^name: fiofilter-task-context\s*$", metadata)
    description = re.search(r"(?m)^description: (.+)$", metadata)
    assert description and description.group(1).strip()

    policy = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert re.search(r"(?m)^  allow_implicit_invocation: false\s*$", policy)


def test_skill_contract_includes_context_map_and_recovery():
    _, body = _skill_parts()
    for required in (
        "VERIFIED_CONTEXT",
        "CANDIDATES_NOT_SELECTED",
        "UNCERTAINTIES",
        "RECOVERY",
        "evaluation hash",
        "matched tokens",
        "section_working_set.py",
        "NOT_VERIFIED",
        "git -C <root> show <sha>:<path>",
    ):
        assert required in body


def test_skill_remains_advisory_and_does_not_change_delivery():
    _, body = _skill_parts()
    body = " ".join(body.split())
    for invariant in (
        "INDEX_AUTHORITY=NAVIGATION_ONLY",
        "DISCOVERY_READ_SUPPRESSION=NO",
        "AUTO_CONTEXT_SELECTION=NO",
        "Never rewrite, suppress, replace",
        "Do not edit files",
        "RECOVERABLE is not SAFE_TO_HIDE",
        "no delivery, visibility, prompt, or source content was altered",
    ):
        assert invariant in body
