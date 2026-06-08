targetScope = 'subscription'

param appName string = 'gasblender'
param location string = 'northeurope'
param environment string = 'prod'
param resourceGroupName string = 'rg-gasblender-prod'
param dnsResourceGroupName string = 'rg-dns-services-shared-001'
param customDomainHostname string = 'gasblender.redkic.co.uk'

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: resourceGroupName
  location: location
}

var resourceToken = take(uniqueString(rg.id), 6)
var storageAccountName = toLower('st${replace(appName, '-', '')}${resourceToken}')
var afdProfileName = 'afd-${appName}-${environment}'
var afdEndpointName = '${appName}-${resourceToken}'

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
    functionAppName: '${appName}-${resourceToken}'
    storageAccountName: storage.outputs.storageAccountName
    appEnv: environment
  }
}

module cdn 'modules/cdn.bicep' = {
  name: 'cdn-deploy'
  scope: rg
  params: {
    afdProfileName: afdProfileName
    afdEndpointName: afdEndpointName
    storageStaticWebHostname: storage.outputs.staticWebsiteHostname
    customDomainHostname: customDomainHostname
  }
}

module dns 'modules/dns.bicep' = {
  name: 'dns-deploy'
  scope: resourceGroup(dnsResourceGroupName)
  params: {
    cdnEndpointHostname: cdn.outputs.afdEndpointHostname
  }
}

output storageAccountName string = storage.outputs.storageAccountName
output functionAppName string = app.outputs.functionAppName
output cdnProfileName string = cdn.outputs.afdProfileName
output cdnEndpointName string = cdn.outputs.afdEndpointName
