param connectorGatewayName string
param dataverseConnectionName string = 'dataverse-policy-intake'
param outlookEnabled bool = false
param outlookConnectionName string = 'office365-outlook'
param outlookMcpServerConfigName string = 'o365-outlook-get-attachment-only'
param location string = resourceGroup().location
param tags object = {}
param managedIdentityPrincipalId string
param deployerPrincipalId string
param tenantId string

#disable-next-line BCP081
resource connectorGateway 'Microsoft.Web/connectorGateways@2026-05-01-preview' = {
  name: connectorGatewayName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

#disable-next-line BCP081
resource dataverseConnection 'Microsoft.Web/connectorGateways/connections@2026-05-01-preview' = {
  parent: connectorGateway
  name: dataverseConnectionName
  properties: {
    connectorName: 'commondataservice'
    displayName: 'Dataverse Policy Service Request intake'
  }
}

#disable-next-line BCP081
resource dataverseDeployerAccessPolicy 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = {
  parent: dataverseConnection
  name: deployerPrincipalId
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        objectId: deployerPrincipalId
        tenantId: tenantId
      }
    }
  }
}

#disable-next-line BCP081
resource dataverseGatewayAccessPolicy 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = {
  parent: dataverseConnection
  name: 'connectorGateway-msi'
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        objectId: connectorGateway.identity.principalId
        tenantId: tenantId
      }
    }
  }
}

#disable-next-line BCP081
resource outlookConnection 'Microsoft.Web/connectorGateways/connections@2026-05-01-preview' = if (outlookEnabled) {
  parent: connectorGateway
  name: outlookConnectionName
  properties: {
    connectorName: 'office365'
    displayName: 'Office 365 Outlook policy intake fallback'
  }
}

#disable-next-line BCP081
resource outlookAppAccessPolicy 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = if (outlookEnabled) {
  parent: outlookConnection
  name: managedIdentityPrincipalId
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        objectId: managedIdentityPrincipalId
        tenantId: tenantId
      }
    }
  }
}

#disable-next-line BCP081
resource outlookDeployerAccessPolicy 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = if (outlookEnabled) {
  parent: outlookConnection
  name: deployerPrincipalId
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        objectId: deployerPrincipalId
        tenantId: tenantId
      }
    }
  }
}

#disable-next-line BCP081
resource outlookGatewayAccessPolicy 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = if (outlookEnabled) {
  parent: outlookConnection
  name: 'connectorGateway-msi'
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        objectId: connectorGateway.identity.principalId
        tenantId: tenantId
      }
    }
  }
}

#disable-next-line BCP081
resource outlookAttachmentMcpServer 'Microsoft.Web/connectorGateways/mcpserverconfigs@2026-05-01-preview' = if (outlookEnabled) {
  parent: connectorGateway
  name: outlookMcpServerConfigName
  properties: {
    state: 'Enabled'
    description: 'Read-only Office 365 Outlook attachment retrieval for fallback policy intake.'
    connectors: [
      {
        name: 'office365'
        connectionName: outlookConnection.name
        displayName: 'Office 365 Outlook'
        description: ''
        operations: [
          {
            name: 'GetAttachment_V2'
            displayName: 'Get policy request attachment'
            description: 'Retrieves one attachment by Outlook message and attachment ID.'
            userParameters: []
            agentParameters: [
              {
                name: 'messageId'
                schema: {
                  type: 'string'
                  description: 'Outlook message ID'
                }
              }
              {
                name: 'attachmentId'
                schema: {
                  type: 'string'
                  description: 'Outlook attachment ID'
                }
              }
            ]
          }
        ]
      }
    ]
    policies: []
    settings: {
      textOnlyContent: true
    }
  }
}

output connectorGatewayName string = connectorGateway.name
output dataverseConnectionName string = dataverseConnection.name
output dataverseConnectionId string = dataverseConnection.id
output outlookConnectionName string = outlookEnabled ? outlookConnection.name : ''
output outlookConnectionId string = outlookEnabled ? outlookConnection.id : ''
output outlookMcpEndpointUrl string = outlookAttachmentMcpServer.?properties.?mcpEndpointUrl ?? ''
