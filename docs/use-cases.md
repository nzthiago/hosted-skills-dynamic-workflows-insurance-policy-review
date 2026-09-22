# Try variations

## Complete request

Create a row with both statuses set to `received`. The report lists both required
document types as present:

```bash
uv run --with-requirements requirements.txt \
  python scripts/create_dataverse_request.py \
  --azd-environment "<azd environment>" \
  --signed-request-status received \
  --wait
```

```powershell
uv run --with-requirements requirements.txt `
  python scripts/create_dataverse_request.py `
  --azd-environment "<azd environment>" `
  --signed-request-status received `
  --wait
```

## Missing document

Set Signed request status to `missing`. The report identifies `signed_request` as
missing while retaining its filename as business metadata. This is the script default.

## Expired driver licence

Set Driver licence status to `expired`. The report marks the evidence as requiring a
current copy:

```bash
uv run --with-requirements requirements.txt \
  python scripts/create_dataverse_request.py \
  --azd-environment "<azd environment>" \
  --driver-licence-status expired \
  --wait
```

```powershell
uv run --with-requirements requirements.txt `
  python scripts/create_dataverse_request.py `
  --azd-environment "<azd environment>" `
  --driver-licence-status expired `
  --wait
```

## Duplicate delivery

Create or replay a row with the same Request ID. The deterministic manifest already
exists, so no second review starts. Use a unique Request ID for a new run.

## Manual fallback

```bash
python scripts/demo.py submit-manual --request examples/policy-service-request.json
```

The script creates the same normalized metadata manifest as Dataverse intake.

## Updates and deletes

They are intentionally unsupported. The configured `GetOnNewItems_V2` operation polls
only for rows created after trigger setup.
