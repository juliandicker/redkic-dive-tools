# GasBlender — Claude guidance

## Project overview

Two tools for technical diving. Python Azure Functions API (FastAPI + ASGI) + React/Vite frontend hosted on Azure Static Web Apps (Free tier).

- **Gas Blender** — fill-sequence calculator: He → O₂ → air top-up steps
- **Dive Planner** — Bühlmann ZHL-16C CCR decompression planner with GF Low/High, gas density analysis, tissue saturation tracking, OTU/CNS

## Structure

```
GasBlender/
├── function_app.py           # ASGI entry point — FastAPI app, Pydantic models, both endpoints
├── DivePlanner/__init__.py   # Helper module: CNS/OTU rates, gas consumption, binary search (tests import from here)
├── planner/
│   ├── buhlmann.py           # ZHL-16C: Schreiner equation, GF ceiling, tissue saturations
│   ├── dive.py               # CCR dive planner: descent, deco grid, profile points
│   └── gas.py                # CCRGas: pp_n2 / pp_he respecting setpoint
├── tests/                    # Unit tests (pytest) — 213 tests total
├── gas_blender.py            # Core blending logic — single source of truth
├── web/                      # React/Vite frontend (TypeScript)
│   ├── src/
│   │   ├── main.tsx          # React entry point
│   │   ├── App.tsx           # React Router — / and /planner
│   │   ├── styles.css        # Global CSS (CSS variables, shared components)
│   │   ├── types.ts          # TypeScript types for API and app state
│   │   ├── api.ts            # API client (auto-detects local vs prod URL)
│   │   ├── utils.ts          # Gas calculations (density, best mix, gas naming)
│   │   ├── storage.ts        # localStorage helpers
│   │   ├── components/
│   │   │   ├── Header.tsx    # App header with nav offcanvas
│   │   │   ├── GasBar.tsx    # Gas composition bar component
│   │   │   └── PlanSection.tsx # Profile+tissue charts, schedule table, metrics
│   │   └── pages/
│   │       ├── GasBlender.tsx  # Gas Blender page (/)
│   │       └── DivePlanner.tsx # Dive Planner page (/planner)
│   ├── public/
│   │   ├── diver.jpg
│   │   ├── redkic_diving_tools_logo.png
│   │   └── staticwebapp.config.json  # SPA routing fallback
│   ├── index.html            # Vite HTML entry
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── host.json                 # Azure Functions runtime config (routePrefix: "")
├── requirements.txt          # Pinned dependencies
├── .funcignore               # Excludes tests/, web/, README.md from deployment
└── infra/
    ├── main.bicep            # Subscription-scoped orchestration — creates resource group + all resources
    ├── main.bicepparam       # Parameter values (appName, environment, location, resourceGroupName, dnsResourceGroupName, customDomainHostname)
    └── modules/
        ├── storage.bicep     # StorageV2 storage account (Function App storage + static website)
        ├── functionApp.bicep # Log Analytics → App Insights → FC1 plan → Function App
        ├── staticWebApp.bicep # Azure Static Web Apps (Free tier)
        ├── swa-domain.bicep   # Custom domain attachment (CNAME delegation)
        └── dns.bicep          # CNAME record in shared DNS zone (rg-dns-services-shared-001)
```

## Local development

### Prerequisites
- Python 3 with `.venv` at repo root
- [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)
- Node/npm for Azurite (`npm install -g azurite`)

### Start everything
Press **F5** in VS Code — starts the Function host (port 7071) and Vite dev server (port 8080) in parallel.

Or manually:
```bash
azurite --location .azurite          # local storage emulator
func host start                       # Azure Function on :7071
cd web && npm run dev                 # Vite dev server on :8080
```

### CORS
`local.settings.json` configures CORS to allow `http://localhost:8080`. This file is gitignored to prevent accidental secret commits — copy `local.settings.example.json` to get started.

