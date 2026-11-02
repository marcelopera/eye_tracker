"""Render a session's existing predictions as a standalone H.264 demonstration."""
import argparse
from bisect import bisect_right
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import tempfile

import av
import cv2
import numpy as np

from preprocess import crop
from video import camera_frames

WIDTH, HEIGHT = 1440, 896
MAX_INTERPOLATION_GAP_MS = 100
FOREGROUND, MUTED, ACCENT = (236, 232, 224), (168, 157, 142), (168, 225, 88)


class Samples:
    """Fill short display gaps between consecutive valid camera samples."""
    def __init__(self, report, rows):
        rows = list(rows)
        self.intervals = report['config']['synchronization']['presented_frames']
        self.times = [frame['media_time_ms'] for frame in self.intervals]
        self.index = {}
        for row in rows:
            stamp = row['stimulus_time_ms']
            if stamp is not None and (stamp not in self.index or
                                     (not self.index[stamp]['valid'] and row['valid'])):
                self.index[stamp] = row
        self.camera_rows = sorted((r for r in rows if r.get('event_time_ns') is not None),
                                  key=lambda r: r['event_time_ns'])
        self.camera_times = [r['event_time_ns'] for r in self.camera_rows]

    def at(self, time_ms, *, interpolate=True):
        position = bisect_right(self.times, time_ms) - 1
        if position >= 0:
            interval = self.intervals[position]
            duration = interval.get('media_duration_ms') or interval['duration_ms']
            if time_ms < interval['media_time_ms'] + duration:
                sample = self.index.get(interval['media_time_ms'])
                if sample is not None or not interpolate:
                    return sample
                return self.between(interval)
        return None

    def between(self, interval):
        event_ns = interval.get('event_ns')
        if event_ns is None:
            return None
        index = bisect_right(self.camera_times, event_ns)
        if index == 0 or index == len(self.camera_rows):
            return None  # Never extrapolate before/after the recorded samples.
        left, right = self.camera_rows[index-1:index+1]
        gap_ns = right['event_time_ns'] - left['event_time_ns']
        if not 0 < gap_ns <= MAX_INTERPOLATION_GAP_MS * 1e6:
            return None
        if right['frame_index'] != left['frame_index'] + 1:
            return None  # A missing timestamp or row must not hide a detection failure.
        if any(not row['valid'] or row.get('phase') != 'stimulus' or
               row.get('demo_stimulus_px') is None for row in (left, right)):
            return None
        fraction = (event_ns - left['event_time_ns']) / gap_ns
        point = ((1-fraction) * np.asarray(left['demo_stimulus_px']) +
                 fraction * np.asarray(right['demo_stimulus_px'])).tolist()
        left_boxes, right_boxes = left.get('boxes') or {}, right.get('boxes') or {}
        boxes = {name: np.rint((1-fraction) * np.asarray(left_boxes[name]) +
                              fraction * np.asarray(right_boxes[name])).astype(int).tolist()
                 for name in left_boxes.keys() & right_boxes.keys()}
        return {**left, 'event_time_ns': event_ns, 'stimulus_time_ms': interval['media_time_ms'],
                'demo_stimulus_px': point, 'boxes': boxes,
                'interpolation': {'from_frame_index': left['frame_index'],
                                  'to_frame_index': right['frame_index'],
                                  'fraction': fraction, 'gap_ms': gap_ns / 1e6}}


class CameraFrames:
    """Sequential decoder with a two-frame buffer for linear image interpolation."""
    def __init__(self, path, capture):
        self.decoder = camera_frames(path, capture['rotation_degrees'], capture['mirrored'])
        self.frames = {}
        self.last_index = -1

    def at(self, index):
        while self.last_index < index:
            try:
                image, timing = next(self.decoder)
            except StopIteration as error:
                raise ValueError('Vídeo da câmera termina antes da amostra associada.') from error
            self.last_index = timing['frame_index']
            self.frames = {key: value for key, value in self.frames.items() if key >= self.last_index-1}
            self.frames[self.last_index] = image
        if index not in self.frames:
            raise ValueError('Ordem temporal das amostras incompatível com a câmera.')
        return self.frames[index]

    def image(self, sample):
        left = self.at(sample['frame_index'])
        interpolation = sample.get('interpolation')
        if interpolation is None:
            return left
        right = self.at(interpolation['to_frame_index'])
        fraction = interpolation['fraction']
        return cv2.addWeighted(left, 1-fraction, right, fraction, 0)

    def close(self):
        self.decoder.close()


def display_rotation(video):
    """ffprobe's display matrix is counterclockwise; camera_frames uses clockwise."""
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream_tags=rotate:stream_side_data=rotation', '-of', 'json', str(video)],
        capture_output=True, text=True, timeout=30, check=True)
    stream = json.loads(result.stdout)['streams'][0]
    rotation = float(stream.get('tags', {}).get('rotate', 0))
    for data in stream.get('side_data_list', []):
        if 'rotation' in data:
            rotation = float(data['rotation'])
    clockwise = (-rotation) % 360
    if clockwise not in (0, 90, 180, 270):
        raise ValueError('Rotação do estímulo deve ser um múltiplo de 90 graus.')
    return int(clockwise)


