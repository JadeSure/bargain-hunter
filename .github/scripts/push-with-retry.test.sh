#!/usr/bin/env bash
# Regression check for push-with-retry.sh: reproduces the production failure
# (rejected push + a tracked-but-unstaged file left over from an earlier step,
# e.g. data/alert_state.json) and asserts push_with_retry still rebases and
# lands the push, with the unstaged file's content intact afterward.
#
# Run manually: bash .github/scripts/push-with-retry.test.sh
set -euo pipefail

# Resolved once, up front -- before any `cd` -- since BASH_SOURCE[0] can be a
# relative path (e.g. invoked as `bash .github/scripts/push-with-retry.test.sh`
# from the repo root) and a later `cd` would make `dirname` resolve it wrong.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

git init -q -b main "$WORK/bare" --bare
git init -q -b main "$WORK/seed"
git -C "$WORK/seed" config user.email t@t.com
git -C "$WORK/seed" config user.name t
mkdir -p "$WORK/seed/data"
echo v0 >"$WORK/seed/data/tracked.json"
git -C "$WORK/seed" add -A
git -C "$WORK/seed" commit -qm init
git -C "$WORK/seed" remote add origin "$WORK/bare"
git -C "$WORK/seed" push -qu origin main

git clone -q "$WORK/bare" "$WORK/runner"
git -C "$WORK/runner" config user.email t@t.com
git -C "$WORK/runner" config user.name t

# A concurrent push lands on origin -- unrelated to the tracked file below,
# same as another hunt.yml step's commit landing mid-run in production.
echo other >"$WORK/seed/data/other.txt"
git -C "$WORK/seed" add -A
git -C "$WORK/seed" commit -qm "other change"
git -C "$WORK/seed" push -q origin main

# The runner has an unstaged, tracked modification it never intends to commit
# here (like alert_state.json every real run), plus its own commit to push.
echo v1 >"$WORK/runner/data/tracked.json"
echo mine >"$WORK/runner/data/mine.txt"
git -C "$WORK/runner" add data/mine.txt
git -C "$WORK/runner" commit -qm mine

cd "$WORK/runner"
# shellcheck source=push-with-retry.sh
source "$SCRIPT_DIR/push-with-retry.sh"

push_with_retry >"$WORK/log" 2>&1 || { echo "FAIL: push_with_retry did not succeed"; cat "$WORK/log"; exit 1; }
[ "$(cat data/tracked.json)" = v1 ] || { echo "FAIL: unstaged tracked.json was lost"; exit 1; }
# (not `git log | grep -q`: with pipefail, grep -q's early exit on match can
# SIGPIPE the upstream `git log`, failing the pipeline despite a real match.)
git log --oneline >"$WORK/gitlog"
grep -q "other change" "$WORK/gitlog" || { echo "FAIL: rebase never picked up the concurrent commit"; exit 1; }

echo "push-with-retry.sh: regression check passed"
