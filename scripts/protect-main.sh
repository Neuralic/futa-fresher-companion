#!/usr/bin/env bash
# One-time setup by the repo admin (the lead). Requires the GitHub CLI: https://cli.github.com
# Usage: ./scripts/protect-main.sh OWNER/REPO
# NOTE: branch protection on PRIVATE repos needs a paid GitHub plan; public repos are free.
set -euo pipefail
REPO="${1:?usage: $0 OWNER/REPO}"

gh api -X PUT "repos/${REPO}/branches/main/protection" --input - <<JSON
{
  "required_status_checks": { "strict": true, "contexts": ["api", "web"] },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "require_code_owner_reviews": true,
    "dismiss_stale_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
echo "main is now protected on ${REPO}"
