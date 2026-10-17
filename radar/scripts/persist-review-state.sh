#!/usr/bin/env bash
# Stage a review-only technical receipt on the EXISTING radar-state branch.
# No spreadsheet, D1, mailbox or application status writes.
set -euo pipefail

test "${RADAR_PERSIST:-0}" = "1"
test "${RADAR_APPROVED_PERSIST:-}" = "yes"
test "${GITHUB_EVENT_NAME:-}" = "workflow_dispatch"
test "${GITHUB_ACTOR:-}" = "Yolol100"
test -n "${RADAR_STATE_BASE_SHA:-}"
test -s .runtime/review-observations.next.json
test "$RADAR_STATE_BASE_SHA" != "missing"
test "$(git rev-parse --show-toplevel)" = "$GITHUB_WORKSPACE"

git fetch --no-tags origin "+refs/heads/radar-state:refs/remotes/origin/radar-state"
head="$(git rev-parse refs/remotes/origin/radar-state)"
if [[ "$head" != "$RADAR_STATE_BASE_SHA" ]]; then
  echo "Radar state branch moved: no write. Rerun with a fresh review."
  exit 1
fi

worktree="$(mktemp -d)"
cleanup() {
  git -C "$GITHUB_WORKSPACE" worktree remove --force "$worktree" >/dev/null 2>&1 || true
  rmdir "$worktree" >/dev/null 2>&1 || true
}
trap cleanup EXIT

git worktree add --detach "$worktree" "$head"
cp .runtime/review-observations.next.json "$worktree/review-observations.json"
(
  cd "$worktree"
  git config user.name "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  git add -- review-observations.json
  if ! git diff --cached --quiet; then
    git commit -m "chore(radar): checkpoint manual review observations" -- review-observations.json
    git push origin HEAD:refs/heads/radar-state
  fi
)

git fetch --no-tags origin "+refs/heads/radar-state:refs/remotes/origin/radar-state"
git show refs/remotes/origin/radar-state:review-observations.json > .runtime/review-observations.readback.json
cmp .runtime/review-observations.next.json .runtime/review-observations.readback.json
echo "Technical review receipt verified on existing radar-state branch."
