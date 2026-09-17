"""Insurance policy review hosted skill and Outlook intake."""

from azure_functions_agents import create_function_app

from outlook_intake import process_outlook_trigger

app = create_function_app()


@app.function_name(name="OutlookPolicyIntake")
@app.generic_trigger(arg_name="trigger_data", type="connectorTrigger")
async def outlook_policy_intake(trigger_data) -> None:  # type: ignore[no-untyped-def]
    """Stage Outlook attachments and publish one normalized request manifest."""
    await process_outlook_trigger(trigger_data)
