targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment used to generate resource names.')
param environmentName string

@minLength(1)
@description('Azure region for all resources. It must support Flex Consumption, the selected Foundry model, and Durable Task Scheduler.')
@metadata({
  azd: {
    type: 'location'
  }
})
param location string

@description('Microsoft Foundry model deployment name.')
param foundryModel string = 'gpt-4.1'

@description('Microsoft Foundry model name.')
param foundryModelName string = 'gpt-4.1'

@description('Microsoft Foundry model version.')
param foundryModelVersion string = '2025-04-14'

@minValue(1)
@description('Microsoft Foundry Global Standard deployment capacity.')
param foundryDeploymentCapacity int = 10

@allowed([
  'Consumption'
  'Dedicated'
])
@description('Durable Task Scheduler billing SKU.')
param dtsSkuName string = 'Consumption'

@minValue(1)
@description('Durable Task Scheduler capacity when the Dedicated SKU is selected.')
param dtsDedicatedCapacity int = 1

@description('Region for the Connector Namespace.')
param connectorNamespaceLocation string = 'westcentralus'

@description('URL of the Dataverse environment, for example https://org.crm.dynamics.com.')
param dataverseEnvironmentUrl string = ''

@description('Power Platform environment ID, used when the URL is not set.')
param dataverseEnvironmentId string = ''

@description('Friendly Dataverse environment name, used when the URL and ID are not set.')
param dataverseEnvironmentName string = ''

@description('Entity set name for the Policy Service Request table.')
param dataverseTableName string = 'ipr_policyservicerequests'

@description('Provision and configure Office 365 Outlook as an attachment-based fallback intake.')
param enableOutlookFallback bool = false

@description('Office 365 Outlook folder ID or connector-recognized path used for fallback intake.')
param outlookFolderPath string = 'Inbox/Policy Review'

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
}
var functionAppName = 'func-policy-${resourceToken}'
var identityName = 'id-policy-${resourceToken}'
var storageAccountName = 'stpolicy${resourceToken}'
var appServicePlanName = 'asp-policy-${resourceToken}'
var logAnalyticsName = 'log-policy-${resourceToken}'
var applicationInsightsName = 'appi-policy-${resourceToken}'
var foundryAccountName = 'aipolicy${resourceToken}'
var foundryProjectName = '${foundryAccountName}-project'
var schedulerName = 'dts-policy-${resourceToken}'
var connectorGatewayName = 'cgw-policy-${resourceToken}'
var dataverseConnectionName = 'dataverse-policy-intake'
var outlookConnectionName = 'office365-outlook'
var taskHubName = 'policyreviews'
var deploymentContainerName = 'app-package-${resourceToken}'
var reportContainerName = 'policy-review-packets'
var intakeContainerName = 'policy-intake'
var deployerPrincipalId = deployer().objectId

resource resourceGroup 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module identity 'br/public:avm/res/managed-identity/user-assigned-identity:0.4.1' = {
  name: 'identity'
  scope: resourceGroup
  params: {
    name: identityName
    location: location
    tags: tags
  }
}

module storage './app/storage.bicep' = {
  name: 'storage'
  scope: resourceGroup
  params: {
    name: storageAccountName
    location: location
    tags: tags
    deploymentContainerName: deploymentContainerName
    reportContainerName: reportContainerName
    intakeContainerName: intakeContainerName
  }
}

module logAnalytics 'br/public:avm/res/operational-insights/workspace:0.7.0' = {
  name: 'log-analytics'
  scope: resourceGroup
  params: {
    name: logAnalyticsName
    location: location
    tags: tags
    dataRetention: 30
  }
}

module monitoring 'br/public:avm/res/insights/component:0.4.1' = {
  name: 'application-insights'
  scope: resourceGroup
  params: {
    name: applicationInsightsName
    location: location
    tags: tags
    workspaceResourceId: logAnalytics.outputs.resourceId
    disableLocalAuth: true
  }
}

module foundry './app/foundry.bicep' = {
  name: 'foundry'
  scope: resourceGroup
  params: {
    accountName: foundryAccountName
    projectName: foundryProjectName
    location: location
    tags: tags
    modelDeploymentName: foundryModel
    modelName: foundryModelName
    modelVersion: foundryModelVersion
    deploymentCapacity: foundryDeploymentCapacity
    managedIdentityPrincipalId: identity.outputs.principalId
    deployerPrincipalId: deployerPrincipalId
  }
}

module dts './app/dts.bicep' = {
  name: 'durable-task-scheduler'
  scope: resourceGroup
  params: {
    name: schedulerName
    taskHubName: taskHubName
    location: location
    tags: tags
    skuName: dtsSkuName
    dedicatedCapacity: dtsDedicatedCapacity
    managedIdentityPrincipalId: identity.outputs.principalId
    deployerPrincipalId: deployerPrincipalId
  }
}

