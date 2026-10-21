param location string
param foundryEndpoint string
param foundryModel string
param speechEndpoint string
param speechRegion string
param speechResourceId string
param minReplicas int

var token = uniqueString(resourceGroup().id)

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${token}'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${token}'
  location: location
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: logs.id }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'cr${token}'
  location: location
  sku: { name: 'Basic' }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${token}'
  location: location
}

// AcrPull so the app can pull its image with the managed identity
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, identity.id, 'acrpull')
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${token}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey }
    }
  }
}

resource engine 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-engine'
  location: location
  tags: { 'azd-service-name': 'engine' }
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  dependsOn: [acrPull]
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      // WebSocket sessions are long-lived and sticky enough for a replay: one session = one connection
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
    }
    template: {
      containers: [{
        name: 'engine'
        image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' // replaced by `azd deploy`
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'HTG_ENV', value: 'azure' }
          { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryEndpoint }
          { name: 'FOUNDRY_MODEL', value: foundryModel }
          { name: 'SPEECH_ENDPOINT', value: speechEndpoint }
          { name: 'SPEECH_REGION', value: speechRegion }
          { name: 'SPEECH_RESOURCE_ID', value: speechResourceId }
          { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
          { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
        ]
      }]
      scale: { minReplicas: minReplicas, maxReplicas: 2 }
    }
  }
}

output registryEndpoint string = registry.properties.loginServer
output url string = 'https://${engine.properties.configuration.ingress.fqdn}'
output principalId string = identity.properties.principalId
