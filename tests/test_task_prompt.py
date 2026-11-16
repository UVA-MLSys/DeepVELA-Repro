"""Task prompts are rendered from the dataset record, never written by hand (evaluation/task_prompt.py)."""

import json

import pytest

from evaluation import task_prompt
from evaluation.task_prompt import DATASET_DIR, REPO_ROOT, load, render


@pytest.fixture(autouse=True)
def no_source_clones(monkeypatch):
    # The documented-command check reads the benchmark clones under .cache/sources, absent in a fresh checkout.
    monkeypatch.setattr(task_prompt, "undocumented_commands", lambda source, tasks: [])


def test_every_answered_source_renders_every_task_with_its_record():
    rendered = 0
    for path in sorted(DATASET_DIR.rglob("*.json")):
        source = load(path.relative_to(DATASET_DIR).with_suffix("").as_posix())
        if source.policy.forbidden is None:  # unanswered source: covered by the refusal test
            continue
        text, tasks = render(source)
        assert "$" not in text.replace("$(", "").replace("$CACHE_ROOT", "")  # every template slot was filled
        if len(source.policy.inputs or {}) > 1:  # a shared path prefix is stated once, as CACHE_ROOT
            assert text.count(str(REPO_ROOT)) == 1
        assert json.loads(tasks) == [t.model_dump(exclude_none=True) for t in source.tasks]
        assert not any(t.task_prompt in text for t in source.tasks)  # per-target fields only in tasks.json
        rendered += 1
    assert rendered == 12  # every shipped MLPerf record


def test_unanswered_field_stops_rendering_and_names_it():
    source = load("mlperf-language-bert")
    source.policy.forbidden = None
    with pytest.raises(SystemExit, match="policy.forbidden"):
        render(source)
