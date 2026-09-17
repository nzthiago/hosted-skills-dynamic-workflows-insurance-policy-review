param connectorGatewayName string
param connectionName string = 'dataverse-policy-intake'
param location string = resourceGroup().location
param tags object = {}
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
  name: connectionName
  properties: {
    connectorName: 'commondataservice'
    displayName: 'Dataverse Policy Service Request intake'
  }
}

#disable-next-line BCP081
resource deployerAccessPolicy 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = {
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
resource gatewayAccessPolicy 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = {
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

output connectorGatewayName string = connectorGateway.name
output connectionName string = dataverseConnection.name
output connectionId string = dataverseConnection.id
