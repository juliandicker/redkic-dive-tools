# GasBlender

Two tools for technical diving, built on Python Azure Functions and a static HTML frontend hosted on Azure Static Web Apps.

| Tool | Description |
|------|-------------|
| **Gas Blender** | Trimix fill-sequence calculator — given a start cylinder and target mix, computes He → O₂ → air top-up steps |
| **Dive Planner** | Bühlmann ZHL-16C CCR decompression planner with GF Low/High, OC bailout planning, gas density analysis, tissue saturation chart, and OTU/CNS tracking |

## Project structure

```
GasBlender/
├── function_app.py         # ASGI entry point — FastAPI app, Pydantic models, both endpoints
├── DivePlanner/
│   └── __init__.py         # Helper module: CNS/OTU rates, gas consumption, binary search
├── planner/
│   ├── buhlmann.py         # ZHL-16C model: Schreiner equation, GF ceiling, tissue saturations
│   ├── dive.py             # CCR dive planner + OC bailout: descent, deco grid, profile points
│   └── gas.py              # CCRGas / OpenCircuitGas: pp_n2 / pp_he for each circuit type
├── tests/
│   ├── test_gas_blender.py          # 28 gas blender tests
│   ├── test_buhlmann.py             # Bühlmann model unit tests
│   ├── test_planner.py              # Dive planner integration tests
│   ├── ovm_reference.py             # OVM CCR reference data (Playwright-recorded)
│   ├── test_ovm_crossval.py         # OVM CCR cross-validation
│   ├── ovm_bailout_reference.py     # OVM OC bailout reference data (Playwright-recorded)
│   ├── test_ovm_bailout_crossval.py # OVM OC bailout cross-validation
│   └── test_openapi.py              # OpenAPI schema generation tests
├── infra/
│   ├── main.bicep          # Subscription-scoped Bicep — resource group + all resources
│   ├── main.bicepparam
│   └── modules/            # storage, functionApp, staticWebApp, swa-domain, dns
├── web/                    # React/Vite frontend (TypeScript)
│   ├── src/
│   │   ├── pages/          # GasBlender.tsx, DivePlanner.tsx
│   │   ├── components/     # Header, GasBar, PlanSection (charts + schedule)
│   │   ├── api.ts          # API client — auto-detects local vs prod URL
│   │   ├── utils.ts        # Gas calculations (density, best mix, naming)
│   │   └── types.ts        # TypeScript types for API and app state
│   ├── public/
│   │   └── staticwebapp.config.json  # SPA routing fallback
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── gas_blender.py          # Core blending logic (single source of truth)
├── host.json
├── requirements.txt
└── .funcignore
```

Deployment is fully automated via GitHub Actions — push to `main` to deploy.

## Hosting

| Component | Azure service | URL |
|-----------|--------------|-----|
| Gas Blender API | Azure Function App (Flex Consumption) | `https://gasblender-tcif7s.azurewebsites.net/api/TrimixBlend` |
| Dive Planner API | Azure Function App (Flex Consumption) | `https://gasblender-tcif7s.azurewebsites.net/api/DivePlanner` |
| Swagger UI | Azure Function App | `https://gasblender-tcif7s.azurewebsites.net/docs` |
| ReDoc | Azure Function App | `https://gasblender-tcif7s.azurewebsites.net/redoc` |
| OpenAPI schema | Azure Function App | `https://gasblender-tcif7s.azurewebsites.net/openapi.json` |
| Frontend | Azure Static Web Apps (Free) | [https://gasblender.redkic.co.uk/](https://gasblender.redkic.co.uk/) |

Infrastructure is defined in `infra/` as Bicep (subscription-scoped) and deployed via GitHub Actions on every push to `main`.

## API documentation

Interactive documentation is served directly from the Function App:

- **Swagger UI**: `/docs`
- **ReDoc**: `/redoc`
- **OpenAPI schema** (JSON): `/openapi.json`

The CI pipeline also exports `openapi.json` as a build artifact on every push to `main`.

### Gas Blender

**POST** `/api/TrimixBlend` — all pressures in bar, gas percentages as integers (0–100).

```json
{
  "start_bar": 50,
  "start_o2": 21,
  "start_he": 0,
  "finish_bar": 200,
  "finish_o2": 21,
  "finish_he": 35,
  "helium_bar": 250,
  "helium_o2": 0,
  "helium_he": 100
}
```

`helium_bar/o2/he` are optional (default: 250 bar pure helium). Returns HTTP 200 with the blend plan and gas analysis, or HTTP 400 for invalid inputs.

### Dive Planner

**POST** `/api/DivePlanner` — minimum required fields:

```json
{
  "diluent_o2": 10,
  "diluent_he": 70,
  "setpoint": 1.3,
  "depth_m": 60,
  "bottom_time_min": 20,
  "gf_low": 50,
  "gf_high": 80
}
```

Returns deco stops, total runtime, dive profile points (depth + ceiling + tissue saturations), gas density analysis, TTS, CNS%, and OTU. Optional fields include ascent/descent rates, last stop depth (3/4/5/6/9 m), CNS warning threshold, SAC rates, bailout gases with cylinder sizes, and per-gas supply analysis. See `/docs` for the full schema.

## Running locally

Requires [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local).

```bash
pip install -r requirements.txt
func host start          # API on :7071
cd web && npm run dev    # Vite dev server on :8080
```

### Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v   # 225 tests
```

## Gas blending logic

Three blend types are supported:

| Type | Sequence |
|------|----------|
| **Trimix** | Add He → Add O₂ → Top up with air |
| **Nitrox** | Add O₂ → Top up with air |
| **Top-up** | Mix two cylinders, calculate final composition |

If the helium bank runs short the calculator adds a second helium step using a fresh 250 bar bank before continuing.

## Tech stack

- Python 3.11 · FastAPI · Pydantic v2
- Azure Functions (ASGI / AsgiFunctionApp, Flex Consumption plan)
- Azure Static Web Apps — Free tier (custom domain, managed HTTPS)
- Application Insights + Log Analytics
- Bicep (IaC — subscription-scoped)
- GitHub Actions + OIDC (CI/CD — no stored credentials)
- React 18 · TypeScript · Vite 5 (frontend)
- Bootstrap 5.3 · react-bootstrap · Chart.js 4.4 · react-chartjs-2 (frontend UI)
