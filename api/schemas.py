"""Only experiments actually precomputed by the simulator may be requested."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CAPACITY_GRID = (0, 1, 2, 3, 4, 5, 10, 15, 20)


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    org_code: str = Field(pattern=r'^[A-Z0-9]{3}$')
    scenario: Literal['baseline', 'strike', 'winter_dip', 'referral_surge'] = 'strike'
    stage: Literal['none', 'diagnosis', 'treatment'] = 'none'
    extra_capacity_pct: int = Field(default=0, ge=0, le=20)

    @field_validator('extra_capacity_pct')
    @classmethod
    def precomputed_grid(cls, value: int) -> int:
        if value not in CAPACITY_GRID:
            raise ValueError(f'Choose a precomputed capacity percentage: {CAPACITY_GRID}')
        return value

    @model_validator(mode='after')
    def supported_combination(self):
        if self.stage == 'none' and self.extra_capacity_pct:
            raise ValueError('Choose diagnosis or treatment when adding capacity')
        if self.scenario != 'strike' and self.extra_capacity_pct:
            raise ValueError('Added-capacity curves are precomputed for the five-day strike only')
        return self
