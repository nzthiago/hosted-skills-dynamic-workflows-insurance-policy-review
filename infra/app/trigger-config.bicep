param connectorGatewayName string
param connectionName string = 'dataverse-policy-intake'
param triggerConfigName string = 'dataverse-policy-service-request-created'
@secure()
param callbackUrl string
param dataset string
param tableName string = 'ipr_policyservicerequests'
param recurrenceFrequency string = 'Minute'
param recurrenceInterval string = '5'

#disable-next-line BCP081
resource connectorGateway 'Microsoft.Web/connectorGateways@2026-05-01-preview' existing = {
  name: connectorGatewayName
}

#disable-next-line BCP081
resource dataverseTrigger 'Microsoft.Web/connectorGateways/triggerconfigs@2026-05-01-preview' = {
  parent: connectorGateway
  name: triggerConfigName
  properties: {
    state: 'Enabled'
    description: 'Invokes policy intake when a Policy Service Request row is created.'
    connectionDetails: {
      connectorName: 'commondataservice'
      connectionName: connectionName
    }
    operationName: 'GetOnNewItems_V2'
    parameters: [
      {
        name: 'dataset'
        value: dataset
      }
      {
        name: 'table'
        value: tableName
      }
    ]
    metadata: {
      recurrenceFrequency: recurrenceFrequency
      recurrenceInterval: recurrenceInterval
    }
    notificationDetails: {
      callbackUrl: callbackUrl
      httpMethod: 'POST'
    }
  }
}

output triggerConfigId string = dataverseTrigger.id
