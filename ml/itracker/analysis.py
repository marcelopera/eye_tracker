"""Explicit temporal/spatial transforms and held-out evaluation."""
from bisect import bisect_right
from collections import deque
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR


def smooth_demonstration(rows):
    """Causal five-frame median; never bridge a missing point or another protocol phase."""
    history = deque(maxlen=5)
    for row in rows:
        point = row.get('calibrated_stimulus_px')
        if point is None or row['phase'] != 'stimulus':
            history.clear()
            row['demo_stimulus_px'] = None
        else:
            history.append(point)
            row['demo_stimulus_px'] = np.median(history, axis=0).tolist()


class Timeline:
    def __init__(self, sync):
        self.sync = sync
        self.report = {"status": "unavailable", "reason": "missing_synchronization"}
        if sync is None:
            return
        self.x0, self.y0 = sync.anchors[0].camera_ns, sync.anchors[0].event_ns
        x = np.array([a.camera_ns - self.x0 for a in sync.anchors], dtype=np.float64)
        y = np.array([a.event_ns - self.y0 for a in sync.anchors], dtype=np.float64)
        self.scale, self.offset = np.linalg.lstsq(np.column_stack([x, np.ones(len(x))]), y, rcond=None)[0]
        residual_ms = float(np.max(np.abs(y - (x * self.scale + self.offset)))) / 1e6
        error_ms = residual_ms + sync.measurement_error_ms
        self.report = {"status": "available" if self.scale > 0 and error_ms <= sync.max_error_ms else "rejected",
                       "method": sync.method, "evidence": sync.evidence, "event_clock": sync.event_clock,
                       "drift_ppm": float((self.scale - 1) * 1e6), "max_residual_ms": residual_ms,
                       "error_bound_ms": error_ms, "max_error_ms": sync.max_error_ms,
                       "anchors": len(sync.anchors)}
        self.presented = [f.event_ns for f in sync.presented_frames]

    def event_time(self, camera_ns):
        if camera_ns is None or self.report["status"] != "available":
            return None
        if not self.sync.anchors[0].camera_ns <= camera_ns <= self.sync.anchors[-1].camera_ns:
            return None
        return int(round(self.y0 + self.offset + (camera_ns - self.x0) * self.scale))

    def stimulus_time(self, event_ns):
        if event_ns is None or not self.presented:
            return None, "missing_temporal_correspondence"
        index = bisect_right(self.presented, event_ns) - 1
        if index < 0:
            return None, "outside_stimulus"
        frame = self.sync.presented_frames[index]
        end_ns = frame.event_ns + frame.duration_ms * 1e6
        if index + 1 < len(self.presented):
            end_ns = min(end_ns, self.presented[index + 1])
        if event_ns >= end_ns:
            return None, "outside_presented_frame_interval"
        return frame.media_time_ms, None


def screen_point(prediction, geometry):
    if geometry is None:
        return None
    millimeters = np.asarray(geometry.model_axes) @ (np.asarray(prediction) * 10)
    millimeters += [geometry.camera_x_mm, geometry.camera_y_mm]
    return (millimeters * [geometry.screen_width_px / geometry.screen_width_mm,
                           geometry.screen_height_px / geometry.screen_height_mm]).tolist()


def stimulus_point(screen, geometry):
    if screen is None or geometry is None:
        return None
    x, y, width, height = geometry.stimulus_rect
    return [(screen[0] - x) * geometry.stimulus_width_px / width,
            (screen[1] - y) * geometry.stimulus_height_px / height]


def calibrate(rows, config):
    settings = config.calibration
    if settings is None:
        return {"status": "unavailable", "reason": "not_configured"}
    samples = [r for r in rows if r["valid"] and r["phase"] == "calibration" and r["target_px"] is not None]
    positions = {tuple(r["target_px"]) for r in samples}
    if len(samples) < settings.min_samples or len(positions) < settings.min_targets:
        return {"status": "unavailable", "reason": "insufficient_calibration", "samples": len(samples), "targets": len(positions)}
    x = np.asarray([r["features"] for r in samples])
    y = np.asarray([r["target_px"] for r in samples])
    models = [make_pipeline(StandardScaler(), SVR(kernel=settings.kernel, C=settings.C,
                                                   epsilon=settings.epsilon, gamma=settings.gamma)).fit(x, y[:, axis])
              for axis in (0, 1)]
    valid = [r for r in rows if r["valid"]]
    if valid:
        predictions = np.column_stack([m.predict([r["features"] for r in valid]) for m in models])
        for row, prediction in zip(valid, predictions):
            row["calibrated_screen_px"] = prediction.tolist()
    return {"status": "available", "samples": len(samples), "targets": len(positions),
            "target_reference": "screen_px", "parameters": settings.model_dump(), "feature_standardization": "calibration_only"}


def evaluate(rows, geometry, criteria):
    result = {}
    validation = [r for r in rows if r["phase"] == "validation"]
    for variant, key in (("baseline", "screen_px"), ("calibrated", "calibrated_screen_px")):
        errors = [float(np.linalg.norm(np.asarray(r[key]) - r["target_px"])) for r in validation
                  if r[key] is not None and r["target_px"] is not None]
        result[variant] = {"validation_frames": len(validation), "evaluated_frames": len(errors),
                           "excluded_frames": len(validation) - len(errors),
                           "mean_error_px": float(np.mean(errors)) if errors else None,
                           "median_error_px": float(np.median(errors)) if errors else None,
                           "p95_error_px": float(np.percentile(errors, 95)) if errors else None}
        if errors and geometry:
            cm = [float(np.linalg.norm((np.asarray(r[key]) - r["target_px"]) *
                                       [geometry.screen_width_mm / geometry.screen_width_px / 10,
                                        geometry.screen_height_mm / geometry.screen_height_px / 10]))
                  for r in validation if r[key] is not None and r["target_px"] is not None]
            result[variant]["mean_error_cm"] = float(np.mean(cm))
        loss = (len(validation) - len(errors)) / len(validation) if validation else None
        result[variant]["validation_invalid_fraction"] = loss
        result[variant]["criteria_passed"] = (bool(np.mean(errors) <= criteria.max_mean_error_px and loss <= criteria.max_invalid_fraction)
                                               if criteria and errors else None)
    return result
