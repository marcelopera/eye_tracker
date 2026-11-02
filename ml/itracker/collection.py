"""Build analysis inputs from instrumented collections and explicit pilot measurements."""
import json
from pydantic import Field, FiniteFloat
from config import Strict, Capture, Geometry, Calibration, Criteria, ProcessingConfig, Synchronization, Target


class PhysicalMeasurements(Strict):
    screen_width_mm: float = Field(gt=0)
    screen_height_mm: float = Field(gt=0)
    camera_x_mm: FiniteFloat
    camera_y_mm: FiniteFloat
    model_axes: tuple[tuple[FiniteFloat, FiniteFloat], tuple[FiniteFloat, FiniteFloat]]
    measurement_evidence: str = Field(min_length=1, max_length=2000)
    axes_evidence: str = Field(min_length=1, max_length=2000)


class TimingMeasurements(Strict):
    measurement_error_ms: float = Field(gt=0)
    max_error_ms: float = Field(gt=0)
    evidence: str = Field(min_length=1, max_length=2000)


class PilotSettings(Strict):
    physical: PhysicalMeasurements | None = None
    timing: TimingMeasurements | None = None
    settling_ms: float | None = Field(default=None, ge=0, lt=2000)
    calibration: Calibration | None = None
    criteria: Criteria | None = None
    export_features: bool = False


def prepare_collection(metadata, settings, *, demonstration=False):
    if demonstration:
        return prepare_demonstration(metadata)
    settings = PilotSettings.model_validate(settings)
    config = ProcessingConfig(schema_version=1, capture=Capture(rotation_degrees=0, mirrored=False),
                              calibration=settings.calibration, criteria=settings.criteria,
                              export_features=settings.export_features)
    issues = []
    groups = {}
    if not isinstance(metadata, dict) or metadata.get('estado') not in ('concluida', 'interrompida'):
        raise ValueError('Metadados de sessão incompatíveis')
    if metadata.get('schema_version') not in (None, 1, 2):
        raise ValueError('Versão de coleta não suportada')
    events = metadata.get('eventos')
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ValueError('Lista de eventos inválida')
    for event in events:
        name = event.get('evento')
        if name not in ('camera_info_v1', 'camera_frame_v1', 'display_v1', 'stimulus_geometry_v1', 'stimulus_timing_v1',
                        'presented_frame_v1', 'target_v1'):
            continue
        if metadata.get('schema_version') != 2:
            raise ValueError('Instrumentação requer versão 2 da coleta')
        if event.get('relogio') != 'frameTimeNanos':
            raise ValueError('Relógio de instrumentação incompatível')
        stamp = event['tempo_nanos']
        if type(stamp) is not int or stamp < 0:
            raise ValueError('Timestamp de instrumentação inválido')
        data = json.loads(event['dados'])
        if not isinstance(data, dict):
            raise ValueError('Instrumentação deve conter objeto JSON')
        groups.setdefault(name, []).append((stamp, data))
    for values in groups.values():
        values.sort(key=lambda value: value[0])
        if any(a[0] >= b[0] for a, b in zip(values, values[1:])):
            raise ValueError('Instrumentação duplicada ou não crescente')
    info = groups.get('camera_info_v1', [])
    if len(info) != 1:
        issues.append('missing_camera_instrumentation')
        return {'config': config.model_dump(), 'issues': issues, 'ready_for_pilot': False}
    camera = info[0][1]
    config.capture = Capture.model_validate({key: camera[key] for key in ('rotation_degrees', 'mirrored')})
    display = groups.get('display_v1', [])
    layout = groups.get('stimulus_geometry_v1', [])
    if settings.physical and len(display) == 1 and len(layout) == 1:
        screen, rect = display[0][1], layout[0][1]
        if rect.get('rotation_degrees') != 0:
            issues.append('unsupported_stimulus_rotation')
        else:
            config.geometry = Geometry(**settings.physical.model_dump(),
                screen_width_px=screen['screen_width_px'], screen_height_px=screen['screen_height_px'],
                stimulus_rect=[rect['x_px'], rect['y_px'], rect['width_px'], rect['height_px']],
                stimulus_width_px=rect['video_width_px'], stimulus_height_px=rect['video_height_px'])
    else:
        issues.append('missing_physical_measurements' if not settings.physical else 'missing_display_geometry')
    frames = groups.get('camera_frame_v1', [])
    presented = groups.get('presented_frame_v1', [])
    timing = groups.get('stimulus_timing_v1', [])
    targets = groups.get('target_v1', [])
    if camera.get('timestamp_source_realtime') is not True:
        issues.append('unknown_camera_clock')
    elif not settings.timing:
        issues.append('missing_timing_measurement')
    elif len(frames) < 3:
        issues.append('insufficient_camera_correspondences')
    else:
        # An anchor exists only for a sample actually written by the encoder. Its PTS starts at zero.
        pts = [d['pts_us'] for _, d in frames]
        errors = [d['clock_error_ns'] for _, d in frames]
        if any(type(p) is not int or p < 0 for p in pts) or any(b <= a for a, b in zip(pts, pts[1:])):
            raise ValueError('PTS codificados devem ser inteiros estritamente crescentes')
        if any(type(e) is not int or e < 0 for e in errors):
            raise ValueError('Incerteza dos relógios inválida')
        intervals = []
        source_pts = timing[0][1]['media_pts_us'] if len(timing) == 1 else []
        if not source_pts:
            issues.append('missing_stimulus_timing')
        if any(type(p) is not int or p < 0 for p in source_pts) or any(b <= a for a, b in zip(source_pts, source_pts[1:])):
            raise ValueError('PTS do estímulo devem ser inteiros estritamente crescentes')
        successors = dict(zip(source_pts, source_pts[1:]))
        for (time, data), (next_time, next_data) in zip(presented, presented[1:]):
            delta = next_data['media_time_us'] - data['media_time_us']
            if data['media_time_us'] < 0 or delta <= 0:
                raise ValueError('Tempo de mídia apresentado não crescente')
            # A skipped callback or dropped frame does not prove what was visible in the gap.
            # A real stall with consecutive source PTS can still hold one frame for longer.
            if successors.get(data['media_time_us']) != next_data['media_time_us']:
                continue
            intervals.append({'event_ns': time, 'media_time_ms': data['media_time_us'] / 1000,
                              'duration_ms': (next_time - time) / 1e6, 'media_duration_ms': delta / 1000})
        # The last rendered frame has no measured successor and is deliberately left unassociated.
        if not intervals:
            issues.append('missing_presented_frames')
        config.synchronization = Synchronization(method='explicit_encoder_pts_and_codec_render_callbacks_v1',
            evidence=settings.timing.evidence, event_clock='frameTimeNanos',
            anchors=[{'camera_ns': d['pts_us'] * 1000, 'event_ns': t} for t, d in frames],
            measurement_error_ms=settings.timing.measurement_error_ms + max(errors) / 1e6,
            max_error_ms=settings.timing.max_error_ms, presented_frames=intervals)
        if settings.settling_ms is None:
            issues.append('missing_settling_window')
        elif not targets or not all(d.get('committed') is True for _, d in targets):
            issues.append('missing_committed_targets')
        else:
            config.targets = [Target(phase=d['phase'], start_ns=t + int(settings.settling_ms * 1e6),
                end_ns=min(t + int(d['duration_ms'] * 1e6), targets[i+1][0] if i+1 < len(targets) else t + int(d['duration_ms'] * 1e6)),
                x_px=d['x_px'], y_px=d['y_px']) for i, (t, d) in enumerate(targets)]
    if settings.calibration is None:
        issues.append('missing_calibration_settings')
    elif config.targets:
        positions = {(t.x_px, t.y_px) for t in config.targets if t.phase == 'calibration'}
        if len(positions) < settings.calibration.min_targets:
            issues.append('insufficient_calibration_targets')
    validation = {(t.x_px, t.y_px) for t in config.targets if t.phase == 'validation'}
    if not validation:
        issues.append('missing_validation_targets')
    if validation & {(t.x_px, t.y_px) for t in config.targets if t.phase == 'calibration'}:
        raise ValueError('Calibração e validação precisam de posições distintas')
    if settings.criteria is None:
        issues.append('missing_acceptance_criteria')
    if metadata['estado'] != 'concluida':
        issues.append('interrupted_collection')
    # Validate generated targets too, including overlaps across phase boundaries.
    config = ProcessingConfig.model_validate(config.model_dump())
    if config.synchronization:
        from analysis import Timeline
        if Timeline(config.synchronization).report['status'] != 'available':
            issues.append('rejected_synchronization')
    return {'config': config.model_dump(), 'issues': issues, 'ready_for_pilot': not issues,
            'scientific_validation': 'requires_device_pilot'}


