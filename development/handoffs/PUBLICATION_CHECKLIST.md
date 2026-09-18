# Publication checklist for online continuation

> Historical checklist prepared for the August 2 M05 checkpoint. The fixed file
> counts, milestone, and failed-fetch note below are historical. The September
> 18 continuation snapshot includes completed work through B09/B10C and migration
> 0049; use `AURUS_HANDOFF.md` and current STATUS for continuation. The exclusion
> rules and quality commands below remain applicable.

The online checkout cannot reproduce the current product from the remote base
commit alone. Publish one reviewed project snapshot before starting the online
task.

## Required checks

1. Confirm that the commit contains the complete intended M01-M05 foundation,
   not only the latest course-map files. The active M05 slice depends on new
   models, migrations 0015-0038, identity/session/LTI services, Canvas import,
   tutor routes, simulator UI, tests, and `development/` documentation.
2. Review all 85 modified and 185 untracked paths. Separate intentional source,
   fixtures, migrations, tests, and docs from local QA artifacts.
3. Keep these paths out of Git:
   - `.env` and `.env.local` files;
   - `.claude/`, `.playwright-cli/`, and `.playwright-mcp/`;
   - `output/`, logs, screenshots, temporary databases, and browser state;
   - credentials, tokens, private keys, cookies, and real Canvas content.
4. Check staged scope and whitespace before committing:

   ```bash
   git status --short
   git diff --cached --stat
   git diff --cached --check
   ```

5. Run at least the current batch-close gates before publishing:

   ```bash
   python -m pytest -q
   npm --prefix frontend run lint
   npm --prefix frontend run build
   pre-commit run --all-files
   ```

6. Commit on a user-approved branch and push it. Then open that exact branch in
   the online Codex environment and use `ONLINE_CODEX_START_PROMPT.md`.

## Current Git note

At handoff preparation time the checked-out branch was
`J-D-polish-ui-and-stability` at `b017a01`. Its configured upstream was
`origin/J-D-polish-ui-and-stability`. A live fetch failed because the local
proxy endpoint at `127.0.0.1:10808` was unavailable, so verify the remote again
immediately before publication.

No commit or push was performed while preparing this handoff.
