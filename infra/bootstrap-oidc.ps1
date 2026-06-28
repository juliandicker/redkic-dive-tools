# Bootstrap OIDC federated identity for GitHub Actions → Azure
#
# Run this once when setting up a new subscription (or from scratch).
# Idempotent — safe to re-run.
#
# Prerequisites:
#   az login  (with an account that has Owner on the target subscription
#              and at least Contributor on the DNS resource group)
#
# Usage:
#   .\bootstrap-oidc.ps1 -SubscriptionId <id>

param(
    [Parameter(Mandatory)]
    [string] $SubscriptionId,

    [string] $AppName           = 'github-gasblender',
    [string] $GitHubOrg         = 'juliandicker',
    [string] $GitHubRepo        = 'redkic-dive-tools',
    [string] $GitHubBranch      = 'main',

    # Shared DNS zone details (subscription that owns redkic.co.uk)
    [string] $DnsSubscriptionId = '4f370769-6921-4fff-af30-d2ad027af683',
    [string] $DnsResourceGroup  = 'rg-dns-services-shared-001'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step([string]$msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Skip([string]$msg) { Write-Host "    --: $msg (already exists)" -ForegroundColor DarkGray }

# ── 1. App registration ──────────────────────────────────────────────────────

Write-Step "App registration"

$existing = az ad app list --display-name $AppName | ConvertFrom-Json
if ($existing.Count -gt 0) {
    $app      = $existing[0]
    $clientId = $app.appId
    $objectId = $app.id
    Write-Skip $AppName
} else {
    $app      = az ad app create --display-name $AppName | ConvertFrom-Json
    $clientId = $app.appId
    $objectId = $app.id
    Write-Ok "Created app '$AppName' ($clientId)"
}

# ── 2. Service principal ─────────────────────────────────────────────────────

Write-Step "Service principal"

$sp = az ad sp list --filter "appId eq '$clientId'" | ConvertFrom-Json
if ($sp.Count -gt 0) {
    $spId = $sp[0].id
    Write-Skip "SP $spId"
} else {
    $sp   = az ad sp create --id $clientId | ConvertFrom-Json
    $spId = $sp.id
    Write-Ok "Created SP $spId"
}

# ── 3. Federated credential for GitHub Actions ───────────────────────────────

Write-Step "Federated credential (branch: $GitHubBranch)"

$subject     = "repo:${GitHubOrg}/${GitHubRepo}:ref:refs/heads/${GitHubBranch}"
$credName    = "github-${GitHubOrg}-${GitHubRepo}-${GitHubBranch}" -replace '[^a-zA-Z0-9-]', '-'
$existingFed = az ad app federated-credential list --id $objectId |
               ConvertFrom-Json |
               Where-Object { $_.subject -eq $subject }

if ($existingFed) {
    Write-Skip "subject=$subject"
} else {
    $fedParamsFile = [System.IO.Path]::GetTempFileName() + '.json'
    @{
        name        = $credName
        issuer      = 'https://token.actions.githubusercontent.com'
        subject     = $subject
        description = "GitHub Actions — $GitHubOrg/$GitHubRepo branch $GitHubBranch"
        audiences   = @('api://AzureADTokenExchange')
    } | ConvertTo-Json | Set-Content $fedParamsFile -Encoding UTF8

    az ad app federated-credential create --id $objectId --parameters "@$fedParamsFile" | Out-Null
    Remove-Item $fedParamsFile
    Write-Ok "Created federated credential for $subject"
}

# ── 4. Contributor on the new target subscription ────────────────────────────

Write-Step "Contributor on subscription $SubscriptionId"

$scope       = "/subscriptions/$SubscriptionId"
$existingRole = @(az role assignment list --assignee $spId --role Contributor --scope $scope |
                ConvertFrom-Json)

if ($existingRole.Count -gt 0) {
    Write-Skip "Contributor already assigned"
} else {
    az role assignment create --assignee $spId --role Contributor --scope $scope | Out-Null
    Write-Ok "Assigned Contributor on $scope"
}

# ── 5. DNS Zone Contributor on the shared DNS resource group ─────────────────

Write-Step "DNS Zone Contributor on $DnsResourceGroup (sub: $DnsSubscriptionId)"

$dnsScope     = "/subscriptions/$DnsSubscriptionId/resourceGroups/$DnsResourceGroup"
$existingDns  = @(az role assignment list --assignee $spId --role 'DNS Zone Contributor' --scope $dnsScope |
                ConvertFrom-Json)

if ($existingDns.Count -gt 0) {
    Write-Skip "DNS Zone Contributor already assigned"
} else {
    az role assignment create --assignee $spId --role 'DNS Zone Contributor' --scope $dnsScope | Out-Null
    Write-Ok "Assigned DNS Zone Contributor on $dnsScope"
}

# ── Summary ──────────────────────────────────────────────────────────────────

Write-Host ''
Write-Host '════════════════════════════════════════════' -ForegroundColor Yellow
Write-Host ' GitHub Actions secrets required:' -ForegroundColor Yellow
Write-Host "   AZURE_CLIENT_ID       = $clientId" -ForegroundColor White
Write-Host "   AZURE_TENANT_ID       = $(az account show --query tenantId -o tsv)" -ForegroundColor White
Write-Host "   AZURE_SUBSCRIPTION_ID = $SubscriptionId" -ForegroundColor White
Write-Host '════════════════════════════════════════════' -ForegroundColor Yellow
Write-Host ''
