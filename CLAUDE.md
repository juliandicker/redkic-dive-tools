# GasBlender — Claude guidance

## Project overview

Trimix gas blending calculator for technical diving. Python Azure Function API + static HTML frontend hosted on Azure Blob Storage.

## Structure

```
GasBlender/
├── TrimixBlend/__init__.py   # Azure HTTP trigger
├── TrimixBlend/function.json # Binding config
├── tests/                    # Unit tests (unittest)
├── gas_blender.py            # Core logic — single source of truth
├── index.html                # Web UI (deployed to Azure Blob Storage, not Function App)
├── host.json                 # Azure Functions runtime config
├── requirements.txt          # Pinned dependencies
└── .funcignore               # Excludes tests/, index.html, README.md from deployment
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
python -m http.server 8080            # frontend on :8080
```

### CORS
`local.settings.json` configures CORS to allow `http://localhost:8080`. This file is gitignored.

### Tests
```bash
python -m unittest discover -s tests -v
```
28 tests covering `Gas`, `BlendStep`, `TrimixBlend`, and `topup_blend`.

## Conventions

- **Single source of truth**: all gas logic lives in `gas_blender.py`. `TrimixBlend/__init__.py` imports from it — never duplicate logic there.
- **Snake_case** for functions (`topup_blend`), PascalCase for classes (`Gas`, `TrimixBlend`, `BlendStep`).
- **No comments** unless the why is non-obvious.
- **Pinned dependencies** in `requirements.txt` (currently `azure-functions==1.24.0`).
- **Tests in `tests/`** — unittest, not pytest.

## Deployment

| Component | Target | How |
|-----------|--------|-----|
| API | Azure Function App | VS Code Azure extension or `func azure functionapp publish` |
| Frontend | Azure Blob Storage static website | Upload `index.html` manually or via Azure CLI |

The `index.html` environment selector auto-detects local vs production based on hostname — no changes needed between environments.

## Azure config

- Extension bundle: `[4.*, 5.0.0)` (host.json)
- Python runtime: v4
- Function auth: anonymous (no API key required)
- Application Insights: enabled with request sampling excluded
