# GasBlender

Two tools for technical diving, built on Python Azure Functions and a static HTML frontend hosted on Azure Static Web Apps.

| Tool | Description |
|------|-------------|
| **Gas Blender** | Trimix fill-sequence calculator — given a start cylinder and target mix, computes He → O₂ → air top-up steps |
| **Dive Planner** | Bühlmann ZHL-16C CCR decompression planner with gas density analysis, tissue saturation chart, and OTU/CNS tracking |

## Project structure

```
GasBlender/
├── TrimixBlend/
│   ├── __init__.py         # Azure HTTP trigger — gas blending
│   └── function.json
├── DivePlanner/
│   ├── __init__.py         # Azure HTTP trigger — decompression planning
│   └── function.json
├── planner/
│   ├── buhlmann.py         # ZHL-16C model: Schreiner equation, GF ceiling, tissue saturations
│   ├── dive.py             # CCR dive planner: descent, deco grid, profile points
│   └── gas.py              # CCRGas: pp_n2 / pp_he respecting setpoint
├── tests/
│   ├── test_gas_blender.py     # 28 gas blender tests
│   ├── test_buhlmann.py        # Bühlmann model unit tests
│   ├── test_planner.py         # Dive planner integration tests
│   └── test_ovm_crossval.py    # OVM cross-validation (reference dives)
├── infra/
│   ├── main.bicep          # Subscription-scoped Bicep — resource group + all resources
│   ├── main.bicepparam
│   └── modules/            # storage, functionApp, staticWebApp, swa-domain, dns
├── web/
│   ├── index.html          # Gas Blender UI
│   ├── app.js
│   ├── planner.html        # Dive Planner UI
│   ├── planner.js
│   └── styles.css
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
| Frontend | Azure Static Web Apps (Free) | [https://gasblender.redkic.co.uk/](https://gasblender.redkic.co.uk/) |

Infrastructure is defined in `infra/` as Bicep (subscription-scoped) and deployed via GitHub Actions on every push to `main`.

## Gas Blender API

**POST** `https://gasblender-tcif7s.azurewebsites.net/api/TrimixBlend`

All pressures in bar, gas percentages as integers (0–100).

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

`helium_bar/o2/he` are optional — omit for a default 250 bar pure-helium bank.

Returns HTTP 200 with a JSON blend plan, or HTTP 400 if parameters are missing or invalid.

## Dive Planner API

**POST** `https://gasblender-tcif7s.azurewebsites.net/api/DivePlanner`

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

Returns deco stops, total runtime, dive profile points (depth + ceiling + tissue saturations at each point), final tissue saturations, gas density analysis, TTS, CNS%, and OTU.

## Running locally

Requires [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local).

```bash
pip install -r requirements.txt
func host start                              # API on :7071
python -m http.server 8080 --directory web  # frontend on :8080
```

### Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v   # 174 tests
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

- Python 3.11
- Azure Functions (Python v4 runtime, Flex Consumption plan)
- Azure Static Web Apps — Free tier (custom domain, managed HTTPS)
- Application Insights + Log Analytics
- Bicep (IaC — subscription-scoped)
- GitHub Actions + OIDC (CI/CD — no stored credentials)
- Bootstrap 5.3 · Chart.js 4.4 (frontend)
