# src/schema.py
from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator, model_validator


class WindingType(str, Enum):
    MANUAL = "Manual"
    AUTOMATIC = "Automatic"


class AutoWindingMechanism(str, Enum):
    NONE = "None (Manual)"
    UNIDIRECTIONAL_PAWL = "Unidirectional (Pawl/Click)"
    BIDIRECTIONAL_REVERSER = "Bidirectional (Reversing Wheels)"
    MAGIC_LEVER = "Bidirectional (Seiko Magic Lever)"
    PELLATON = "Bidirectional (Pellaton Pawl)"
    BUMPER = "Bumper / Hammer"
    PERIPHERAL = "Peripheral Rotor"
    MICRO_ROTOR = "Micro-Rotor / Planetary"


class CertificationStandard(str, Enum):
    COSC = "COSC (ISO 3159)"
    METAS = "METAS (Master Chronometer)"
    GENEVA_SEAL = "Poinçon de Genève"
    QUALITE_FLEURIER = "Qualité Fleurier"
    JCS = "Japanese Chronometer (JCS)"
    OBSERVATORY = "Observatory Tested"
    ISO_6425 = "ISO 6425 (Diver's Watch)"
    ISO_22810 = "ISO 22810 (Standard Water Resistance)"
    MANUFACTURER_INTERNAL = "Manufacturer Internal Spec"


class MovementSpec(BaseModel):
    caliber_id: str = Field(
        ...,
        pattern=r"^[a-z0-9_]+$",
        description="Unique lowercase slug, e.g., 'eta_6497_1' or 'omega_1120'",
    )
    manufacturer: str = Field(..., min_length=1)
    caliber_number: str = Field(..., min_length=1)
    base_caliber: Optional[str] = Field(
        None, description="Parent movement if derived, e.g., 'ETA 2892-A2'"
    )
    winding_type: WindingType
    winding_mechanism: AutoWindingMechanism
    escapement_type: str = Field(
        default="Swiss Lever",
        description="e.g., Swiss Lever, Co-Axial, Detent, Spring Detent",
    )
    frequency_vph: int = Field(
        ..., description="Vibrations per hour, e.g., 18000, 21600, 25200, 28800, 36000"
    )
    jewels: int = Field(..., ge=0, le=100)
    power_reserve_hours: float = Field(..., gt=0, le=2400)
    hacking: bool = False
    hand_winding: bool = True
    description: str = Field(..., min_length=10)

    @field_validator("frequency_vph")
    @classmethod
    def check_mechanical_frequency(cls, v: int) -> int:
        # Guardrail against accidental quartz entries (e.g., 32,768 Hz)
        if v < 7200 or v > 72000:
            raise ValueError(
                f"Frequency {v} vph is outside mechanical bounds (7,200 to 72,000 vph)."
            )
        return v

    @model_validator(mode="after")
    def check_winding_consistency(self) -> "MovementSpec":
        if (
            self.winding_type == WindingType.MANUAL
            and self.winding_mechanism != AutoWindingMechanism.NONE
        ):
            raise ValueError(
                "Manual movements must have winding_mechanism set to 'None (Manual)'."
            )
        if (
            self.winding_type == WindingType.AUTOMATIC
            and self.winding_mechanism == AutoWindingMechanism.NONE
        ):
            raise ValueError(
                "Automatic movements must specify an automatic winding_mechanism."
            )
        return self


class TestAndCertification(BaseModel):
    standard: CertificationStandard
    rated_accuracy_sec_per_day: Optional[Tuple[float, float]] = Field(
        None,
        description="(max_loss, max_gain) in sec/day, e.g., (-4.0, 6.0) for COSC",
    )
    water_resistance_bar: Optional[float] = Field(
        None, ge=0, description="Pressure passed in bar/ATM"
    )
    water_resistance_meters: Optional[int] = Field(None, ge=0)
    magnetic_resistance_gauss: Optional[int] = Field(
        None, ge=0, description="e.g., 15000 for METAS"
    )
    test_notes: Optional[str] = None


class WatchReference(BaseModel):
    watch_id: str = Field(
        ...,
        pattern=r"^[a-z0-9_]+$",
        description="Unique lowercase slug, e.g., 'omega_seamaster_2254_50'",
    )
    brand: str = Field(..., min_length=1)
    model_family: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    reference_numbers: List[str] = Field(..., min_length=1)
    caliber_id: str = Field(
        ..., description="Foreign key matching MovementSpec.caliber_id"
    )
    production_year_start: Optional[int] = Field(None, ge=1500, le=2035)
    production_year_end: Optional[int] = Field(
        None, ge=1500, le=2035, description="Leave null/None if still in production"
    )
    tests_passed: List[TestAndCertification] = Field(default_factory=list)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def check_production_years(self) -> "WatchReference":
        if (
            self.production_year_start is not None
            and self.production_year_end is not None
            and self.production_year_end < self.production_year_start
        ):
            raise ValueError(
                f"production_year_end ({self.production_year_end}) cannot be earlier "
                f"than production_year_start ({self.production_year_start})."
            )
        return self 
