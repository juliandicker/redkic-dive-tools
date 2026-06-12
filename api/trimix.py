import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gas_blender import Gas, TrimixBlend, density_depth, end_depth, mod_m

router = APIRouter()


class GasComposition(BaseModel):
    bar: float
    o2: float
    he: float


class FillStep(BaseModel):
    """One step in a cylinder fill sequence (He top-up, O₂ top-up, or air top-up).

    Named FillStep rather than BlendStep to avoid confusion with gas_blender.BlendStep,
    which is the internal domain class for the same concept.
    """
    name: str
    start_gas: GasComposition
    result_gas: GasComposition


class GasAnalysis(BaseModel):
    mod_1_2: float = Field(description="MOD at ppO₂ 1.2 bar (m)")
    mod_1_4: float = Field(description="MOD at ppO₂ 1.4 bar (m)")
    mod_1_6: float = Field(description="MOD at ppO₂ 1.6 bar (m)")
    density_max_depth: float = Field(description="Depth at BSAC recommended density limit 5.2 g/L (m)")
    density_limit_depth: float = Field(description="Depth at BSAC upper density limit 6.3 g/L (m)")
    end_30_depth: float = Field(description="Depth where END reaches 30 m (m)")
    end_40_depth: float = Field(description="Depth where END reaches 40 m (m)")


class TrimixBlendRequest(BaseModel):
    """Cylinder fill parameters for a trimix top-up sequence."""
    start_bar: float = Field(gt=0, description="Starting cylinder pressure (bar)")
    start_o2: float = Field(ge=0, le=100, description="Starting O₂ (%)")
    start_he: float = Field(ge=0, le=100, description="Starting He (%)")
    finish_bar: float = Field(gt=0, description="Target cylinder pressure (bar)")
    finish_o2: float = Field(ge=0, le=100, description="Target O₂ (%)")
    finish_he: float = Field(ge=0, le=100, description="Target He (%)")
    helium_bar: float = Field(default=250.0, gt=0, description="Helium source pressure (bar)")
    helium_o2: float = Field(default=0.0, ge=0, le=100, description="Helium source O₂ (%)")
    helium_he: float = Field(default=100.0, ge=0, le=100, description="Helium source He (%)")


class TrimixBlendResponse(BaseModel):
    """Fill steps and gas analysis for the requested blend."""
    start_gas: GasComposition
    finish_gas: GasComposition
    he_gas: GasComposition
    steps: List[FillStep]
    analysis: GasAnalysis


@router.post(
    "/api/TrimixBlend",
    response_model=TrimixBlendResponse,
    summary="Trimix fill sequence",
    description=(
        "Computes the helium → O₂ → air fill steps required to reach the target "
        "trimix from the starting cylinder contents."
    ),
    responses={400: {"description": "Invalid inputs or infeasible blend", "content": {"text/plain": {}}}},
)
def trimix_blend(req: TrimixBlendRequest) -> TrimixBlendResponse:
    logging.info("TrimixBlend request received.")
    start_gas  = Gas(req.start_bar,  req.start_o2,  req.start_he)
    finish_gas = Gas(req.finish_bar, req.finish_o2, req.finish_he)
    helium_gas = Gas(req.helium_bar, req.helium_o2, req.helium_he)
    try:
        result = TrimixBlend(start_gas, finish_gas, helium_gas)
    except (ValueError, ZeroDivisionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TrimixBlendResponse(
        start_gas=GasComposition(bar=result.start_gas.bar, o2=result.start_gas.o2, he=result.start_gas.he),
        finish_gas=GasComposition(bar=result.finish_gas.bar, o2=result.finish_gas.o2, he=result.finish_gas.he),
        he_gas=GasComposition(bar=result.he_gas.bar, o2=result.he_gas.o2, he=result.he_gas.he),
        steps=[
            FillStep(
                name=s.name,
                start_gas=GasComposition(bar=s.start_gas.bar, o2=s.start_gas.o2, he=s.start_gas.he),
                result_gas=GasComposition(bar=s.result_gas.bar, o2=s.result_gas.o2, he=s.result_gas.he),
            )
            for s in result.steps
        ],
        analysis=GasAnalysis(
            mod_1_2=mod_m(req.finish_o2, 1.2),
            mod_1_4=mod_m(req.finish_o2, 1.4),
            mod_1_6=mod_m(req.finish_o2, 1.6),
            density_max_depth=density_depth(req.finish_o2, req.finish_he, 5.2),
            density_limit_depth=density_depth(req.finish_o2, req.finish_he, 6.3),
            end_30_depth=end_depth(req.finish_o2, req.finish_he, 30),
            end_40_depth=end_depth(req.finish_o2, req.finish_he, 40),
        ),
    )
