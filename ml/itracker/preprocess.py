"""Experimental MediaPipe crops; not equivalent to Apple's training detector."""
import math

import cv2
import numpy as np
from scipy.io import loadmat

from model_assets import LANDMARKER_SHA256, LANDMARKER_URL, digest, verify


class DetectionFailure(ValueError):
    pass


def square(points, factor):
    low, high = points.min(axis=0), points.max(axis=0)
    side = int(math.ceil(max(high - low) * factor))
    if side < 2:
        raise DetectionFailure("invalid_crop")
    center = (low + high) / 2
    return [int(math.floor(center[0] - side / 2)), int(math.floor(center[1] - side / 2)), side, side]


def crop(image, box):
    x, y, w, h = box
    height, width = image.shape[:2]
    if w < 2 or h < 2 or w > 2 * width or h > 2 * height or x >= width or y >= height or x + w <= 0 or y + h <= 0:
        raise DetectionFailure("invalid_crop")
    padded = cv2.copyMakeBorder(image, max(0, -y), max(0, y + h - height),
                               max(0, -x), max(0, x + w - width), cv2.BORDER_REPLICATE)
    return padded[max(0, y):max(0, y) + h, max(0, x):max(0, x) + w]


def face_grid(box, width, height):
    # MATLAB round (half away from zero), then the reference's clamped inclusive bounds.
    def rounded(value):
        return int(np.sign(value) * np.floor(abs(value) + .5))
    x, y, w, h = box
    lo_x, lo_y = rounded(x * 25 / width), rounded(y * 25 / height)
    hi_x, hi_y = lo_x + rounded(w * 25 / width) - 1, lo_y + rounded(h * 25 / height) - 1
    lo_x, hi_x, lo_y, hi_y = [min(24, max(0, v)) for v in (lo_x, hi_x, lo_y, hi_y)]
    grid = np.zeros((25, 25), np.float32)
    grid[lo_y:hi_y + 1, lo_x:hi_x + 1] = 1
    return grid.reshape(1, 625)


class Preprocessor:
    def __init__(self, directory):
        import mediapipe as mp
        task = directory / "face_landmarker.task"
        if not task.is_file() or digest(task) != LANDMARKER_SHA256:
            raise ValueError("Face Landmarker ausente ou alterado; execute download-detector")
        verify(directory, [f"mean_{name}_224.mat" for name in ("face", "left", "right")])
        self.means = {name: loadmat(directory / f"mean_{name}_224.mat")["image_mean"].astype(np.float32)
                      for name in ("face", "left", "right")}
        if any(a.shape != (224, 224, 3) or not np.isfinite(a).all() for a in self.means.values()):
            raise ValueError("Médias incompatíveis")
        self.mp = mp
        self.detector = mp.tasks.vision.FaceLandmarker.create_from_options(
            mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(task)),
                running_mode=mp.tasks.vision.RunningMode.IMAGE, num_faces=2))

    def close(self):
        self.detector.close()

    def prepare(self, image):
        result = self.detector.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                                                    data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB)))
        if len(result.face_landmarks) != 1:
            raise DetectionFailure("no_face" if not result.face_landmarks else "multiple_faces")
        height, width = image.shape[:2]
        points = np.array([[p.x * width, p.y * height] for p in result.face_landmarks[0]])
        if not np.isfinite(points).all():
            raise DetectionFailure("invalid_landmarks")
        # Anatomical left appears on the right in the upright, unmirrored image.
        boxes = {"face": square(points, 1.1),
                 "left": square(points[[362, 385, 387, 263, 373, 380]], 1.8),
                 "right": square(points[[33, 160, 158, 133, 153, 144]], 1.8)}
        crops = {name: cv2.resize(crop(image, box), (224, 224), interpolation=cv2.INTER_LINEAR)
                 for name, box in boxes.items()}
        inputs = {name: (value.astype(np.float32) - self.means[name]).transpose(2, 0, 1)[None].copy()
                  for name, value in crops.items()}
        inputs["grid"] = face_grid(boxes["face"], width, height)
        return inputs, boxes, crops
