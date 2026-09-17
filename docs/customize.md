# Customize

## Change the mail contract

Edit `SUBJECT_PATTERN` and `ATTACHMENT_PATTERN` in
[src/outlook_intake.py](../src/outlook_intake.py), then update README examples and tests.
Keep parsing deterministic; do not ask the model to interpret mailbox commands.

## Change attachment limits

Update `ALLOWED_CONTENT_TYPES` and `MAX_ATTACHMENT_BYTES`. Treat email names, MIME types,
and content as untrusted. Keep connector operations read-only and allow-listed.

## Inspect real documents

`inspect_driver_document` currently evaluates normalized metadata and Blob references.
Document extraction/authenticity checking is a separate safety-sensitive extension. Keep
the report decision-neutral and require authorized human verification.

## Change the workflow

The plan is in [src/main.agent.md](../src/main.agent.md). Preserve:

- load → validate → parallel inspect → build → publish ordering
- JSON-serializable workflow activity results
- idempotent side effects
- `review_status: human_review_required`
- `decision: null`

## Use another intake connector

Keep the normalized manifest contract stable. Replace only the ingestion function,
Connector Namespace resources, and trigger config. Do not expose write/delete operations
when read-only retrieval is sufficient.
