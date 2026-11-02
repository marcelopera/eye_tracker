import copy
import json

import pytest
from analysis import Timeline, screen_point, stimulus_point
from collection import prepare_collection


def event(name, time, **data):
    return {'evento': name, 'tempo_nanos': time, 'relogio': 'frameTimeNanos', 'dados': json.dumps(data)}


def collection():
    origin = 10**15
    events = [event('camera_info_v1', origin-1, rotation_degrees=270, mirrored=False, timestamp_source_realtime=True),
              event('display_v1', origin-2, screen_width_px=1000, screen_height_px=2000),
              event('stimulus_geometry_v1', origin+10, x_px=0, y_px=500, width_px=1000, height_px=1000,
                    video_width_px=500, video_height_px=500, rotation_degrees=0)]
    events += [event('camera_frame_v1', origin+i*1_000_000_000, pts_us=i*1_000_000, clock_error_ns=1000) for i in range(15)]
    # A wall-clock stall holds an existing frame; media duration stays distinct from wall duration.
    events += [event('presented_frame_v1', origin+t, media_time_us=m) for t, m in
               ((8_000_000_000, 0), (8_100_000_000, 100_000), (8_500_000_000, 200_000))]
    events.append(event('stimulus_timing_v1', origin-3, media_pts_us=[0,100_000,200_000]))
    events += [event('target_v1', origin+i*2_000_000_000, phase='calibration' if i<3 else 'validation',
                     x_px=100+i*100, y_px=200+i*100, duration_ms=2000, committed=True) for i in range(4)]
    return {'schema_version': 2, 'estado': 'concluida', 'eventos': events}


def settings():
    return {'physical': {'screen_width_mm': 100, 'screen_height_mm': 200, 'camera_x_mm': 50,
            'camera_y_mm': 0, 'model_axes': [[1,0],[0,-1]], 'measurement_evidence': 'synthetic only', 'axes_evidence': 'synthetic only'},
            'timing': {'measurement_error_ms': 2, 'max_error_ms': 5, 'evidence': 'synthetic only'},
            'settling_ms': 500, 'calibration': {'kernel': 'linear', 'C': 1, 'epsilon': 0, 'gamma': 1, 'min_samples': 3, 'min_targets': 3},
            'criteria': {'max_mean_error_px': 100, 'max_invalid_fraction': .2}}


def test_preparation_preserves_pts_geometry_holdout_and_rendered_stalls():
    result = prepare_collection(collection(), settings())
    assert result['ready_for_pilot'] and result['issues'] == []
    config = result['config']
    assert config['capture'] == {'rotation_degrees': 270, 'mirrored': False}
    assert [a['camera_ns'] for a in config['synchronization']['anchors']] == [i*10**9 for i in range(15)]
    assert config['synchronization']['presented_frames'][1]['duration_ms'] == 400
    assert config['synchronization']['presented_frames'][1]['media_duration_ms'] == 100
    assert len(config['synchronization']['presented_frames']) == 2  # Never invent last-frame duration.
    assert config['targets'][0]['start_ns'] == 10**15 + 500_000_000
    assert [t['phase'] for t in config['targets']] == ['calibration']*3 + ['validation']
    from config import ProcessingConfig
    parsed = ProcessingConfig.model_validate(config)
    timeline = Timeline(parsed.synchronization)
    assert timeline.stimulus_time(10**15 + 8_300_000_000) == (100., None)
    assert timeline.stimulus_time(10**15 + 8_600_000_000)[0] is None
    assert stimulus_point(screen_point([0, -10], parsed.geometry), parsed.geometry) == [250,250]


@pytest.mark.parametrize('condition,issue', [('no_timing','missing_timing_measurement'), ('unknown_clock','unknown_camera_clock'),
    ('uncommitted','missing_committed_targets'), ('rejected','rejected_synchronization'), ('physical','missing_physical_measurements')])
def test_unverified_measurements_are_not_invented(condition, issue):
    data, measurements = collection(), settings()
    if condition == 'no_timing': measurements.pop('timing')
    if condition == 'physical': measurements.pop('physical')
    if condition == 'unknown_clock':
        data['eventos'][0]['dados'] = json.dumps({**json.loads(data['eventos'][0]['dados']), 'timestamp_source_realtime':False})
    if condition == 'uncommitted':
        for e in data['eventos']:
            if e['evento'] == 'target_v1': e['dados'] = json.dumps({**json.loads(e['dados']), 'committed':False})
    if condition == 'rejected': measurements['timing']['max_error_ms'] = 1
    result = prepare_collection(data, measurements)
    assert not result['ready_for_pilot'] and issue in result['issues']
    if condition in ('no_timing','unknown_clock'): assert result['config']['synchronization'] is None
    if condition == 'uncommitted': assert result['config']['targets'] == []


def test_legacy_and_malformed_telemetry():
    result = prepare_collection({'estado':'concluida','eventos':[]}, {})
    assert result['config']['synchronization'] is None and not result['ready_for_pilot']
    data = collection()
    data['eventos'].append(copy.deepcopy(data['eventos'][3]))
    with pytest.raises(ValueError, match='duplicada'): prepare_collection(data, settings())
    data = collection()
    data['eventos'][3]['relogio'] = 'unrelated'
    with pytest.raises(ValueError, match='Relógio'): prepare_collection(data, settings())
    data = collection()
    data['eventos'][3]['dados'] = '{broken'
    with pytest.raises(ValueError): prepare_collection(data, settings())


def test_missing_render_callback_leaves_gap_instead_of_extending_previous_frame():
    data = collection()
    data['eventos'] = [e for e in data['eventos'] if not (e['evento']=='presented_frame_v1' and
                      json.loads(e['dados'])['media_time_us']==100_000)]
    result = prepare_collection(data, settings())
    assert result['config']['synchronization']['presented_frames'] == []
    assert 'missing_presented_frames' in result['issues']


def test_classroom_demo_assumes_profile_and_fits_rotated_phone_video():
    data = collection()
    for e in data['eventos']:
        if e['evento']=='display_v1':
            e['dados']=json.dumps({'screen_width_px':1080,'screen_height_px':2400,'model':'SM-M526B'})
        if e['evento']=='stimulus_geometry_v1':
            e['dados']=json.dumps({'x_px':0,'y_px':90,'width_px':1080,'height_px':2184,
                                  'video_width_px':720,'video_height_px':1280,'rotation_degrees':0})
    result = prepare_collection(data, {}, demonstration=True)
    assert result['ready_for_pilot'] and result['issues']==[]
    config=result['config']
    assert config['demonstration'] and config['capture']['rotation_degrees']==270
    assert tuple(config['geometry']['stimulus_rect'])==(0,222,1080,1920)
    assert config['geometry']['stimulus_coordinate_space']=='display'
    assert config['geometry']['screen_width_mm']==pytest.approx(69.84,abs=.1)
    assert config['calibration']['C']==1000 and config['criteria'] is None
    assert 'não medidos' in result['assumptions']
