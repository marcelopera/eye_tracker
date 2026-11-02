"""Versioned processing inputs. Measurements must come from the session operator."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Capture(Strict):
    rotation_degrees: Literal[0, 90, 180, 270]
    mirrored: bool


class Geometry(Strict):
    screen_width_px: int = Field(gt=0)
    screen_height_px: int = Field(gt=0)
    screen_width_mm: float = Field(gt=0)
    screen_height_mm: float = Field(gt=0)
    camera_x_mm: FiniteFloat
    camera_y_mm: FiniteFloat
    # Map model centimeters to screen-oriented centimeters; translation is the camera.
    model_axes: tuple[tuple[FiniteFloat, FiniteFloat], tuple[FiniteFloat, FiniteFloat]]
    measurement_evidence: str = Field(min_length=1, max_length=2000)
    axes_evidence: str = Field(min_length=1, max_length=2000)
    # Effective original-video content rectangle in screen pixels, including crop/letterbox.
    stimulus_rect: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    stimulus_width_px: int = Field(gt=0)
    stimulus_height_px: int = Field(gt=0)
    stimulus_coordinate_space: Literal["encoded", "display"] = "encoded"

    @model_validator(mode="after")
    def check(self):
        if self.stimulus_rect[2] <= 0 or self.stimulus_rect[3] <= 0:
            raise ValueError("Retângulo do estímulo deve ter dimensões positivas")
        a, b = self.model_axes
        if abs(a[0] * b[1] - a[1] * b[0]) < 1e-8:
            raise ValueError("Transformação espacial singular")
        return self


class Anchor(Strict):
    camera_ns: int
    event_ns: int


class PresentedFrame(Strict):
    event_ns: int
    media_time_ms: float = Field(ge=0)
    duration_ms: float = Field(gt=0)
    media_duration_ms: float | None = Field(default=None, gt=0)


class Synchronization(Strict):
    method: str = Field(min_length=1, max_length=2000)
    evidence: str = Field(min_length=1, max_length=2000)
    event_clock: str = Field(min_length=1)
    anchors: list[Anchor] = Field(min_length=3, max_length=10000)
    measurement_error_ms: float = Field(ge=0)
    max_error_ms: float = Field(gt=0)
    presented_frames: list[PresentedFrame] = Field(default_factory=list, max_length=100000)

    @model_validator(mode="after")
    def ordered(self):
        for field, key in ((self.anchors, "camera_ns"), (self.anchors, "event_ns"),
                           (self.presented_frames, "event_ns")):
            values = [getattr(row, key) for row in field]
            if any(b <= a for a, b in zip(values, values[1:])):
                raise ValueError("Tempos devem ser estritamente crescentes")
        return self


class Target(Strict):
    phase: Literal["calibration", "validation"]
    start_ns: int
    end_ns: int
    x_px: FiniteFloat
    y_px: FiniteFloat

    @model_validator(mode="after")
    def interval(self):
        if self.end_ns <= self.start_ns:
            raise ValueError("Intervalo do alvo vazio")
        return self


class Calibration(Strict):
    kernel: Literal["linear", "rbf"]
    C: float = Field(gt=0)
    epsilon: float = Field(ge=0)
    gamma: float = Field(gt=0)
    min_samples: int = Field(ge=3)
    min_targets: int = Field(ge=3)


class Criteria(Strict):
    max_mean_error_px: float = Field(gt=0)
    max_invalid_fraction: float = Field(ge=0, le=1)


class ProcessingConfig(Strict):
    schema_version: Literal[1]
    capture: Capture
    demonstration: bool = False
    geometry: Geometry | None = None
    synchronization: Synchronization | None = None
    targets: list[Target] = Field(default_factory=list, max_length=10000)
    calibration: Calibration | None = None
    criteria: Criteria | None = None
    export_features: bool = False
    preview_frames: int = Field(default=3, ge=0, le=20)

    @model_validator(mode="after")
    def targets_do_not_overlap(self):
        ordered = sorted(self.targets, key=lambda t: t.start_ns)
        if any(a.end_ns > b.start_ns for a, b in zip(ordered, ordered[1:])):
            raise ValueError("Intervalos de alvos não podem se sobrepor")
        return self
