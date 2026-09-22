# Stage runbook — Nordic Integration Summit, Demo 2

This is a **stage runbook**, not a tutorial. It exists to run Demo 2 live, on
time, and recover cleanly if the Dataverse poll runs long. For setup and
concepts, see [How it works](how-it-works.md), [Deploy](deploy.md), and
[Troubleshooting](troubleshooting.md).

**Stage shell: Windows Terminal running PowerShell 7+ (`pwsh`).** Every command
below is written PowerShell-first because the live session runs from a Windows
laptop. A Bash/zsh equivalent follows in parentheses or a secondary block where
the syntax differs (line continuation, environment variables); the underlying
CLI flags are identical on every OS. No WSL is required — Azure CLI, `azd`,
Python, and `uv` all install as native Windows binaries, and `azd`'s hooks
already select the matching `.ps1` script on Windows automatically
(`azure.yaml`).

## Thesis (say this, remember this)

> The same connector contract can carry a document to a card, or a business
> row into a durable, auditable agent workflow that still leaves the decision
> to a human.

## Where Demo 2 sits in the 35-minute session

The talk runs **31 minutes of content plus a 4-minute recovery buffer**. Two
demos share one spine — *Connector Namespace connects. Hosted Skills reason.
Dynamic Workflows execute durable multistep work.* Demo 1 is unstructured
document intelligence (SharePoint → Content Understanding `prebuilt-layout` →
deterministic routing → one private-channel Teams card, one invocation). Demo
2, this runbook, is a structured business event driving a model-authored,
durable, multi-step plan that ends in a human-reviewed packet — the contrast
*is* the thesis.

## 35-minute show flow

| Time | Beat | What happens |
| --- | --- | --- |
| 0:00–3:00 | Hook + start the Demo 2 clock | State the thesis. **Create the unique Dataverse row now** so its five-minute poll runs in the background. |
| 3:00–7:00 | Three platform layers | Connector Namespace connects. Hosted Skills reason. Dynamic Workflows execute durable multistep work. |
| 7:00–14:00 | Demo 1 | SharePoint → polling trigger → Content Understanding extraction → deterministic routing → private Teams card. |
| 14:00–18:00 | Hosted Skills bridge | One `.agent.md` maps to one Azure Function; event triggers plus instructions plus tools become an AI-powered skill. |
| 18:00–27:00 | **Demo 2 (this runbook)** | Return to the row; follow manifest → Event Grid → Dynamic Workflow → HTML report, in that order. |
| 27:00–31:00 | Trust boundary + lessons | Metadata-only review, idempotency, observable durability, explicit human decision boundary. |
| 31:00–35:00 | Buffer / close | Absorb polling variance or questions. Close on: *connect business events, add bounded reasoning, keep decisions human-owned.* |

By the time you return to Demo 2 at 18:00, roughly 15–19 minutes have elapsed
since row creation — comfortably past one five-minute poll.

## Pre-stage checklist

**Browser tabs (left → right, pinned, in this order):**

1. Power Apps table view, filtered to today's rows
2. Connector Namespace connection status (must read **Connected**)
3. Blob container `policy-intake/normalized/`
4. Durable Task Scheduler dashboard (`DURABLE_TASK_DASHBOARD_URL`)
5. Blob container `policy-review-packets/reviews/` (or the downloaded HTML report)
6. A pre-seeded, previously validated HTML report open in its own tab as cold fallback

**Logins refreshed before walking on stage:**

- `az login --tenant "<tenant ID>"` completed within the last hour (opens the
  default browser on Windows, same as macOS/Linux).
- `azd auth login` completed.
- Power Apps / Dataverse portal session active (not just cached).

**Warmed resources:**

- Function App is not in a cold-start state — trigger one harmless invocation
  beforehand (e.g. re-run the fallback ladder's known-good row once in
  rehearsal).
- Connector Namespace connection shows **Connected**, not **Needs attention**.
- `GetOnNewItems_V2` trigger config shows **Enabled**.

**Pre-created fallback artifacts (own device, not cloud-dependent):**

- One previously validated Request ID, its completed DTS instance, and its
  downloaded `output/<request-id>.html`, ready to open with zero network calls.
