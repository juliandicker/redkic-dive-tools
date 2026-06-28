targetScope = 'subscription'

param appName string = 'gasblender'
param location string = 'northeurope'
param environment string = 'prod'
param resourceGroupName string = 'rg-gasblender-prod'
param dnsSubscriptionId string
param dnsResourceGroupName string = 'rg-dns-services-shared-001'
param customDomainHostname string = 'divetools.redkic.co.uk'
param subDomainLabel string = 'divetools'

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: resourceGroupName
  location: location
}

var resourceToken = take(uniqueString(rg.id), 6)
var storageAccountName = toLower('st${replace(appName, '-', '')}${resourceToken}')
var staticWebAppName = '${appName}-${resourceToken}'

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

module swa 'modules/staticWebApp.bicep' = {
  name: 'swa-deploy'
  scope: rg
  params: {
    staticWebAppName: staticWebAppName
  }
}

module dns 'modules/dns.bicep' = {
  name: 'dns-deploy'
  scope: resourceGroup(dnsSubscriptionId, dnsResourceGroupName)
  params: {
    targetHostname: swa.outputs.defaultHostname
    subDomainLabel: subDomainLabel
  }
}

module swaDomain 'modules/swa-domain.bicep' = {
  name: 'swa-domain-deploy'
  scope: rg
  params: {
    staticWebAppName: swa.outputs.staticWebAppName
    customDomainHostname: customDomainHostname
  }
  dependsOn: [dns]
}

module gasblenderDns 'modules/dns.bicep' = {
  name: 'gasblender-dns-deploy'
  scope: resourceGroup(dnsSubscriptionId, dnsResourceGroupName)
  params: {
    targetHostname: swa.outputs.defaultHostname
    subDomainLabel: 'gasblender'
  }
}

module gasblenderSwaDomain 'modules/swa-domain.bicep' = {
  name: 'gasblender-swa-domain-deploy'
  scope: rg
  params: {
    staticWebAppName: swa.outputs.staticWebAppName
    customDomainHostname: 'gasblender.redkic.co.uk'
  }
  dependsOn: [gasblenderDns]
}

output storageAccountName string = storage.outputs.storageAccountName
output functionAppName string = app.outputs.functionAppName
output staticWebAppName string = swa.outputs.staticWebAppName
output deployedResourceGroupName string = rg.name