def prepare_demonstration(metadata):
    """A useful classroom default: approximate dimensions, real recorded features/targets."""
    display = next((json.loads(e['dados']) for e in metadata.get('eventos', []) if e.get('evento') == 'display_v1'), {})
    width, height = display.get('screen_width_px', 1080), display.get('screen_height_px', 2400)
    diagonal_mm = 170.18  # Assumed 6.7-inch screen; not a measured device profile.
    scale = diagonal_mm / (width * width + height * height) ** .5
    assumed = 'Valores aproximados para demonstração de disciplina; não medidos.'
    settings = {
        'physical': {'screen_width_mm': width * scale, 'screen_height_mm': height * scale,
            'camera_x_mm': width * scale / 2, 'camera_y_mm': 4,
            'model_axes': [[1, 0], [0, -1]], 'measurement_evidence': assumed, 'axes_evidence': assumed},
        'timing': {'measurement_error_ms': 35, 'max_error_ms': 100, 'evidence': assumed},
        'settling_ms': 500,
        'calibration': {'kernel': 'linear', 'C': 1000, 'epsilon': 10, 'gamma': .01, 'min_samples': 15, 'min_targets': 3},
        'criteria': None,
    }
    result = prepare_collection(metadata, settings)
    config = result['config']
    config['demonstration'] = True
    geometry = config.get('geometry')
    if geometry:
        # Older apps recorded the Surface before its final layout. Reconstruct FIT content
        # from its viewport and the displayed video dimensions, including video rotation.
        x, y, viewport_width, viewport_height = geometry['stimulus_rect']
        factor = min(viewport_width / geometry['stimulus_width_px'], viewport_height / geometry['stimulus_height_px'])
        content_width, content_height = geometry['stimulus_width_px'] * factor, geometry['stimulus_height_px'] * factor
        geometry['stimulus_rect'] = [x + (viewport_width - content_width) / 2,
            y + (viewport_height - content_height) / 2, content_width, content_height]
        geometry['stimulus_coordinate_space'] = 'display'
    config = ProcessingConfig.model_validate(config).model_dump()
    result.update(config=config, demonstration=True, assumptions=assumed,
                  scientific_validation='classroom_demonstration')
    result['issues'] = [issue for issue in result['issues'] if issue != 'missing_acceptance_criteria']
    result['ready_for_pilot'] = not result['issues']
    return result
