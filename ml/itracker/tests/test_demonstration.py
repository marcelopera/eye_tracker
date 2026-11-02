import json
from fractions import Fraction
import subprocess

import av
import numpy as np
import pytest

from demonstration import CameraFrames, Samples, display_rotation, draw_frame, render_demonstration
from test_video import make_video


def fixture(tmp_path):
    camera, stimulus = tmp_path / 'camera.mkv', tmp_path / 'stimulus.mkv'
    make_video(camera)
    make_video(stimulus)
    results = tmp_path / 'results'
    results.mkdir()
    config = {'capture': {'rotation_degrees': 0, 'mirrored': False},
              'geometry': {'stimulus_width_px': 32, 'stimulus_height_px': 24,
                           'screen_width_px': 1080, 'screen_height_px': 2400},
              'synchronization': {'presented_frames': [
                  {'media_time_ms': 0, 'duration_ms': 100},
                  {'media_time_ms': 500, 'duration_ms': 100}]}}
    report = {'config': config, 'frames': 3, 'valid_frames': 2,
              'calibration': {'status': 'available'},
              'validation': {'calibrated': {'mean_error_px': 273.7}}}
    rows = [{'frame_index': index, 'stimulus_time_ms': stamp, 'valid': True,
             'demo_stimulus_px': point, 'boxes': {n: [0, 0, 24, 24] for n in ('face', 'left', 'right')}}
            for index, stamp, point in ((0, 0, [16, 12]), (2, 500, [1000, -1000]))]
    (results / 'summary.json').write_text(json.dumps(report))
    (results / 'samples.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    return camera, stimulus, results, report, rows


def test_render_mp4_preserves_variable_timestamps_and_does_not_fill_gaps(tmp_path):
    camera, stimulus, results, _, _ = fixture(tmp_path)
    output, progress = tmp_path / 'demo.mp4', tmp_path / 'progress.json'
    stats = render_demonstration(camera, stimulus, results, output, progress_path=progress)
    assert stats == {'frames': 3, 'frames_with_sample': 2, 'interpolated_frames': 0}
    assert json.loads(progress.read_text()) == {'stage': 'completed', 'frames_processed': 3}
    with av.open(str(output)) as video:
        assert video.streams.video[0].codec_context.name == 'h264'
        frames = list(video.decode(video.streams.video[0]))
        assert [(f.width, f.height) for f in frames] == [(1440, 896)] * 3
        assert [float(f.pts * f.time_base) for f in frames] == pytest.approx([0, .2, .5])
    assert not list(tmp_path.glob('.demonstration-*'))


def test_draw_marker_only_for_real_in_bounds_prediction_and_no_title_banner(tmp_path):
    _, _, _, report, rows = fixture(tmp_path)
    image = np.zeros((24, 32, 3), np.uint8)
    valid = draw_frame(image, rows[0], image, report, 0)
    missing = draw_frame(image, None, None, report, 200)
    outside = draw_frame(image, rows[1], image, report, 500)
    np.testing.assert_array_equal(valid[428, 252], [100, 65, 255])
    np.testing.assert_array_equal(missing[428, 252], [0, 0, 0])
    np.testing.assert_array_equal(outside[428, 252], [0, 0, 0])
    # No Eye Tracker / demonstration banner above the three panels.
    assert np.all(valid[:8] == [27, 23, 19])


def test_interval_lookup_respects_media_duration_and_prefers_valid_samples(tmp_path):
    _, _, _, report, rows = fixture(tmp_path)
    report['config']['synchronization']['presented_frames'][0].update(duration_ms=400, media_duration_ms=100)
    samples = Samples(report, [{'frame_index': 99, 'stimulus_time_ms': 0, 'valid': False}, *rows])
    assert samples.at(-1) is None
    assert samples.at(0)['frame_index'] == 0
    assert samples.at(99)['frame_index'] == 0
    assert samples.at(100) is None and samples.at(200) is None
    assert samples.at(500)['frame_index'] == 2
    assert samples.at(600) is None


def test_failed_render_never_publishes_partial_mp4_or_overwrites_inputs(tmp_path):
    camera, stimulus, results, report, _ = fixture(tmp_path)
    report['config']['geometry']['stimulus_width_px'] = 100
    (results / 'summary.json').write_text(json.dumps(report))
    output = tmp_path / 'demo.mp4'
    output.write_bytes(b'previous complete artifact')
    with pytest.raises(ValueError, match='Dimensões'):
        render_demonstration(camera, stimulus, results, output)
    assert output.read_bytes() == b'previous complete artifact'
    assert not list(tmp_path.glob('.demonstration-*'))
    with pytest.raises(ValueError, match='substituir'):
        render_demonstration(camera, stimulus, results, camera)
    report['calibration']['status'] = 'unavailable'
    (results / 'summary.json').write_text(json.dumps(report))
    with pytest.raises(ValueError, match='calibrar'):
        render_demonstration(camera, stimulus, results, tmp_path / 'missing.mp4')
    assert not (tmp_path / 'missing.mp4').exists()


def test_display_rotation_follows_mp4_matrix(tmp_path):
    original, rotated = tmp_path / 'original.mp4', tmp_path / 'rotated.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=32x24:d=0.1',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(original)], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-display_rotation', '90', '-i', str(original),
                    '-c', 'copy', str(rotated)], check=True)
    assert display_rotation(original) == 0
    assert display_rotation(rotated) == 270


