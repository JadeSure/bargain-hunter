#!/usr/bin/env bash
# Shared by hunt.yml's auto-commit steps. main moves constantly (this pipeline
# commits every few minutes), so every push needs a rebase-and-retry.
#
# The working tree almost always carries unstaged, tracked changes that this
# step never intends to commit -- data/deals_state.json and data/alert_state.json
# are rewritten by every pipeline run but only explicitly committed elsewhere
# (deals_state.json at most once/day; alert_state.json never). A plain
# `git pull --rebase` refuses to run against any unstaged change ("You have
# unstaged changes"), which silently kills every retry attempt (confirmed in
# production, runs 32431946523 and others). `-c rebase.autoStash=true` stashes
# and restores that automatically around the rebase.
#
# Usage: source this file, then call push_with_retry.
push_with_retry() {
  for attempt in 1 2 3 4 5; do
    if git push; then
      echo "Pushed on attempt $attempt."
      return 0
    fi
    echo "Push rejected (attempt $attempt); rebasing on latest main."
    if ! git -c rebase.autoStash=true pull --rebase -X theirs origin main; then
      git rebase --abort 2>/dev/null || true
    fi
  done
  return 1
}
