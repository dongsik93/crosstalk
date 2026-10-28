# Isolated cmux PR reviews

Deep review prepares a detached worktree at a fixed PR head SHA. It leaves the
original checkout, branch, index, stash, tracked files, untracked files and ignored
files alone. Git objects, dedicated `refs/crosstalk/reviews/` fetch refs and worktree
registration metadata are shared; this is not a security sandbox.

Initialize or explicitly migrate the mailbox before using these commands. A review
uses `review_runs` in the mailbox DB and keeps its ownership record and artifacts
under `$CROSSTALK_CONFIG_DIR/reviews/runs/<id>/` (default
`~/.claude/crosstalk/reviews/runs/<id>/`). The checkout is separately stored under
`reviews/worktrees/<id>/`.

```sh
crosstalk review prepare 1440 --repo /absolute/repository --peer codex
crosstalk review status RUN_ID
crosstalk review finish RUN_ID --outcome completed --result-stdin --confirm-stopped < review-result.md
crosstalk review cleanup RUN_ID
```

For a local fixed-commit review, replace the PR number with `--base COMMIT --head
COMMIT`. Preparation resolves both to commit IDs, calculates their merge base and
generates the diff from that merge base to the fixed head. PR preparation gets the
base/head pair in one metadata request and fetches those exact object IDs into
Crosstalk refs. A moving remote head never changes an existing run's target.

Every peer request must include `review_root`, `head_sha` and the fixed diff path.
Every tool call must explicitly select that absolute root, and every result must
identify `reviewed_commit` and evidence paths. An inaccessible worktree is an error;
do not substitute the original repository. This release does not add Ghostty review.

The owner record is saved before worktree creation. A process killed after Git
creates the worktree leaves a diagnosable `preparing` run. `review status` checks
ownership and registration without writing the DB. It shows a verified interrupted
checkout as a candidate for inspection, not as an automatically resumed task.

`finish --confirm-stopped` attests that all peers and review commands have stopped
using the checkout. This does not kill or detect arbitrary external processes.
Finish stores the complete review result outside the checkout; for an aborted
review use `--outcome failed` and preserve existing answers and failure details.

Cleanup requires matching owner nonce, exact owned path, matching Git registration,
a detached unchanged HEAD, a finished run with stopped confirmation, and no tracked,
untracked or ignored changes. Symlinks, missing ownership, new commits and uncertain
active work are retained. Cleanup calls `git worktree remove` without force and has
no destructive fallback. The result is `removed`, `retained_active` or
`retained_dirty`; errors retain the run and record the error code. A second cleanup
is safe, but a path recreated after removal is considered unowned.

Review artifacts and fixed diffs remain after checkout removal. Dedicated fetched
refs are also retained. Cleanup is serialized for Crosstalk commands; an unrelated
process writing to the checkout after inspection cannot be fenced by this local
coordination mechanism. Do not confirm stopped while a peer is still working.

Git helper calls have bounded waits, their own process groups, disabled hooks and
fsmonitor. Configured checkout smudge/process filters are disabled while preparing
the worktree. No repository test or script is automatically run.

Automated coverage uses temporary Git repositories with simultaneous staged,
unstaged, untracked, ignored and stash data. It exercises preparation failures,
process death immediately after creation, dirty/new-commit retention, path and nonce
mismatch, cleanup failure, repeated cleanup, hooks/filters and read-only diagnosis.
Actual cmux peer execution remains a separate release verification requirement.
