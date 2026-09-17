# Troubleshooting

## The Outlook connection is not authorized

Run `azd provision` again to reopen the interactive authorization hook. Sign in with the
dedicated mailbox account. The connection must show `Connected` before deployment
continues.

## Email does not trigger intake

Confirm:

- the message reached `OUTLOOK_FOLDER_PATH`
- the subject starts with `[POLICY-REQUEST]`
- the message contains a non-inline attachment
- the trigger config uses `OnNewEmailV3`
- the Connector Extension preview bundle loaded

The trigger polls. Wait at least two configured polling intervals before using the manual
fallback.

## Attachment retrieval fails

The MCP config exposes only `GetAttachment_V2`. Confirm `O365_MCP_SERVER_URL` is set,
the Function identity has a connection access policy, and the connection is authorized.

Attachment names must be:

```text
<driver_license|signed_request>__<document-id>__<file-name>
```

Only PDF, JPEG, and PNG up to 10 MiB are accepted. The trigger currently includes
attachment metadata/bodies so IDs are present, but intake ignores inline `contentBytes`
and calls `GetAttachment_V2`.

## A duplicate email produces no workflow

This is expected when the request ID was already normalized. Use a new request ID for a
new review. Connector retries race on a Blob lease and cannot create a second manifest.

## The workflow does not start

Check the `policy-intake/normalized/` prefix and open:

```bash
azd env get-value DURABLE_TASK_DASHBOARD_URL
```

The hosted skill uses a Blob trigger, then loads the normalized manifest with
`load_normalized_policy_request`.

## The report is missing

Wait for `publish_driver_review_report`. Confirm `POLICY_REVIEW_STORAGE_URL` and
`POLICY_REVIEW_CONTAINER`.

## Live connector testing is blocked

Use the fallback:

```bash
python scripts/demo.py submit-manual --request examples/policy-service-request.json
```

The example stages a safe placeholder PDF. A OneDrive-synced file path can be supplied
through `source_path`.
