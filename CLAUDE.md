# GasBlender — Claude guidance

## Project overview

Trimix gas blending calculator for technical diving. Python Azure Function API + static HTML frontend hosted on Azure Blob Storage.

## Structure

```
GasBlender/
├── TrimixBlend/__init__.py   # Azure HTTP trigger
├── TrimixBlend/function.json # Binding config
├── tests/                    # Unit tests (pytest)
├── gas_blender.py            # Core logic — single source of truth
├── web/                      # Static website assets (deployed to Azure Blob Storage, not Function App)
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── diver.jpg
├── host.json                 # Azure Functions runtime config
├── requirements.txt          # Pinned dependencies
├── .funcignore               # Excludes tests/, web/, README.md from deployment
└── infra/
    ├── main.bicep            # Subscription-scoped orchestration — creates resource group + all resources
    ├── main.bicepparam       # Parameter values (appName, environment, location, resourceGroupName, dnsResourceGroupName, customDomainHostname)
    └── modules/
        ├── storage.bicep     # StorageV2 storage account (Function App storage + static website)
        ├── functionApp.bicep # Log Analytics → App Insights → FC1 plan → Function App
        ├── cdn.bicep         # Azure Front Door Standard — profile, endpoint, origin, custom domain + managed TLS
        └── dns.bicep         # CNAME record in shared DNS zone (rg-dns-services-shared-001)
```

## Local development

### Prerequisites
- Python 3 with `.venv` at repo root
- [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)
- Node/npm for Azurite (`npm install -g azurite`)

### Start everything
Press **F5** in VS Code — starts the Function host (port 7071) and HTTP server for the frontend (port 8080) in parallel.

Or manually:
```bash
azurite --location .azurite          # local storage emulator
func host start                       # Azure Function on :7071
python -m http.server 8080 --directory web   # frontend on :8080
```

### CORS
`local.settings.json` configures CORS to allow `http://localhost:8080`. This file is gitignored to prevent accidental secret commits — copy `local.settings.example.json` to get started.

### Tests
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
28 tests covering `Gas`, `BlendStep`, `TrimixBlend`, and `topup_blend`.

## Conventions

- **Single source of truth**: all gas logic lives in `gas_blender.py`. `TrimixBlend/__init__.py` imports from it — never duplicate logic there.
- **Snake_case** for functions (`topup_blend`), PascalCase for classes (`Gas`, `TrimixBlend`, `BlendStep`).
- **No comments** unless the why is non-obvious.
- **Pinned dependencies** in `requirements.txt` (currently `azure-functions==1.24.0`).
- **Tests in `tests/`** — pytest, using plain `assert` and `pytest.approx`.

## Deployment

Push to `main` — GitHub Actions handles everything in order:

1. **Test** — pytest
2. **Deploy Infrastructure** — `az deployment sub create` with Bicep (idempotent); also enables HTTPS on the CDN custom domain
3. **Deploy Function App** + **Deploy Static Website** — run in parallel; static website deploy also purges the CDN cache

CI/CD uses OIDC federated identity (no stored secrets beyond `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`).

`app.js` auto-detects local vs production based on hostname — no changes needed between environments.

To test Bicep changes locally before pushing:
```bash
az bicep build --file infra/main.bicep                          # syntax check
az deployment sub what-if --location northeurope \              # dry run
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

## Azure resources

| Resource | Name | Notes |
|---|---|---|
| Resource group | `rg-gasblender-prod` | North Europe |
| Storage account | `stgasblendertcif7s` | Static website + Function App storage |
| Function App | `gasblender-tcif7s` | Flex Consumption (FC1), Python 3.11, 512 MB |
| App Service Plan | `asp-gasblender-prod` | FC1 / FlexConsumption |
| App Insights | `appi-gasblender-prod` | Workspace-based |
| Log Analytics | `log-gasblender-prod` | 30-day retention |
| Front Door profile | `afd-gasblender-prod` | Standard_AzureFrontDoor |
| Front Door endpoint | `gasblender-<token>` | Fronts storage static website, custom domain + managed TLS |

- Frontend: `https://gasblender.redkic.co.uk/` (CDN custom domain)
- Storage origin: `https://stgasblendertcif7s.z16.web.core.windows.net/`
- API endpoint: `https://gasblender-tcif7s.azurewebsites.net/api/TrimixBlend`
- Function auth: anonymous (no API key required)
- Extension bundle: `[4.*, 5.0.0)` (host.json)
