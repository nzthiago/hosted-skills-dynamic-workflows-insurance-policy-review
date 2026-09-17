"""Insurance policy review hosted skill with Dataverse and Outlook intake."""

from azure_functions_agents import create_function_app

from dataverse_intake import process_dataverse_trigger
from outlook_intake import process_outlook_trigger

app = create_function_app()


@app.function_name(name="DataversePolicyIntake")
@app.generic_trigger(arg_name="trigger_data", type="connectorTrigger")
def dataverse_policy_intake(trigger_data) -> None:  # type: ignore[no-untyped-def]
    """Normalize created Dataverse rows into deterministic request manifests."""
    process_dataverse_trigger(trigger_data)


@app.function_name(name="OutlookPolicyIntake")
@app.generic_trigger(arg_name="trigger_data", type="connectorTrigger")
async def outlook_policy_intake(trigger_data) -> None:  # type: ignore[no-untyped-def]
    """Stage Outlook attachments and publish one normalized request manifest."""
    await process_outlook_trigger(trigger_data)
