# Phase 16 — first playable Pixel Operations Room

Implemented on dedicated local branch `phase16-pixel-room`, preserving the clean
Phase 15 base `8e6a977a810bcd38485f40a51c3ed173583fe29d`. No backend source,
authentication, database schema, approval, controls, execution or verification
behavior changed. This is a first playable frontend, not full Phase 16 acceptance
against PostgreSQL or a verified GitHub checkpoint.

## Delivered

- Original pixel office furnishings, seven selectable characters, workstation
  names, chairs, monitors, cabinets, plants, lounge and handoff corridors.
- Browser-only canvas, Pixel Agents character sheets and adapted BFS pathfinding;
  source and art notices in `frontend/public/pixel-room/licenses/`.
- Continuous four-direction walking, typing/reading frames, stand/sit visual
  transitions, document carry/delivery, recipient acknowledgement and return.
  These are compact sprite-based transitions, not a bespoke large animation pack.
- Serialized handoffs reserve one recipient interaction at a time; collision
  routes avoid desks and occupied seats. Y sorting preserves furniture layering.
- Stable requestAnimationFrame renderer, independent 3-second protected polling,
  abortable 10-second requests, reduced-motion support, event/listener cleanup.
- Existing navigation retained and Pixel Operations Room added. Public
  `/pixel-room-preview` exposes only the explicitly labelled visual test, with no
  case requests, credentials or operational controls.
- Protected `/pixel-room` uses existing workbench case and reliability replay GET
  APIs. No new backend route, second workflow engine or operational writes.
- Initial live catch-up applies present status without reenacting old work.
  Subsequent persisted events queue in deterministic timestamp/kind/ID order.
  Stable case-scoped IDs deduplicate polls; at most 300 recent records are mapped.
  Replay freezes a received snapshot; pause/resume/fast-forward control animation
  only. Case switches discard old records and queued playback.
- Queue history, accepted specialist results, Supervisor review, targeted checks,
  conditional human review, synthetic execution and supported independent
  verification map to seven roles. Simulations cannot produce real completion.
- Clickable progress stages expose their persisted records. No fictional progress
  percentage. Blocked controls, waiting for human, failures and verified resolution
  stay distinct.
- Inspector includes task/record IDs, timestamps, linked permitted evidence,
  observed findings with support assessment, hypotheses, contradictions, missing
  evidence, recommendations, next known step and reconstruction limits.
- Human decisions stay in the existing protected Case Centre and Approvals pages.
  A review link appears only when protected approvals returns an eligible open
  review for the identity. No inline pause/cancel/takeover/override is added.

## Validation in this environment

- TypeScript and ESLint passed.
- 23 frontend unit tests passed (8 original + 15 Phase 16 tests). Report:
  `phase16-frontend-unit-results.xml`.
- Production Next.js webpack build passed.
- Four production Chromium browser checks passed. Report:
  `phase16-browser-results.xml`. Three test the actual office, selection,
  collision-backed full handoff, pause/resume, zero mutation requests,
  fast-forward and mobile layout. The fourth is an explicit **API transport
  contract fixture**, testing record inspection, blocked controls, read-only
  replay, stale data and case isolation. It is not a real backend journey.
- Backend regression: **71 passed, 283 skipped** without PostgreSQL. Report:
  `phase16-backend-regression.xml`. Prior Phase 15 reports are preserved.
  The skipped PostgreSQL suite must be rerun; these results do not replace the
  earlier Phase 15 database acceptance.
- Actual browser screenshots: `screenshots/phase16-office.png`,
  `phase16-handoff.png`, `phase16-mobile.png`; initial milestone captures also
  retained. No concept images are presented as implemented screenshots.
- No measured 60 FPS performance claim or enterprise load claim is made.

## Checkpoints and backup limitation

1. `7cab72f`: first selectable office and attribution.
2. `02e30a6`: continuous document handoff and animation controls.
3. `fbfba86`: protected record adapter, all-role mapping, progress/inspection and tests.

Direct Git push failed because no GitHub credentials were available. Connected
GitHub `create_branch` and `create_blob` both returned **403 Resource not accessible
by integration**. No Phase 16 commit is claimed pushed or remotely verified.
GitHub main remains the Phase 15 checkpoint. The downloadable source archive (which includes a Git bundle) preserves the local branch until repository write access is available.

## Run the visual office without a database

From the repository root:

```bash
cd frontend
npm ci
npm run build
npm run start
```

Open http://127.0.0.1:3000/pixel-room-preview and click
**Play Transaction → Supervisor handoff**. All four demo events are visual test
steps; none are persisted banking actions. Select any character by clicking its
sprite or its accessible button below the scene.

## Run with actual recorded cases

Follow `RECOVERY_HANDOFF.md` to create the isolated PostgreSQL demo and run backend,
worker and frontend. Log in with the authorized development token. Open
**Pixel Operations Room**, select a permitted case, then choose **Live** or
**Replay recorded case**. Actual supported independent verification is required
for verified progress. This integration uses real endpoints in source but still
requires a fresh PostgreSQL-backed Phase 16 acceptance run.

## Verification commands

```bash
cd frontend
npm run typecheck
npm run lint
npm test -- --outputFile=../phase16-frontend-unit-results.xml
npm run build
npx playwright install chromium
npx playwright test --config playwright.phase16.config.ts
cd ..
python verify_backend.py --report phase16-postgres-regression.xml
```

The backend verifier requires the administrative PostgreSQL connection described
in `RECOVERY_HANDOFF.md` and creates its own disposable database. Never point the
destructive integration fixtures directly at development. Browser tests start a
production frontend on port 3030. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` can supply a
preinstalled Chromium executable when the normal browser download is unavailable.

## Remaining acceptance / extension work

- Push the dedicated branch and verify the remote SHA once GitHub write access is
  available; do not overwrite Phase 15 main.
- Run real PostgreSQL journeys for accepted specialist handoff, targeted
  reinvestigation, human review, permitted execution, independent failure/success
  and backend processing while the room is closed or paused.
- Inline human mutation forms are deliberately deferred to the existing reviewed
  workbench. Current controls are inspection and navigation to permitted reviews.
- Interrupted/retargeted walking and deeper artwork/animation polish remain future
  improvements; V1 serializes playback and fast-forwards intentionally.
- Enterprise identity, tenancy and real banking are inherited future work, not
  enabled by this visualization.

## Restore Git history from the archive

```bash
git clone --branch phase16-pixel-room ResolveOS-phase16.bundle ResolveOS-recovered
cd ResolveOS-recovered
git remote set-url origin https://github.com/adenleung/ResolveOS.git
git push -u origin phase16-pixel-room
```

The final local checkpoint is the bundle branch HEAD. Push requires repository
write access; successful source packaging does not establish a remote backup.
