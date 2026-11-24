Reproduce the targets in ./tasks.json from ./repo, the source tree of commit $commit without Git metadata. Each entry has $fields.

Platform: $platform

$inputs
$uv_cache
Work for each target in ./<target id>/ with OUTPUT_DIR=./<target id>/out, and save every log (build, run, evaluator) as a
*.log file there. Only files are scored.

Deliverable: ./reproduce.sh --target <target id>. It must work when copied alone beside a fresh copy of the repository,
with the inputs above, OUTPUT_DIR set and nothing built, run once per target in the order of ./tasks.json, all from one
directory, and write the target's `outputs` to OUTPUT_DIR.

Then write ./report.json as {target id: {result name: value exactly as printed}}, for example $report_example.

Do not access $forbidden. Outside this directory, use only the inputs$cache_named above, system software and temporary
directories.
$time_limit
