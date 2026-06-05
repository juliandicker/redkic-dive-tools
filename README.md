# GasBlender

A trimix gas blending calculator for technical diving. Given a starting cylinder composition and a target gas mix, it computes the step-by-step blending procedure (helium → oxygen → air top-up) needed to achieve that mixture.

## What it does

Technical divers breathe gas mixtures containing oxygen, helium, and nitrogen (trimix) or just oxygen and nitrogen (nitrox). Blending these gases from banks and cylinders requires precise sequencing — add too much of one component and the final mix is wrong. GasBlender automates this calculation.

You provide:
- **Start gas** — the existing contents of the cylinder (pressure in bar, O₂%, He%)
- **Finish gas** — the target mixture and final pressure
- **Helium bank** — the available He supply (pressure in bar, O₂%, He%)

It returns the ordered steps: how much helium to add, how much oxygen to add, and how much air to top up with, along with the intermediate pressure and composition at each stage.

## Project structure

```
GasBlender/
├── TrimixBlend/
│   ├── __init__.py     # Azure HTTP trigger — parses request, calls gas_blender
│   └── function.json   # Binding config (HTTP POST)
├── gas_blender.py      # Core logic: Gas, BlendStep, TrimixBlend, topup_blend
├── test_gas_blender.py # Unit tests (28 tests, unittest)
├── index.html          # Static web UI (hosted on Azure Blob Storage)
├── host.json           # Azure Functions runtime config
├── requirements.txt    # Python dependencies
└── .funcignore         # Excludes tests/venv from Azure deployment
```

The repo root is the Azure Function app — deploy it directly with the Azure Functions Core Tools or VS Code extension.

## Hosting

| Component | Azure service |
|-----------|--------------|
| API | Azure Function App (`gasblender.azurewebsites.net`) |
| Frontend | Azure Blob Storage static website |

### Backend

`TrimixBlend/__init__.py` is a Python Azure Functions v4 HTTP trigger. It accepts a JSON body, runs the blend calculation, and returns the result as JSON.

Endpoint: `https://gasblender.azurewebsites.net/api/TrimixBlend`

### Frontend

`index.html` is a single-page form (jQuery + Bootstrap 5) that posts to the Azure Function endpoint and renders the step-by-step blend plan.

## API

**POST** `https://gasblender.azurewebsites.net/api/TrimixBlend`

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

`helium_bar/o2/he` are optional — omit them to use a default 250 bar pure-helium bank.

Returns HTTP 200 with a JSON blend plan, or HTTP 400 if parameters are missing or invalid.

## Running locally

Requires the [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local).

```bash
pip install -r requirements.txt
func host start
```

### Tests

```bash
python -m unittest test_gas_blender -v
```

## Gas blending logic

Three blend types are supported:

| Type | Sequence |
|------|----------|
| **Trimix** | Add He → Add O₂ → Top up with air |
| **Nitrox** | Add O₂ → Top up with air |
| **Top-up** | Mix two cylinders, calculate final composition |

If the helium bank runs short during a trimix blend, the calculator adds a second helium step using a fresh 250 bar bank before continuing with oxygen and air.

## Tech stack

- Python 3
- Azure Functions (Python v4 runtime, extension bundle 4.x)
- Azure Blob Storage (static website hosting)
- Application Insights (telemetry sampling)
- jQuery 3.6.0 + Bootstrap 5.2.0
