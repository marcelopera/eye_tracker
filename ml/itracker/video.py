"""Decode camera frames without inventing stimulus timestamps or gaze points."""
from fractions import Fraction
from pathlib import Path

import av
import cv2


def camera_frames(path: Path, rotation: int = 0, mirrored: bool = False):
    """Yield upright, unmirrored BGR images and their original presentation times.

    Rotation is clockwise and describes the correction to apply to stored pixels.
    Mirroring describes the stored pixels, so it is undone before rotation.
    """
    if rotation not in (0, 90, 180, 270):
        raise ValueError("Rotação deve ser 0, 90, 180 ou 270 graus")
    with av.open(str(path), options={"protocol_whitelist": "file,pipe"}) as container:
        if not container.streams.video:
            raise ValueError("Arquivo não contém vídeo")
        stream = container.streams.video[0]
        count = 0
        for frame in container.decode(stream):
            if frame.width * frame.height > 16777216:
                raise ValueError("Quadro excede o limite de 16 megapixels")
            image = frame.to_ndarray(format="bgr24")
            if mirrored:
                image = cv2.flip(image, 1)
            if rotation:
                image = cv2.rotate(image, {90: cv2.ROTATE_90_CLOCKWISE,
                                           180: cv2.ROTATE_180,
                                           270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rotation])
            time_base = Fraction(frame.time_base) if frame.time_base is not None else None
            yield image, {
                "frame_index": count,
                "camera_pts": frame.pts,
                "camera_time_base": ([time_base.numerator, time_base.denominator]
                                     if time_base is not None else None),
            }
            count += 1
        if count == 0:
            raise ValueError("Vídeo não contém quadros decodificáveis")
