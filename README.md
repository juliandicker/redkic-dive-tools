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
├── tests/
│   └── test_gas_blender.py  # Unit tests (28 tests, pytest)
├── infra/
│   ├── main.bicep      # Subscription-scoped Bicep — creates resource group + all resources
│   ├── main.bicepparam # Parameter values
│   └── modules/        # storage.bicep, functionApp.bicep, cdn.bicep, cdn-domain.bicep, dns.bicep
├── web/
│   ├── index.html      # Static web UI
│   ├── app.js          # Frontend logic
│   └── styles.css
├── gas_blender.py      # Core logic: Gas, BlendStep, TrimixBlend, topup_blend
├── host.json           # Azure Functions runtime config
├── requirements.txt    # Python dependencies
└── .funcignore         # Excludes tests/, web/, README.md from Azure deployment
```

Deployment is fully automated via GitHub Actions — push to `main` to deploy.

## Hosting

| Component | Azure service | URL |
|-----------|--------------|-----|
| API | Azure Function App (Flex Consumption) | [https://gasblender-tcif7s.azurewebsites.net/api/TrimixBlend](https://gasblender-tcif7s.azurewebsites.net/api/TrimixBlend) |
| Frontend | Azure CDN → Blob Storage static website | [https://gasblender.redkic.co.uk/](https://gasblender.redkic.co.uk/) |

Infrastructure is defined in `infra/` as Bicep (subscription-scoped) and deployed via GitHub Actions on every push to `main`.

### Backend

`TrimixBlend/__init__.py` is a Python Azure Functions v4 HTTP trigger. It accepts a JSON body, runs the blend calculation, and returns the result as JSON.

### Frontend

`web/index.html` + `web/app.js` is a single-page form (Bootstrap 5.3, native fetch) that posts to the Azure Function endpoint and renders the step-by-step blend plan. Served via Azure CDN at `gasblender.redkic.co.uk`.

## API

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
pip install -r requirements-dev.txt
pytest tests/ -v
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
- Azure Functions (Python v4 runtime, Flex Consumption plan)
- Azure Blob Storage (static website hosting) + Azure CDN (custom domain, HTTPS)
- Application Insights + Log Analytics (telemetry)
- Bicep (IaC — subscription-scoped, deploys all resources)
- GitHub Actions + OIDC (CI/CD — no stored credentials)
- Bootstrap 5.3 (native fetch, no jQuery)
