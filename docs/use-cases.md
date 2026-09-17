# Try variations

## Complete request

Attach both:

```text
driver_license__DOC-001__jordan-license.pdf
signed_request__DOC-002__signed-request.pdf
```

The report lists both required document types as present.

## Missing document

Send only the driver's license. The normalized request contains only retrieved
attachments, and the report identifies `signed_request` as missing.

## Duplicate delivery

Send the same request ID again or replay the connector callback. The deterministic
manifest already exists, so no second review starts. Use a new request ID for a new run.

## Manual or OneDrive-synced fallback

Set a document's `source_path` in the example JSON to a local or OneDrive-synced path:

```bash
python scripts/demo.py submit-manual --request examples/policy-service-request.json
```

The script stages the file and creates the same normalized manifest as Outlook intake.

## Empty request

The Outlook path rejects messages without non-inline attachments. For workflow-only
testing, a manually normalized request may contain an empty `documents` list; the report
lists both required document types as missing.