### Tests
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
213 tests: 28 covering `Gas`, `BlendStep`, `TrimixBlend`, `topup_blend`; 3 covering OpenAPI schema generation; the rest cover the Bühlmann model, CCR dive planner, and OVM cross-validation.

## Pre-approved permissions

The following are already in the allowlists (`.claude/settings.json` and `.claude/settings.local.json`) — no need to ask before running these:

- **Tests**: `.venv\Scripts\pytest tests/ -v`, `.venv\Scripts\pytest tests/ -q`, `python -m pytest tests/`
- **Dev server**: `func host start`, `cd web && npm run dev`, `azurite`
- **Frontend build**: `cd web && npm ci`, `cd web && npm run build`
- **Dependencies**: `pip install -r requirements.txt`, `pip install -r requirements-dev.txt`, `pip install *`
- **Azure CLI**: `az bicep *`, `az deployment *`
- **Git**: `git add *`, `git commit`, `git push`, `git rm`, `git mv`
- **GitHub CLI**: `gh run *`, `gh pr *`
- **Browser automation (Playwright MCP)**: navigate, snapshot, screenshot, click, fill, type, hover, press key, drag, select, evaluate, wait, console messages
- **GitHub MCP**: `mcp__github__get_me`, `mcp__github__issue_read`, `mcp__github__issue_write`
- **Web**: `WebSearch`, `WebFetch` for docs and reference sites

## Conventions

- **Single source of truth**: all gas blending logic lives in `gas_blender.py`; all decompression logic lives in `planner/`. `function_app.py` only handles HTTP contract (parsing, validation, response shaping) and calls into those modules.
- **Warnings belong in the API**: all safety warnings (ppO₂ floor, gas density) are generated in `function_app.py` and returned as a `warnings` array (`[{level, message}]`). The frontend (and any future client) only renders them — no warning logic in the UI.
- **FastAPI + Pydantic v2** for the HTTP layer: Pydantic models in `function_app.py` are the contract. Cross-field validation (GF ordering, bottom-time vs descent-time) uses `@model_validator`. Plain-text error responses are preserved for frontend compatibility via custom exception handlers.
- **Snake_case** for functions (`topup_blend`), PascalCase for classes (`Gas`, `TrimixBlend`, `BlendStep`, Pydantic models).
- **No comments** unless the why is non-obvious.
- **Pinned dependencies** in `requirements.txt` (`azure-functions==1.24.0`, `fastapi>=0.115.0`, `pydantic>=2.0.0`).
- **Tests in `tests/`** — pytest, using plain `assert` and `pytest.approx`.

## Deployment

Push to `main` — GitHub Actions handles everything in order:

1. **Test** — pytest
2. **Deploy Infrastructure** — `az deployment sub create` with Bicep (idempotent); also enables HTTPS on the CDN custom domain
3. **Deploy Function App** + **Deploy Static Website** — run in parallel; static website deploy uses the SWA deploy action (token retrieved via OIDC at deploy time)

CI/CD uses OIDC federated identity (no stored secrets beyond `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`).

`api.ts` auto-detects local vs production based on `window.location.hostname` — no changes needed between environments. The CI/CD pipeline runs `npm ci && npm run build` in `web/` and deploys `web/dist/` to Azure Static Web Apps.

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
| Static Web App | `gasblender-<token>` | Free tier, global distribution, managed TLS |

- Frontend: `https://gasblender.redkic.co.uk/` (SWA custom domain)
- Gas Blender API: `https://gasblender-tcif7s.azurewebsites.net/api/TrimixBlend`
- Dive Planner API: `https://gasblender-tcif7s.azurewebsites.net/api/DivePlanner`
- Swagger UI: `https://gasblender-tcif7s.azurewebsites.net/docs`
- ReDoc: `https://gasblender-tcif7s.azurewebsites.net/redoc`
- OpenAPI schema: `https://gasblender-tcif7s.azurewebsites.net/openapi.json`
- Function auth: anonymous (no API key required)
- Extension bundle: `[4.*, 5.0.0)` (host.json)
