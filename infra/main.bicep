targetScope = 'subscription'

@minLength(1)
@maxLength(16)
@description('azd environment name, used to name resources')
param environmentName string
param location string = 'swedencentral'

@description('Foundry project endpoint and model deployment already created by the owner')
param foundryEndpoint string
param foundryModel string = 'gpt-5-mini'
param foundryReasoningEffort string = 'minimal'
param speechEndpoint string
param speechRegion string
param speechResourceId string

@description('1 during judging so the demo never cold-starts; 0 otherwise')
param minReplicas int = 1

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: { 'azd-env-name': environmentName }
}

module app 'app.bicep' = {
  scope: rg
  name: 'app'
  params: {
    location: location
    foundryEndpoint: foundryEndpoint
    foundryModel: foundryModel
    foundryReasoningEffort: foundryReasoningEffort
    speechEndpoint: speechEndpoint
    speechRegion: speechRegion
    speechResourceId: speechResourceId
    minReplicas: minReplicas
  }
}

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = app.outputs.registryEndpoint
output APP_URL string = app.outputs.url
output APP_PRINCIPAL_ID string = app.outputs.principalId