- `examples/policy-service-request.json` present for the manual-fallback path.

**Terminal:**

- Windows Terminal, PowerShell 7+ (`pwsh`) profile pinned as default, font
  size bumped for the room (18pt+). Two tabs: one dedicated to the E2E
  script launched at 0:00 and left running untouched until minute 18:00 (see
  Step 1 below), and a separate working tab for anything else.
- Working directory already at the repository root in both tabs.
- Command history cleared of any environment-specific values; retype the
  `--azd-environment` flag live rather than relying on shell history/autocomplete
  that could reveal another environment's name.

**Display and notifications:**

- OS notifications and chat pop-ups silenced (Do Not Disturb / Focus Assist).
- Browser zoom and terminal font large enough for the back row; no dev-tools
  panels open by default.
- Close unrelated tabs and apps that might leak internal names on screen share.

**Connector status, confirmed within the hour:**

- Dataverse connection: **Connected**.
- `GetOnNewItems_V2` trigger: **Enabled**, five-minute polling interval.
- Event Grid subscription for `Host.Functions.main`: present and healthy (see
  [Troubleshooting](troubleshooting.md) if not).

## Exact live Demo 2 sequence

**Launch at minute 0:00, in a dedicated terminal tab you leave running and
untouched.** This is the same terminal tab referenced again at minute 18:00 —
open a second Windows Terminal tab for it now if Demo 1 needs the first tab
free. Do not close or reuse this tab before Step 7.

### Step 1 — 0:00 · Launch the E2E script (this is "Run the E2E script")

- **Action:** In the dedicated tab, paste and run:

  ```powershell
  uv run --with-requirements requirements.txt `
    python scripts/create_dataverse_request.py `
    --azd-environment "ipr-dv-e2e-0917" `
    --wait `
    --download-report
  ```

  (Swap `ipr-dv-e2e-0917` for your own `--azd-environment` value if different.
  Omitting `--request-id` auto-generates a unique `PSR-DV-<timestamp>-<random>`
  ID, so this run can never collide with rehearsal.)
- **What appears:** Within a few seconds:
  `Request ID: PSR-DV-...`, `Dataverse row ID: ...`,
  `Expected manifest: policy-intake/normalized/<request-id>.json`,
  `Expected report: policy-review-packets/reviews/<request-id>.html`, then
  `Normalized manifest: waiting (the connector polls every five minutes;
  timeout 15 minutes)`. The script then blocks silently — that is expected,
  it is polling Blob Storage every 15 seconds in the background.
- **What to show:** The terminal tab itself, for a few seconds only.
- **Say:** "This is one real Dataverse row — a Policy Service Request —
  created just now. It generates its own unique ID, so this run can't
  collide with anything from rehearsal."
- **If it stalls:** No `Request ID:` line within ~10 seconds means the script
  failed before creating the row (auth or environment resolution). Press
  `Ctrl+C`, glance at the printed error, and re-run once. If it fails twice,
  move on to slides anyway and use the fallback ladder's pre-seeded run at
  18:00 — never debug auth live.

**Now switch away** to the opening/Demo 1 screens for the next ~11 minutes.
Leave the dedicated tab alone; do not alt-tab back to check it.

### Step 2 — 18:00 · Return to the terminal tab

- **Action:** Alt-tab back to the dedicated terminal tab from Step 1. Do not
  press Enter or re-run anything.
- **What appears:** `Normalized manifest: ready after <N>s` should already be
  printed (the five-minute connector poll elapsed during Demo 1). The next
  line will be either `HTML report: waiting for Event Grid, Functions.main,
  and DTS` (still running) or `HTML report: ready after <N>s` (already done).
- **What to show:** The terminal tab.
- **Say:** "While we talked, the connector polled, picked up the row, and
  normalized it into a Blob manifest."
- **If it stalls:** Still on `Normalized manifest: waiting...` after 18+
  minutes elapsed means the poll hasn't fired yet. Give it the 30–60 seconds
  from fallback ladder step 1 while narrating the architecture slide; if it's
  still not there, jump straight to fallback ladder step 2 (pre-seeded run).