def progress(path, frames, stage):
    if path is None:
        return
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.render-progress-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'frames_processed': frames, 'stage': stage}, stream)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def text(canvas, message, x, y, size=.6, color=FOREGROUND, thickness=1):
    # The content starts at the top: there is no brand/title banner in the MP4.
    cv2.putText(canvas, message, (x, y - 64), cv2.FONT_HERSHEY_SIMPLEX,
                size, color, thickness, cv2.LINE_AA)


def paste_fit(canvas, image, x, y, width, height):
    scale = min(width / image.shape[1], height / image.shape[0])
    w, h = round(image.shape[1] * scale), round(image.shape[0] * scale)
    left, top = x + (width - w) // 2, y - 64 + (height - h) // 2
    canvas[top:top+h, left:left+w] = cv2.resize(image, (w, h), interpolation=cv2.INTER_AREA)
    return left, top, w, h


def draw_frame(stimulus, sample, camera, report, time_ms):
    canvas = np.full((HEIGHT, WIDTH, 3), (27, 23, 19), dtype=np.uint8)
    text(canvas, 'ESTIMULO + OLHAR ESTIMADO', 36, 90, .55, MUTED)
    x, y, width, height = paste_fit(canvas, stimulus, 36, 108, 432, 768)
    point = sample.get('demo_stimulus_px', sample.get('calibrated_stimulus_px')) if sample else None
    geometry = report['config']['geometry']
    visible = (point is not None and 0 <= point[0] < geometry['stimulus_width_px'] and
               0 <= point[1] < geometry['stimulus_height_px'])
    if visible:
        center = (round(x + point[0] / geometry['stimulus_width_px'] * width),
                  round(y + point[1] / geometry['stimulus_height_px'] * height))
        cv2.circle(canvas, center, 11, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.circle(canvas, center, 7, (100, 65, 255), -1, cv2.LINE_AA)
    text(canvas, f'Tempo do estimulo: {time_ms/1000:05.2f} s', 36, 910, .62)
    text(canvas, 'Ponto: calibracao da sessao + mediana de 5 amostras', 36, 939, .45, MUTED)
    text(canvas, 'CAMERA FRONTAL', 520, 90, .55, MUTED)
    text(canvas, 'ENTRADAS DO iTRACKER', 810, 90, .55, MUTED)
    if sample and camera is not None:
        paste_fit(canvas, camera, 520, 108, 240, 320)
        boxes = sample.get('boxes') or {}
        for i, (key, label) in enumerate((('face', 'Rosto'), ('left', 'Olho esquerdo'), ('right', 'Olho direito'))):
            if key in boxes:
                paste_fit(canvas, crop(camera, boxes[key]), 810 + 194*i, 128, 180, 180)
            text(canvas, label, 810 + 194*i, 337, .48, MUTED)
        interpolation = sample.get('interpolation')
        label = (f'Quadros: {sample["frame_index"]} -> {interpolation["to_frame_index"]}'
                 if interpolation else f'Quadro associado: {sample["frame_index"]}')
        text(canvas, label, 520, 453, .5)
    else:
        text(canvas, 'Sem amostra associada neste intervalo', 520, 250, .65, MUTED)
    text(canvas, 'PIPELINE', 810, 394, .65, ACCENT, 2)
    rotation = report['config']['capture']['rotation_degrees']
    steps = [
        ('01  Captura Android', 'Video frontal + eventos + timestamps'),
        ('02  Orientacao e sincronizacao', f'Rotacao {rotation} graus; PTS -> tempo do estimulo'),
        ('03  MediaPipe', 'Rosto, olhos e grid facial 25 x 25'),
        ('04  iTracker congelado', 'Previsao bruta em cm + 128 features'),
        ('05  Calibracao da sessao', 'Dois SVRs -> pixels da tela -> estimulo'),
        ('06  Visualizacao', 'Mediana + interpolacao de lacunas curtas'),
    ]
    for i, (title, detail) in enumerate(steps):
        top = 412 + i*67
        cv2.rectangle(canvas, (800, top-64), (1402, top-6), (43, 36, 29), -1)
        text(canvas, title, 818, top+23, .57)
        text(canvas, detail, 818, top+45, .43, MUTED)
    text(canvas, 'RESULTADO DA SESSAO', 520, 520, .55, ACCENT, 2)
    text(canvas, f'{report["valid_frames"]} / {report["frames"]} quadros', 520, 558, .58)
    text(canvas, 'com inferencia numerica', 520, 584, .48, MUTED)
    error = report.get('validation', {}).get('calibrated', {}).get('mean_error_px')
    text(canvas, 'Erro de validacao:', 520, 638, .56)
    text(canvas, f'{error:.0f} px' if error is not None else 'Indisponivel', 520, 681, .85, (112, 190, 255), 2)
    text(canvas, f'Tela: {geometry["screen_width_px"]} x {geometry["screen_height_px"]}', 520, 710, .45, MUTED)
    state = 'Ponto estimado' if visible else 'Ponto indisponivel' if point is None else 'Ponto fora do estimulo'
    if visible and sample.get('interpolation'):
        state = 'Ponto interpolado'
    text(canvas, state, 520, 774, .5, ACCENT if visible else MUTED)
    text(canvas, 'Localizacao aproximada; erro medido em alvos separados.', 520, 881, .55, MUTED)
    text(canvas, 'Calibracao e geometria automaticas para demonstracao.', 520, 913, .52, MUTED)
    return canvas


def render_demonstration(camera, stimulus, results, output, *, progress_path=None):
    report = json.loads((results / 'summary.json').read_text(encoding='utf-8'))
    config = report['config']
    if not config.get('geometry') or not config.get('synchronization'):
        raise ValueError('A demonstração exige geometria e sincronização da coleta.')
    if report['calibration']['status'] != 'available':
        raise ValueError('Não há amostras suficientes para calibrar o olhar. Faça uma nova coleta completa.')
    with (results / 'samples.jsonl').open(encoding='utf-8') as source:
        rows = [json.loads(line) for line in source]
    samples = Samples(report, rows)
    if not any(r.get('demo_stimulus_px') is not None for r in rows):
        raise ValueError('Nenhuma previsão de olhar associada ao estímulo. Faça uma nova coleta completa.')
    inputs = {camera.resolve(), stimulus.resolve(), (results / 'summary.json').resolve(),
              (results / 'samples.jsonl').resolve()}
    if output.resolve() in inputs or (progress_path is not None and
                                    (progress_path.resolve() in inputs or progress_path.resolve() == output.resolve())):
        raise ValueError('As saídas não podem substituir os arquivos de entrada.')
    rotation = display_rotation(stimulus)
    cameras = CameraFrames(camera, config['capture'])
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix='.demonstration-', suffix='.mp4')
    os.close(fd)
    cv2.setNumThreads(1)
    count, associated, interpolated = 0, 0, 0
    try:
        progress(progress_path, 0, 'rendering')
        with av.open(str(stimulus), options={'protocol_whitelist': 'file,pipe'}) as source, \
                av.open(temporary, 'w', format='mp4', options={'movflags': '+faststart'}) as destination:
            original = source.streams.video[0]
            stream = destination.add_stream('libx264', rate=original.average_rate or Fraction(30))
            stream.width, stream.height, stream.pix_fmt = WIDTH, HEIGHT, 'yuv420p'
            stream.options = {'crf': '20', 'preset': 'fast'}
            stream.time_base = stream.codec_context.time_base = Fraction(original.time_base)
            stream.codec_context.max_b_frames = 0
            first_pts = None
            for frame in source.decode(original):
                if count >= 100000 or frame.width * frame.height > 16777216:
                    raise ValueError('Estímulo excede o limite de quadros ou resolução.')
                if frame.pts is None or frame.time_base is None:
                    raise ValueError('Quadro do estímulo sem timestamp.')
                time_ms = float(frame.pts * frame.time_base * 1000)
                # Tiny tolerance handles decimal millisecond representations of the same PTS.
                sample = samples.at(time_ms + 1e-6)
                camera_image = cameras.image(sample) if sample else None
                if sample:
                    associated += 1
                    interpolated += sample.get('interpolation') is not None
                image = frame.to_ndarray(format='bgr24')
                if rotation:
                    image = cv2.rotate(image, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                                                270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rotation])
                geometry = config['geometry']
                if (image.shape[1], image.shape[0]) != (geometry['stimulus_width_px'], geometry['stimulus_height_px']):
                    raise ValueError('Dimensões de exibição do estímulo divergem da coleta.')
                canvas = draw_frame(image, sample, camera_image if sample else None, report, time_ms)
                rendered = av.VideoFrame.from_ndarray(canvas, format='bgr24')
                if first_pts is None:
                    first_pts = frame.pts
                rendered.pts, rendered.time_base = frame.pts - first_pts, frame.time_base
                for packet in stream.encode(rendered):
                    destination.mux(packet)
                count += 1
                if count % 30 == 0:
                    progress(progress_path, count, 'rendering')
            if not count or not associated:
                raise ValueError('Não há quadros do estímulo com amostras para a demonstração.')
            for packet in stream.encode():
                destination.mux(packet)
        os.replace(temporary, output)
        progress(progress_path, count, 'completed')
    finally:
        cameras.close()
        Path(temporary).unlink(missing_ok=True)
    return {'frames': count, 'frames_with_sample': associated, 'interpolated_frames': interpolated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('camera', 'stimulus', 'results', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--progress', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(render_demonstration(args.camera, args.stimulus, args.results, args.output,
                                             progress_path=args.progress)))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, cv2.error, av.FFmpegError) as error:
        parser.exit(1, f'Erro: {error}\n')


if __name__ == '__main__':
    main()
