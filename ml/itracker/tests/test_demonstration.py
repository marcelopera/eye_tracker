import json
import subprocess

import av
import numpy as np
import pytest

from demonstration import Samples, display_rotation, draw_frame, render_demonstration
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
    assert stats == {'frames': 3, 'frames_with_sample': 2}
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
