targetScope = 'subscription'

param appName string = 'gasblender'
param location string = 'northeurope'
param environment string = 'prod'
param resourceGroupName string = 'rg-gasblender-prod'

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: resourceGroupName
  location: location
}

var resourceToken = take(uniqueString(rg.id), 6)
var storageAccountName = toLower('st${replace(appName, '-', '')}${resourceToken}')

module storage 'modules/storage.bicep' = {
  name: 'storage-deploy'
  scope: rg
  params: {
    location: location
    storageAccountName: storageAccountName
  }
}

module app 'modules/functionApp.bicep' = {
  name: 'functionapp-deploy'
  scope: rg
  params: {
    location: location
    functionAppName: appName
    storageAccountName: storage.outputs.storageAccountName
    appEnv: environment
  }
}

output storageAccountName string = storage.outputs.storageAccountName
output functionAppName string = app.outputs.functionAppName
