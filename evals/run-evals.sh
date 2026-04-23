#!/usr/bin/env bash
# Eval runner for jira-communication skill.
#
# Usage:
#   evals/run-evals.sh [iteration-name] [--results-json <path>]
#
# For each eval in evals/comprehensive-evals.json, spawns a headless `claude`
# run with the local jira plugin loaded (--plugin-dir). Captures stream-json
# output, counts tool_use events, and writes per-eval transcripts plus an
# optional consolidated results JSON (the format consumed by the post-refactor
# comparison step).
#
# Requires: claude CLI, jq.
# Exits 2 if either is missing (intended behavior; do not fabricate results).

set -euo pipefail

ITERATION="${1:-$(date +%Y%m%d-%H%M%S)}"
RESULTS_JSON=""
if [[ "${2:-}" == "--results-json" && -n "${3:-}" ]]; then
    RESULTS_JSON="$3"
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EVALS_JSON="$REPO_ROOT/evals/comprehensive-evals.json"
WORKSPACE="$REPO_ROOT/evals/comprehensive-workspace/$ITERATION"

if ! command -v claude >/dev/null 2>&1; then
    echo "ERROR: claude CLI not found in PATH" >&2
    exit 2
fi
if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq not found in PATH" >&2
    exit 2
fi

mkdir -p "$WORKSPACE"

eval_count=$(jq '.evals | length' "$EVALS_JSON")
echo "Running $eval_count evals into $WORKSPACE"

tmp_results=$(mktemp)
trap 'rm -f "$tmp_results" "$tmp_results.new"' EXIT
echo '[]' > "$tmp_results"

for i in $(seq 0 $((eval_count - 1))); do
    eval_obj=$(jq ".evals[$i]" "$EVALS_JSON")
    id=$(echo "$eval_obj" | jq -r '.id')
    name=$(echo "$eval_obj" | jq -r '.name')
    prompt=$(echo "$eval_obj" | jq -r '.prompt')
    expected=$(echo "$eval_obj" | jq -r '.expected_output')
    out_dir="$WORKSPACE/eval-$id/outputs"
    mkdir -p "$out_dir"

    start=$(date +%s)
    # --plugin-dir loads the local jira plugin so the skill is available.
    # stream-json emits machine-readable tool_use events. bypassPermissions is
    # required for non-interactive runs (local scripts may fail on missing
    # Jira config — that's fine, we just want to capture intent).
    # (Not using --bare: it disables OAuth auth and requires ANTHROPIC_API_KEY,
    # which we do not set in dev environments.)
    printf '%s' "$prompt" | claude \
        --print \
        --output-format stream-json \
        --verbose \
        --plugin-dir "$REPO_ROOT" \
        --permission-mode bypassPermissions \
        > "$out_dir/stream.ndjson" 2>"$out_dir/stderr.log" || true
    end=$(date +%s)
    duration=$((end - start))

    # tool_calls: count of tool_use events in the assistant's messages.
    tool_calls=$(jq -s '[.[]? | select(.type == "assistant") | .message.content[]? | select(.type == "tool_use")] | length' "$out_dir/stream.ndjson" 2>/dev/null)
    if [[ -z "$tool_calls" ]]; then tool_calls=0; fi

    # Final assistant text (from the terminal result event).
    jq -rs '[.[]? | select(.type == "result") | .result] | last // ""' "$out_dir/stream.ndjson" > "$out_dir/output.txt" 2>/dev/null || : > "$out_dir/output.txt"

    # Pass heuristic: the expected_output typically names a `jira-*.py` script.
    # The eval passes when that script name appears anywhere in the stream's
    # tool-use commands. Evals without a script reference are marked "unknown".
    expected_script=$(printf '%s' "$expected" | grep -oE 'jira-[a-z-]+\.py' | head -1 || true)
    if [[ -n "$expected_script" ]]; then
        if grep -qF "$expected_script" "$out_dir/stream.ndjson"; then
            pass="true"
        else
            pass="false"
        fi
    else
        pass="unknown"
    fi

    jq --argjson id "$id" \
       --arg name "$name" \
       --arg pass "$pass" \
       --argjson tc "$tool_calls" \
       --argjson d "$duration" \
       '. + [{id: $id, name: $name, pass: $pass, tool_calls: $tc, duration_seconds: $d}]' \
       "$tmp_results" > "$tmp_results.new" && mv "$tmp_results.new" "$tmp_results"

    printf '  eval-%s (%s): pass=%s tool_calls=%s duration=%ss\n' "$id" "$name" "$pass" "$tool_calls" "$duration"
done

if [[ -n "$RESULTS_JSON" ]]; then
    mkdir -p "$(dirname "$RESULTS_JSON")"
    jq -n --arg iter "$ITERATION" --slurpfile results "$tmp_results" '{iteration: $iter, results: $results[0]}' > "$RESULTS_JSON"
    echo "Consolidated results: $RESULTS_JSON"
fi

echo "Done. Results in $WORKSPACE"
