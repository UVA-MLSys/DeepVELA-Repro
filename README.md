# DeepVELA-Repro

Agent skills for benchmark reproduction with Claude Code and Codex.

## Configurations

| Configuration | Claude Code | Codex |
| --- | --- | --- |
| Reproduce (Skill-guided) | [Reproduce](skills/claude/reproduce/SKILL.md) | [Reproduce](skills/codex/reproduce/SKILL.md) |
| Builder + Reproduce | [Builder + Reproduce](skills/claude/builder-reproduce/SKILL.md) | [Builder + Reproduce](skills/codex/builder-reproduce/SKILL.md) |

**Reproduce** follows the declared workload through preparation, preflight,
execution, repair, verification, and reporting. **Builder + Reproduce** first
constructs a source-grounded benchmark contract and assesses reference quality
against the MLCommons ontology, then hands that contract to Reproduce.
Reference-quality scores and reproduction agreement are separate assessments.

## Use

Choose the packages for your agent. Install `reproduce` for Skill-guided.
For Builder + Reproduce, install both `builder-reproduce` and `reproduce` from
the same agent directory. The builder package contains the ontology reference,
rubric, templates, and scoring scripts; the reproduction procedure is shared
with the standalone Reproduce configuration.

- Claude Code: place the selected folders under your project's `.claude/skills/`.
- Codex: place the selected folders under your project's `.agents/skills/`.

Invoke `reproduce` for reproduction alone. For Builder + Reproduce, invoke
`builder-reproduce`, request the ontology assessment and score, and continue
with `reproduce` in the same session. Builder scoring requires Python 3 and
PyYAML (`python -m pip install pyyaml`).
