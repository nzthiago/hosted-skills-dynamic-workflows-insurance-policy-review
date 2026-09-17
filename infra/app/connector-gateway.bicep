param connectorGatewayName string
param connectionName string = 'office365-outlook'
param mcpServerConfigName string = 'o365-outlook-get-attachment-only'
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
resource office365Connection 'Microsoft.Web/connectorGateways/connections@2026-05-01-preview' = {
  parent: connectorGateway
  name: connectionName
  properties: {
    connectorName: 'office365'
    displayName: 'Office 365 Outlook policy intake'
  }
}

#disable-next-line BCP081
resource appAccessPolicy 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = {
  parent: office365Connection
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
resource deployerAccessPolicy 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = {
  parent: office365Connection
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
resource gatewayAccessPolicy 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = {
  parent: office365Connection
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
resource attachmentMcpServer 'Microsoft.Web/connectorGateways/mcpserverconfigs@2026-05-01-preview' = {
  parent: connectorGateway
  name: mcpServerConfigName
  properties: {
    state: 'Enabled'
    description: 'Read-only Office 365 Outlook attachment retrieval for policy intake.'
    connectors: [
      {
        name: 'office365'
        connectionName: office365Connection.name
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
output connectionName string = office365Connection.name
output connectionId string = office365Connection.id
output mcpEndpointUrl string = attachmentMcpServer.properties.mcpEndpointUrl