def interpolation_fixture(tmp_path):
    _, _, _, report, _ = fixture(tmp_path)
    report['config']['synchronization']['presented_frames'] = [
        {'event_ns': ms * 10**6, 'media_time_ms': ms, 'duration_ms': 20}
        for ms in (0, 20, 40)]
    rows = [{'frame_index': i, 'event_time_ns': event * 10**6, 'stimulus_time_ms': media,
             'phase': 'stimulus', 'valid': True, 'demo_stimulus_px': point,
             'boxes': {name: box for name in ('face', 'left', 'right')}}
            for i, event, media, point, box in ((0, 10, 0, [8, 6], [0, 0, 16, 16]),
                                               (1, 50, 40, [24, 18], [4, 4, 16, 16]))]
    return report, rows


def write_frames(path, values):
    with av.open(str(path), 'w') as output:
        stream = output.add_stream('ffv1', rate=25)
        stream.width, stream.height, stream.pix_fmt = 32, 24, 'bgr0'
        stream.time_base = stream.codec_context.time_base = Fraction(1, 1000)
        for pts, intensity in values:
            frame = av.VideoFrame.from_ndarray(np.full((24, 32, 3), intensity, np.uint8), format='bgr24')
            frame.pts, frame.time_base = pts, Fraction(1, 1000)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)


def test_interpolation_uses_camera_timestamps_and_preserves_measured_rows(tmp_path):
    report, rows = interpolation_fixture(tmp_path)
    original = json.dumps(rows)
    samples = Samples(report, rows)
    assert samples.at(20, interpolate=False) is None
    middle = samples.at(20)
    assert middle['demo_stimulus_px'] == [12, 9]  # (20 - 10) / (50 - 10) = 0.25
    assert middle['boxes']['face'] == [1, 1, 16, 16]
    assert middle['interpolation'] == {'from_frame_index': 0, 'to_frame_index': 1,
                                       'fraction': .25, 'gap_ms': 40}
    assert samples.at(0) is rows[0] and samples.at(40) is rows[1]
    assert samples.at(-1) is None and samples.at(60) is None
    assert json.dumps(rows) == original


@pytest.mark.parametrize('change', [
    {'valid': False}, {'demo_stimulus_px': None}, {'phase': 'validation'},
    {'event_time_ns': 150_000_000}, {'frame_index': 2},
])
def test_interpolation_does_not_bridge_detection_failures_phases_or_long_gaps(tmp_path, change):
    report, rows = interpolation_fixture(tmp_path)
    rows[1].update(change)
    assert Samples(report, rows).at(20) is None


def test_an_invalid_measured_sample_is_not_replaced_and_unknown_intervals_stay_empty(tmp_path):
    report, rows = interpolation_fixture(tmp_path)
    invalid = {'frame_index': 1, 'event_time_ns': 25_000_000, 'stimulus_time_ms': 20,
               'valid': False, 'phase': 'stimulus', 'reason': 'no_face', 'demo_stimulus_px': None}
    rows[1]['frame_index'] = 2
    assert Samples(report, [rows[0], invalid, rows[1]]).at(20) is invalid
    report['config']['synchronization']['presented_frames'].pop(1)
    assert Samples(report, rows).at(20) is None


def test_camera_blends_neighboring_frames_and_reuses_lookahead_with_bounded_memory(tmp_path):
    report, rows = interpolation_fixture(tmp_path)
    path = tmp_path / 'blend.mkv'
    write_frames(path, [(10, 0), (50, 200), (80, 100)])
    reader = CameraFrames(path, report['config']['capture'])
    try:
        np.testing.assert_array_equal(reader.image(rows[0]), 0)
        np.testing.assert_array_equal(reader.image(Samples(report, rows).at(20)), 50)
        np.testing.assert_array_equal(reader.image(rows[1]), 200)
        np.testing.assert_array_equal(reader.at(2), 100)
        assert len(reader.frames) == 2
    finally:
        reader.close()


def test_interpolated_mp4_contains_blended_camera_and_preserves_sources(tmp_path):
    report, rows = interpolation_fixture(tmp_path)
    camera, stimulus = tmp_path / 'blend-camera.mkv', tmp_path / 'blend-stimulus.mkv'
    write_frames(camera, [(10, 0), (50, 200)])
    write_frames(stimulus, [(0, 0), (20, 0), (40, 0)])
    results = tmp_path / 'results'
    (results / 'summary.json').write_text(json.dumps(report))
    (results / 'samples.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    originals = {p: p.read_bytes() for p in results.iterdir()}
    stats = render_demonstration(camera, stimulus, results, tmp_path / 'interpolated.mp4')
    assert stats == {'frames': 3, 'frames_with_sample': 3, 'interpolated_frames': 1}
    with av.open(str(tmp_path / 'interpolated.mp4')) as video:
        frames = list(video.decode(video.streams.video[0]))
        assert [float(f.pts * f.time_base) for f in frames] == pytest.approx([0, .02, .04])
        image = frames[1].to_ndarray(format='bgr24')
        # H.264/YUV conversion changes pixel values slightly; an empty panel (0)
        # or either original camera frame (0/200) must still fail this check.
        assert float(image[180:200, 620:640].mean()) == pytest.approx(50, abs=5)
    assert all(p.read_bytes() == value for p, value in originals.items())
