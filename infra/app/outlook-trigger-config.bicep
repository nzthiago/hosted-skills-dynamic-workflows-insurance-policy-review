param connectorGatewayName string
param connectionName string = 'office365-outlook'
param triggerConfigName string = 'office365-policy-request-email'
@secure()
param callbackUrl string
param folderPath string
param recurrenceFrequency string = 'Minute'
param recurrenceInterval string = '1'

#disable-next-line BCP081
resource connectorGateway 'Microsoft.Web/connectorGateways@2026-05-01-preview' existing = {
  name: connectorGatewayName
}

#disable-next-line BCP081
resource outlookTrigger 'Microsoft.Web/connectorGateways/triggerconfigs@2026-05-01-preview' = {
  parent: connectorGateway
  name: triggerConfigName
  properties: {
    state: 'Enabled'
    description: 'Invokes fallback policy intake for new Outlook messages with attachments.'
    connectionDetails: {
      connectorName: 'office365'
      connectionName: connectionName
    }
    operationName: 'OnNewEmailV3'
    parameters: [
      {
        name: 'folderPath'
        value: folderPath
      }
      {
        name: 'fetchOnlyWithAttachment'
        value: true
      }
      {
        // Attachment IDs are required for GetAttachment_V2. Intake code discards
        // trigger-provided contentBytes and explicitly retrieves each attachment.
        name: 'includeAttachments'
        value: true
      }
      {
        name: 'subjectFilter'
        value: '[POLICY-REQUEST]'
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

output triggerConfigId string = outlookTrigger.id
