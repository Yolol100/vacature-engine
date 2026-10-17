#!/usr/bin/env bash
# Read only the existing historical technical branch; never bootstrap or reset it.
set -euo pipefail
mkdir -p .runtime
git fetch --no-tags origin "+refs/heads/radar-state:refs/remotes/origin/radar-state"
sha="$(git rev-parse refs/remotes/origin/radar-state)"
if [[ -z "$sha" ]]; then echo "Missing existing radar-state branch"; exit 1; fi
echo "RADAR_STATE_BASE_SHA=$sha" >> "$GITHUB_ENV"
if git cat-file -e refs/remotes/origin/radar-state:review-observations.json 2>/dev/null; then
  git show refs/remotes/origin/radar-state:review-observations.json > .runtime/review-observations.json
else
  printf '%s\n' '{"schema_version":1,"observed":[],"runs":[]}' > .runtime/review-observations.json
fi
node --input-type=module -e "import {parseReviewState} from './radar/src/review-state.mjs'; import {readFileSync} from 'node:fs'; const r=parseReviewState(readFileSync('.runtime/review-observations.json','utf8')); console.log(JSON.stringify({technical_history_items:r.observed.length,completed_receipts:r.runs.length}));"