### Step 3 — Show the normalized manifest

- **Action:** Click pinned browser tab 3 (Blob container
  `policy-intake/normalized/`). If using Storage Browser in the Azure portal,
  it's already scoped to that container/prefix from the pre-stage checklist.
- **What appears:** One JSON blob named `<request-id>.json` (the exact ID
  printed in Step 1), with a "Last modified" timestamp a few minutes old.
- **What to show:** That blob listing.
- **Say:** "One deterministic JSON file — the only thing this connector
  produces, no automation started yet."
- **If it stalls:** Blob not listed yet — refresh the container view once; if
  still missing, the manifest genuinely isn't there, return to Step 2's
  fallback.

### Step 4 — Show the Durable Task Scheduler dashboard

- **Action:** Click pinned browser tab 4 (DTS dashboard). If it isn't already
  loaded, retrieve and open the URL directly:

  ```powershell
  Start-Process (azd env get-value DURABLE_TASK_DASHBOARD_URL -e "ipr-dv-e2e-0917")
  ```

  (The same URL is also printed by the script itself, as `DTS dashboard:
  https://...`, once the report finishes — see Step 6.)
- **What appears:** An orchestration instance for `<request-id>` in
  **Running** or **Completed** state, with the parallel-inspect fan-out
  visible in the instance graph.
- **What to show:** That orchestration instance's detail view.
- **Say:** "Event Grid picked up that Blob and invoked the hosted skill —
  here's the durable workflow it built: validate, inspect each document in
  parallel, build, publish."
- **If it stalls:** Instance not listed yet — wait ~30 seconds while
  narrating from slides; do not repeatedly refresh on stage.

### Step 5 — Point at the fan-out

- **Action:** Click/expand the parallel activity group in the DTS dashboard
  instance view.
- **What appears:** Multiple parallel `inspect_driver_document` activities.
- **What to show:** The expanded fan-out (same tab as Step 4).
- **Say:** "Two documents, two parallel branches — this plan was authored by
  the model, not hand-coded as a DAG."
- **If it stalls:** Not applicable — this is a read of an already-completed
  instance from Step 4.

### Step 6 — Back to the terminal for completion

- **Action:** Alt-tab to the dedicated terminal tab (Steps 1–2).
- **What appears, in order:** `HTML report: ready after <N>s`, then
  `Downloaded report: C:\...\output\<request-id>.html`, then
  `DTS dashboard: https://...`, then `E2E success: Dataverse row, normalized
  manifest, and HTML report are ready.`
- **What to show:** The terminal tab.
- **Say:** "The workflow just finished — durably, with every step recorded."
- **If it stalls:** Still on `HTML report: waiting for Event Grid,
  Functions.main, and DTS` after another ~60 seconds — go to fallback ladder
  step 2 (pre-seeded report) rather than waiting further on stage.

### Step 7 — Open the HTML report

- **Action:** In the same terminal, open the file the previous step printed:

  ```powershell
  Start-Process "output\<request-id>.html"
  ```

  (Substitute the Request ID printed in Step 1; or click the path from the
  `Downloaded report:` line directly in File Explorer.)
- **What appears:** Default browser opens the report showing a
  `Human review required. No decision has been made.` banner and
  per-document status rows for the licence and signed-request documents.
- **What to show:** This newly opened browser tab — make it your active
  window.
- **Say:** "The report flags what's missing or expired — and the decision
  stays right here: `decision: null`. No auto-approval, no auto-denial."
