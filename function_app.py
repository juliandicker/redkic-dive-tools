import azure.functions as func
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse

from api.trimix import router as trimix_router
from api.dive_planner import router as deco_router

fastapi_app = FastAPI(
    title="GasBlender API",
    description=(
        "Technical diving tools: trimix fill-sequence calculator and "
        "CCR decompression planner (Bühlmann ZHL-16C with gradient factors)."
    ),
    version="1.0.0",
    contact={"name": "GasBlender", "url": "https://gasblender.redkic.co.uk"},
)


@fastapi_app.exception_handler(HTTPException)
async def _http_exc(request, exc):
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


@fastapi_app.exception_handler(RequestValidationError)
async def _validation_exc(request, exc):
    errors = "; ".join(
        f"{' > '.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in exc.errors()
    )
    return PlainTextResponse(f"Validation error: {errors}", status_code=400)


fastapi_app.include_router(trimix_router)
fastapi_app.include_router(deco_router)

app = func.AsgiFunctionApp(app=fastapi_app, http_auth_level=func.AuthLevel.ANONYMOUS)
