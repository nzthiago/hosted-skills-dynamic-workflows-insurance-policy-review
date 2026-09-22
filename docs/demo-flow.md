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

- Windows Terminal, one tab, PowerShell 7+ (`pwsh`) profile pinned as default,
  font size bumped for the room (18pt+).
- Working directory already at the repository root.
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

Run this starting at minute 0:00 (row creation) and return to steps 4–8 at
minute 18:00.

| # | Thiago does | Screen shows | Narration (one line) |
| --- | --- | --- | --- |
| 1 | Runs the E2E script with `--wait --download-report` in a terminal, no `--request-id` (unique ID auto-generated) | Terminal prints the generated Request ID and "row created" | "This is one real Dataverse row — a Policy Service Request — created just now." |
| 2 | Switches to Demo 1 for the next ~11 minutes | (Demo 1 screens) | — |
| 3 | Returns to the terminal tab | Terminal shows "normalized manifest ready" (should already be printed) | "While we talked, the connector polled, picked up the row, and normalized it into a Blob manifest." |
| 4 | Switches to the Blob container tab | `policy-intake/normalized/<request-id>.json` listed | "One deterministic JSON file — the only thing this connector produces, no automation started yet." |
| 5 | Switches to the Durable Task Scheduler dashboard tab (or opens the printed URL) | Orchestration instance in **Running** or **Completed** state, with the parallel-inspect fan-out visible | "Event Grid picked up that Blob and invoked the hosted skill — here's the durable workflow it built: validate, inspect each document in parallel, build, publish." |
| 6 | Points at the fan-out step specifically | Multiple parallel `inspect_driver_document` activities | "Two documents, two parallel branches — this plan was authored by the model, not hand-coded as a DAG." |
| 7 | Switches to the terminal | "HTML report ready" printed, report path shown | "The workflow just finished — durably, with every step recorded." |
| 8 | Opens the downloaded `output/<request-id>.html` (or the Blob tab) | HTML report with `human_review_required` banner and per-document status | "The report flags what's missing or expired — and the decision stays right here: `decision: null`. No auto-approval, no auto-denial." |

If the manifest or report has **not** appeared by the time you return at
18:00, go straight to the fallback ladder below — do not wait silently on
stage.

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
3. **Use the E2E script's manual path.** Run
   `uv run --with-requirements requirements.txt python scripts/demo.py submit-manual --request examples/policy-service-request.json`
   (identical in PowerShell and Bash/zsh — no line continuation needed) to write
   the same normalized manifest directly, bypassing the connector poll
   entirely, and continue narrating from the Blob/DTS/report steps.
4. **Show the known-good report.** If Blob Storage, Event Grid, or DTS are
   unreachable, open the downloaded `output/<request-id>.html` from your own
   device — no network dependency.
5. **Never** attempt to re-authenticate Azure CLI, `azd`, or the Connector
   Namespace connection live. If auth is broken, move straight to step 4 and
   explain that this is a previously validated run.

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