- **If it stalls:** File not found yet (Step 6 hadn't finished downloading) —
  switch instead to pinned browser tab 5
  (`policy-review-packets/reviews/`) and open the blob there.

## WOW moments to call out explicitly

- **A business row becomes an auditable durable workflow** — no code change,
  no new pipeline, the same connector contract as Demo 1.
- **Parallel fan-out/fan-in** — the model-authored plan inspects multiple
  documents concurrently, then rejoins into one report.
- **The report keeps the decision human-owned** — `human_review_required` and
  `decision: null` are printed on screen, not just in the docs.
- **Idempotency, live** — mention (don't demo unless asked) that replaying the
  same Request ID cannot start a second workflow.

## What NOT to show or explain on stage

- Don't open `dataverse_intake.py` or any source file line-by-line.
- Don't explain OAuth token exchange, managed identity plumbing, or Event Grid
  subscription JSON.
- Don't show the Ruff/pytest suite or CI configuration.
- Don't narrate the five-minute polling wait in real time — cut away to Demo 1
  and come back.
- Don't open `azd env get-value` output that could reveal subscription IDs,
  tenant IDs, or storage account names — copy only the values you need before
  the session.
- Don't attempt to fix a broken connector connection live — go to the fallback
  ladder instead.

## Success signals (what "it worked" looks like)

1. Dataverse row visible in Power Apps with the generated Request ID.
2. `policy-intake/normalized/<request-id>.json` exists in Blob Storage.
3. Durable Task Scheduler instance for that Request ID shows **Completed**.
4. `policy-review-packets/reviews/<request-id>.html` exists.
5. The HTML report shows `review_status: human_review_required`.
6. The HTML report shows `decision: null`.

## Fallback ladder (never improvise auth on stage)

Work down this list in order — stop at the first step that lets you keep
narrating:

1. **Wait briefly.** If you're inside the 15-minute script timeout and just
   past a five-minute boundary, give it 30–60 more seconds while talking
   through the architecture slide.
2. **Show the pre-seeded orchestration.** Switch to the previously validated
   Request ID's DTS instance and report, opened before the talk. Label it
   clearly: *"here's a run from rehearsal, same path, already completed."*
3. **Use the E2E script's manual path.** Set the storage target, then submit
   directly (without these two variables the script falls back to a local
   dev-storage connection string, not the real demo storage account):

   ```powershell
   $env:POLICY_REVIEW_STORAGE_URL = azd env get-value POLICY_REVIEW_STORAGE_URL -e "ipr-dv-e2e-0917"
   $env:POLICY_INTAKE_CONTAINER = azd env get-value POLICY_INTAKE_CONTAINER -e "ipr-dv-e2e-0917"
   uv run --with-requirements requirements.txt python scripts/demo.py submit-manual --request examples/policy-service-request.json
   ```

   (Identical on Bash/zsh with `export` in place of `$env:` — no line
   continuation needed either way.) This writes the same normalized manifest
   directly, bypassing the connector poll entirely. Console shows `Submitted
   fallback request PSR-2026-00042 with 2 document records.` Continue
   narrating from the Blob/DTS/report steps (Steps 3–7 above), using Request
   ID `PSR-2026-00042` (from `examples/policy-service-request.json`) in place
   of the auto-generated ID.
4. **Show the known-good report.** If Blob Storage, Event Grid, or DTS are
   unreachable, open the downloaded `output/<request-id>.html` from your own
   device — no network dependency.
5. **Never** attempt to re-authenticate Azure CLI, `azd`, or the Connector
   Namespace connection live. If auth is broken, move straight to step 4 and
   explain that this is a previously validated run.

<details>
<summary>Optional presenter recovery: inspect the manifest/report directly
with Azure CLI (not part of the happy path — use only if a browser tab
fails)</summary>

Only if a pinned browser tab won't load, confirm a blob exists straight from
Azure CLI (`--auth-mode login` reuses your existing `az login`, no keys or
SAS needed):

```powershell
$storageAccount = (azd env get-value POLICY_REVIEW_STORAGE_URL -e "ipr-dv-e2e-0917") -replace 'https://([^.]+)\..*', '$1'

# Confirm the normalized manifest exists
az storage blob show --account-name $storageAccount --auth-mode login `
  --container-name policy-intake --name "normalized/<request-id>.json"

# Confirm/download the HTML report
az storage blob download --account-name $storageAccount --auth-mode login `
  --container-name policy-review-packets --name "reviews/<request-id>.html" `
  --file "output/<request-id>.html"
```

This is a diagnostic check, not something to narrate or show on the
projector — glance at the terminal, confirm the blob exists, then return to
the normal Blob-container/report browser tabs.

</details>

## Reset / rehearsal instructions

Every rehearsal and every live attempt must use a **new, unique Request ID** —
duplicate IDs are rejected by design and won't start a new review.

```powershell
uv run --with-requirements requirements.txt `
  python scripts/create_dataverse_request.py `
  --azd-environment "<your-azd-environment-name>" `
  --wait `
  --download-report
```

Bash/zsh equivalent (same flags, backslash continuation):

```bash
uv run --with-requirements requirements.txt \
  python scripts/create_dataverse_request.py \
  --azd-environment "<your-azd-environment-name>" \
  --wait \
  --download-report
```

Example, using a previously validated environment name as a concrete
reference only (substitute your own):

```powershell
uv run --with-requirements requirements.txt `
  python scripts/create_dataverse_request.py `
  --azd-environment "ipr-dv-e2e-0917" `
  --wait `
  --download-report
```

- Omit `--request-id` so a unique ID is generated every time
  (`PSR-DV-<timestamp>-<random>`).
- Use `--driver-licence-status` and `--signed-request-status` (choices:
  `received`, `missing`, `expired`) to rehearse different report outcomes.
- Default timeout is 15 minutes (`--timeout-minutes`); budget at least one
  five-minute connector poll.
- To re-download a report from an earlier run:

  ```powershell
  uv run --with-requirements requirements.txt python scripts/demo.py download `
    --blob "reviews/<request-id>.html" `
    --output "output/<request-id>.html"
  ```

- Rehearse the full sequence at least once the day of the talk, and keep that
  run's Request ID as your fallback artifact.

## Speaker phrasing (say it this way)

- **Connector Namespace:** "Managed integration infrastructure that connects
  business systems through triggers and actions — not a workflow engine, and
  not an Azure Functions feature. It's a shared resource any compute can call."
- **Hosted Skills:** "One `.agent.md` file maps to one Azure Function. It
  combines an event trigger, natural-language instructions, and optional
  tools — the Function supplies identity, monitoring, and scale."
- **The handoff (say all four hops, don't compress):** "Connector Namespace
  does not invoke the hosted skill directly. The Dataverse callback validates
  the row and writes a create-only normalized manifest to Blob Storage. An
  Event Grid `BlobCreated` subscription then invokes the hosted skill's Blob
  trigger. That event-based handoff is required on Flex Consumption, where
  polling Blob triggers aren't supported."
- **Dynamic Workflows:** "This moves a model-generated tool plan out of the
  chat loop and into durable orchestration on the Durable Task Scheduler —
  steps can fan out in parallel, waits survive restarts, and the hosted skill
  gets the final result, not every intermediate payload. It's bounded, not
  free-form: workflow tools are explicitly allowed, synchronous,
  JSON-serializable, and idempotent — not a static deterministic DAG, and not
  any MCP tool."
- **Authentication:** "The Function reaches Azure resources and the Connector
  Namespace runtime with managed identity. The business-system connections —
  Dataverse here — are interactively authorized OAuth connections." Never say
  "managed identity end to end."
- **Close line:** "Connect the business events you already have. Add bounded
  reasoning. Keep the decision human-owned."

## Presenter-only caveats (know these, say them when asked — not slide filler)

- **Preview status.** Azure Functions Hosted Skills and Connector Namespace
  are preview capabilities with no preview SLA and limited regional/connector
  coverage. Never call either GA or production-ready.
- **`GetOnNewItems_V2` is publicly listed as "When a row is added (Admin
  Only) [DEPRECATED]."** It polls every five minutes and fires on created
  rows only — no updates, no deletes. It's a proven demo bridge, not the
  recommended long-term trigger.
- **Admin Only / Global Read.** The connector authorization account needs
  organization-level ("Global") Read on the table — an elevated access
  requirement; use a dedicated, least-privilege account, not a personal one.
- **Metadata-only review.** The workflow inspects filename/status metadata.
  It does not download or open the referenced documents, validate identity,
  detect fraud, or authenticate signatures.
- **No automated policy decision.** The workflow produces a review packet. It
  does not approve or deny coverage, change a policy, or write a decision back
  to Dataverse. An authorized human makes the call outside the workflow.
