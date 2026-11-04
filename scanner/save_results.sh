#!/usr/bin/env bash
# Publică rezultatele din docs/data pe GitHub (rulează în GitHub Actions).
set -euo pipefail
git config user.name "flight-scanner-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add docs/data
git diff --cached --quiet && exit 0
git commit -m "Scanare $(date -u +'%Y-%m-%d %H:%M') UTC"
# La conflict rămâne scanarea nouă: un job pornit din commit-ul care a declanșat rularea poate avea date mai vechi.
git pull --rebase -X theirs
git push
