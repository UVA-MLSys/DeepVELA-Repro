"""Seals and checks a task bundle: the frozen files every arm of one task starts from.

    python -m evaluation.bundle seal <task_id>     # write MANIFEST.sha256 after authoring
    python -m evaluation.bundle check <task_id>    # print the digest, or fail if a file changed

A bundle is `<bundle root>/<task_id>/` holding `manifest.yaml`, `prompt.md`, `tasks.json`, `masked.txt` and
`source.tar.gz` (agent-evaluation-profile, author mode). The digest covers every file in that folder, so an edit
after sealing makes `evaluation.prepare` refuse to launch until the task is re-authored and sealed again.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path

import yaml

from .task_prompt import DATASET_DIR, load as load_record

BUNDLE_ROOT_ENV_VAR = "EVALUATION_BUNDLE_DIR"
MANIFEST = "MANIFEST.sha256"
REQUIRED = ("manifest.yaml", "prompt.md", "tasks.json", "masked.txt", "source.tar.gz")


class EvaluationBundleError(ValueError):
    """The task bundle is missing, incomplete, or changed since it was sealed."""


def resolve_bundle_root() -> Path:
    """The deployment's bundle root, from `EVALUATION_BUNDLE_DIR`, recorded in docs/local-preferences.md, section 1."""
    value = os.environ.get(BUNDLE_ROOT_ENV_VAR)
    if not value:
        raise EvaluationBundleError(f"{BUNDLE_ROOT_ENV_VAR} is not set: take it from docs/local-preferences.md, section 1")
    return Path(value).expanduser().resolve()


def check_task_id(task_id: str) -> None:
    """A task ID is one or more path components of letters, digits, `.`, `_` and `-`, so it names a folder under
    the bundle and runs roots and stays safe inside a shell command."""
    if not all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]*", part) for part in task_id.split("/")):
        raise EvaluationBundleError(f"task_id {task_id!r} must be '/'-separated names of letters, digits, '.', '_', '-'")


def task_dir(task_id: str) -> Path:
    check_task_id(task_id)
    return resolve_bundle_root() / task_id


def check_manifest(task_id: str, folder: Path) -> None:
    """manifest.yaml names this task, a dataset record, and that record's commit, which the prompt also states."""
    manifest = yaml.safe_load((folder / "manifest.yaml").read_text()) or {}
    if manifest.get("task_id") != task_id:
        raise EvaluationBundleError(f"{folder}/manifest.yaml names task_id {manifest.get('task_id')!r}, expected {task_id!r}")
    source_id = manifest.get("source_id")
    if not source_id or not (DATASET_DIR / f"{source_id}.json").is_file():
        raise EvaluationBundleError(f"{folder}/manifest.yaml names source_id {source_id!r}, which has no dataset record")
    commit = load_record(source_id).repo["commit"]
    if manifest.get("commit") != commit:
        raise EvaluationBundleError(f"{folder}/manifest.yaml names commit {manifest.get('commit')!r}; the record pins {commit}")
    if commit not in (folder / "prompt.md").read_text():
        raise EvaluationBundleError(f"{folder}/prompt.md does not state commit {commit}: render it again from the record")


def _hashes(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file() and p.name != MANIFEST}


def _manifest_text(hashes: dict[str, str]) -> str:
    return "".join(f"{digest}  ./{rel}\n" for rel, digest in sorted(hashes.items()))


def seal(task_id: str) -> str:
    folder = task_dir(task_id)
    missing = [name for name in REQUIRED if not (folder / name).is_file()]
    if missing:
        raise EvaluationBundleError(f"{folder} lacks {', '.join(missing)}: finish author mode before sealing")
    check_manifest(task_id, folder)
    text = _manifest_text(_hashes(folder))
    (folder / MANIFEST).write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def bundle_digest(task_id: str) -> str:
    """sha256 of MANIFEST.sha256, after checking that it still lists exactly the folder's files and hashes."""
    folder = task_dir(task_id)
    manifest = folder / MANIFEST
    if not manifest.is_file():
        raise EvaluationBundleError(f"{manifest} does not exist: run `python -m evaluation.bundle seal {task_id}`")
    text = manifest.read_text()
    if text != _manifest_text(_hashes(folder)):
        raise EvaluationBundleError(f"{folder} changed after it was sealed: re-author the task and seal it again")
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["seal", "check"])
    parser.add_argument("task_id")
    args = parser.parse_args()
    print(seal(args.task_id) if args.action == "seal" else bundle_digest(args.task_id))


if __name__ == "__main__":
    main()
