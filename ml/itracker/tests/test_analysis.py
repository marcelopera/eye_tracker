import numpy as np
import pytest
from pydantic import ValidationError

from analysis import Timeline, calibrate, evaluate, screen_point, stimulus_point
from config import ProcessingConfig
from preprocess import crop, face_grid, DetectionFailure


def config(**values):
    return ProcessingConfig.model_validate({"schema_version": 1, "capture": {"rotation_degrees": 0, "mirrored": False}, **values})


def sync(**values):
    return {"method": "synthetic measured anchors", "evidence": "test only", "event_clock": "test_clock",
            "anchors": [{"camera_ns": t, "event_ns": 1000000000000000 + t * 1.00001} for t in (0, 1000000000, 2000000000)],
            "measurement_error_ms": .1, "max_error_ms": .2,
            "presented_frames": [{"event_ns": 1000000000000000, "media_time_ms": 40, "duration_ms": 20}], **values}


def test_timeline_uses_bounded_measured_mapping_and_presented_frames():
    timeline = Timeline(config(synchronization=sync()).synchronization)
    assert timeline.report["status"] == "available"
    assert timeline.report["drift_ppm"] == pytest.approx(10, abs=.001)
    assert timeline.event_time(-1) is None
    assert timeline.event_time(2000000001) is None
    assert timeline.stimulus_time(timeline.event_time(10000000)) == (40, None)
    assert timeline.stimulus_time(timeline.event_time(50000000))[0] is None
    rejected = Timeline(config(synchronization=sync(measurement_error_ms=1)).synchronization)
    assert rejected.report["status"] == "rejected" and rejected.event_time(10) is None


def test_geometry_preserves_points_outside_video_and_non_square_physical_scale():
    g = config(geometry={"screen_width_px": 1000, "screen_height_px": 2000,
                        "screen_width_mm": 100, "screen_height_mm": 200,
                        "camera_x_mm": 50, "camera_y_mm": -5, "model_axes": [[1, 0], [0, -1]],
                        "measurement_evidence": "synthetic", "axes_evidence": "synthetic",
                        "stimulus_rect": [100, 500, 800, 1000], "stimulus_width_px": 1600, "stimulus_height_px": 1000}).geometry
    assert screen_point([0, -10.5], g) == [500, 1000]
    assert stimulus_point([500, 1000], g) == [800, 500]
    assert stimulus_point([-100, 100], g) == [-400, -400]


def test_calibration_never_fits_validation_targets():
    cfg = config(calibration={"kernel": "linear", "C": 1000, "epsilon": 0, "gamma": 1, "min_samples": 3, "min_targets": 3})
    def rows(validation_target):
        result = [{"valid": True, "phase": "calibration", "features": [float(i), 0.], "target_px": [float(i * 10), float(i * 20)],
                   "screen_px": [0., 0.], "calibrated_screen_px": None} for i in range(3)]
        result.append({"valid": True, "phase": "validation", "features": [1., 0.], "target_px": validation_target,
                       "screen_px": [0., 0.], "calibrated_screen_px": None})
        return result
    a, b = rows([10., 20.]), rows([9000., -8000.])
    assert calibrate(a, cfg)["status"] == "available"
    calibrate(b, cfg)
    assert a[-1]["calibrated_screen_px"] == b[-1]["calibrated_screen_px"]
    assert evaluate(a, None, None)["calibrated"]["mean_error_px"] < .1
    assert calibrate(a[:2], cfg)["reason"] == "insufficient_calibration"


def test_grid_matlab_rounding_row_order_and_repeated_edges():
    grid = face_grid([2, 4, 4, 6], 100, 100).reshape(25, 25)
    assert grid[1:3, 1:2].sum() == 2 and grid.sum() == 2
    image = np.arange(4 * 4 * 3, dtype=np.uint8).reshape(4, 4, 3)
    padded = crop(image, [-1, -1, 3, 3])
    assert np.array_equal(padded[0, 0], image[0, 0])
    assert np.array_equal(padded[2, 2], image[1, 1])
    with pytest.raises(DetectionFailure):
        crop(image, [10, 0, 2, 2])
    with pytest.raises(ValidationError):
        config(targets=[{"phase": "validation", "start_ns": 1, "end_ns": 1, "x_px": 0, "y_px": 0}])


def test_preprocessing_keeps_bgr_scale_nchw_and_anatomical_eye_order():
    from types import SimpleNamespace
    from preprocess import Preprocessor
    points = [SimpleNamespace(x=.1, y=.1) for _ in range(468)]
    points[1] = SimpleNamespace(x=.9, y=.9)
    for indices, center in (([362,385,387,263,373,380], .75), ([33,160,158,133,153,144], .25)):
        for i,index in enumerate(indices):
            points[index] = SimpleNamespace(x=center + (i%2)*.1, y=.4 + (i%3)*.02)
    processor = Preprocessor.__new__(Preprocessor)
    processor.mp = SimpleNamespace(Image=lambda **kwargs: kwargs, ImageFormat=SimpleNamespace(SRGB=1))
    processor.detector = SimpleNamespace(detect=lambda _: SimpleNamespace(face_landmarks=[points]))
    processor.means = {name: np.full((224,224,3), [1,2,3], dtype=np.float32) for name in ('face','left','right')}
    image = np.full((100,100,3), [11,22,33], dtype=np.uint8)
    inputs, boxes, _ = processor.prepare(image)
    for name in ('face','left','right'):
        assert inputs[name].dtype == np.float32 and inputs[name].shape == (1,3,224,224)
        np.testing.assert_array_equal(inputs[name][0,:,0,0], [10,20,30])
    assert boxes['left'][0] > boxes['right'][0]
    assert inputs['grid'].shape == (1,625)
    processor.detector = SimpleNamespace(detect=lambda _: SimpleNamespace(face_landmarks=[points,points]))
    with pytest.raises(DetectionFailure, match='multiple_faces'):
        processor.prepare(image)