module appServicePlan 'br/public:avm/res/web/serverfarm:0.1.1' = {
  name: 'app-service-plan'
  scope: resourceGroup
  params: {
    name: appServicePlanName
    location: location
    tags: tags
    reserved: true
    sku: {
      name: 'FC1'
      tier: 'FlexConsumption'
    }
  }
}

module rbac './app/rbac.bicep' = {
  name: 'rbac'
  scope: resourceGroup
  params: {
    storageAccountName: storage.outputs.name
    applicationInsightsName: monitoring.outputs.name
    managedIdentityPrincipalId: identity.outputs.principalId
    deployerPrincipalId: deployerPrincipalId
  }
}

module connectors './app/connector-gateway.bicep' = {
  name: 'connector-gateway'
  scope: resourceGroup
  params: {
    connectorGatewayName: connectorGatewayName
    dataverseConnectionName: dataverseConnectionName
    outlookEnabled: enableOutlookFallback
    outlookConnectionName: outlookConnectionName
    location: connectorNamespaceLocation
    tags: tags
    managedIdentityPrincipalId: identity.outputs.principalId
    deployerPrincipalId: deployerPrincipalId
    tenantId: tenant().tenantId
  }
}

var outlookAppSettings = enableOutlookFallback ? {
  O365_MCP_SERVER_URL: connectors.outputs.outlookMcpEndpointUrl
  O365_MCP_CLIENT_ID: identity.outputs.clientId
} : {}

module api './app/api.bicep' = {
  name: 'api'
  scope: resourceGroup
  dependsOn: [
    rbac
  ]
  params: {
    name: functionAppName
    location: location
    tags: tags
    applicationInsightsName: monitoring.outputs.name
    appServicePlanId: appServicePlan.outputs.resourceId
    storageAccountName: storage.outputs.name
    deploymentStorageContainerName: deploymentContainerName
    identityId: identity.outputs.resourceId
    identityClientId: identity.outputs.clientId
    appSettings: union({
      AZURE_FUNCTIONS_AGENTS_PROVIDER: 'foundry'
      FOUNDRY_PROJECT_ENDPOINT: foundry.outputs.projectEndpoint
      FOUNDRY_MODEL: foundry.outputs.modelDeploymentName
      AZURE_CLIENT_ID: identity.outputs.clientId
      DURABLE_TASK_SCHEDULER_CONNECTION_STRING: 'Endpoint=${dts.outputs.endpoint};Authentication=ManagedIdentity;ClientID=${identity.outputs.clientId}'
      TASKHUB_NAME: dts.outputs.taskHubName
      POLICY_REVIEW_STORAGE_URL: storage.outputs.blobEndpoint
      POLICY_REVIEW_CONTAINER: reportContainerName
      POLICY_INTAKE_CONTAINER: intakeContainerName
      DATAVERSE_TABLE_NAME: dataverseTableName
      ENABLE_MULTIPLATFORM_BUILD: 'true'
    }, outlookAppSettings)
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP_NAME string = resourceGroup.name
output AZURE_FUNCTION_NAME string = api.outputs.name
output AZURE_CLIENT_ID string = identity.outputs.clientId
output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.name
output POLICY_REVIEW_STORAGE_URL string = storage.outputs.blobEndpoint
output POLICY_REVIEW_CONTAINER string = reportContainerName
output POLICY_INTAKE_CONTAINER string = intakeContainerName
output DATAVERSE_CONNECTOR_GATEWAY_NAME string = connectors.outputs.connectorGatewayName
output DATAVERSE_CONNECTION_NAME string = connectors.outputs.dataverseConnectionName
output DATAVERSE_CONNECTION_ID string = connectors.outputs.dataverseConnectionId
output DATAVERSE_ENVIRONMENT_URL string = dataverseEnvironmentUrl
output DATAVERSE_ENVIRONMENT_ID string = dataverseEnvironmentId
output DATAVERSE_ENVIRONMENT_NAME string = dataverseEnvironmentName
output DATAVERSE_TABLE_NAME string = dataverseTableName
output ENABLE_OUTLOOK_FALLBACK bool = enableOutlookFallback
output O365_CONNECTOR_GATEWAY_NAME string = connectors.outputs.connectorGatewayName
output O365_CONNECTION_NAME string = connectors.outputs.outlookConnectionName
output O365_CONNECTION_ID string = connectors.outputs.outlookConnectionId
output O365_MCP_SERVER_URL string = connectors.outputs.outlookMcpEndpointUrl
output OUTLOOK_FOLDER_PATH string = outlookFolderPath
output DURABLE_TASK_SCHEDULER_NAME string = dts.outputs.name
output DURABLE_TASK_HUB_NAME string = dts.outputs.taskHubName
output DURABLE_TASK_DASHBOARD_URL string = dts.outputs.dashboardUrl
output FOUNDRY_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output FOUNDRY_MODEL string = foundry.outputs.modelDeploymentName
