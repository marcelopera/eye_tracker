import { useEffect, useRef, useState } from 'react';

type Run = { id: string; status: string; error: string | null; created_at: string; progress?: { frames_processed: number }; config: Record<string, unknown> };
type Sample = { frame_index: number; camera_pts: number | null; camera_time_base: [number, number] | null; stimulus_time_ms: number | null; prediction_cm: number[] | null; screen_px: number[] | null; calibrated_screen_px: number[] | null; stimulus_px: number[] | null; calibrated_stimulus_px: number[] | null; valid: boolean; reason: string | null; temporal_reason: string | null; phase: string; outside_stimulus: boolean | null; calibrated_outside_stimulus: boolean | null };
type Summary = { frames: number; valid_frames: number; invalid_fraction: number; processing_seconds: number; geometry_status: string; synchronization: { status: string; error_bound_ms?: number; drift_ppm?: number }; calibration: { status: string; reason?: string }; validation: Record<string, { evaluated_frames: number; mean_error_px: number | null; p95_error_px: number | null; criteria_passed: boolean | null }>; previews: { frame_index: number }[]; config: { geometry?: { stimulus_width_px: number; stimulus_height_px: number } } };
const labels: Record<string, string> = { queued: 'Na fila', running: 'Processando', completed: 'Concluído', failed: 'Falhou' };
const descriptions: Record<string, string> = { provided: 'Fornecida', available: 'Disponível', unavailable: 'Indisponível', rejected: 'Rejeitada', baseline: 'Sem calibração', calibrated: 'Calibrada', calibration: 'Calibração', validation: 'Validação', stimulus: 'Estímulo', unknown: 'Fase não associada', no_face: 'Rosto não detectado', multiple_faces: 'Múltiplos rostos', invalid_crop: 'Recorte inválido', invalid_landmarks: 'Landmarks inválidos', not_configured: 'Não configurada', insufficient_calibration: 'Dados insuficientes de calibração', outside_stimulus: 'Fora da apresentação do estímulo', outside_presented_frame_interval: 'Sem quadro apresentado neste intervalo', synchronization_unavailable: 'Sincronização indisponível', synchronization_rejected: 'Sincronização rejeitada', outside_anchor_range: 'Fora do intervalo temporal medido', missing_camera_timestamp: 'Quadro sem timestamp', missing_temporal_correspondence: 'Correspondência temporal ausente' };
const describe = (value: string | null | undefined) => value ? descriptions[value] || value : '';
const coordinates = (point: number[] | null) => point?.map(v => v.toFixed(2)).join(', ') ?? 'Ausente';


async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Não foi possível concluir a solicitação.');
  return value as T;
}

export default function Analysis({ sessionId, experimentId }: { sessionId: string; experimentId: string }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [rotation, setRotation] = useState('0');
  const [mirrored, setMirrored] = useState(false);
  const [config, setConfig] = useState<Record<string, unknown>>({ schema_version: 1 });
  const [summary, setSummary] = useState<Summary | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [offset, setOffset] = useState(0);
  const [sample, setSample] = useState<Sample | null>(null);
  const [calibrated, setCalibrated] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const sequence = useRef(0);
  const current = runs.find(r => r.id === selected);

  useEffect(() => {
    let active = true;
    const poll = () => request<Run[]>(`/api/sessions/${sessionId}/runs`).then(value => {
      if (active) { setRuns(value); setSelected(old => old || value[0]?.id || ''); }
    }).catch(e => { if (active) setError(String(e.message)); });
    void poll();
    const timer = setInterval(poll, 2000);
    return () => { active = false; clearInterval(timer); };
  }, [sessionId]);

  useEffect(() => {
    sequence.current += 1;
    setSummary(null); setSamples([]); setSample(null);
    if (!selected || current?.status !== 'completed') return;
    let active = true;
    Promise.all([request<Summary>(`/api/runs/${selected}/summary`), request<{ items: Sample[] }>(`/api/runs/${selected}/samples?offset=${offset}&limit=50`)])
      .then(([report, data]) => { if (active) { setSummary(report); setSamples(data.items); } })
      .catch(e => { if (active) setError(String(e.message)); });
    return () => { active = false; };
  }, [selected, current?.status, offset]);

  async function start() {
    setBusy(true); setError('');
    try {
      const run = await request<Run>(`/api/sessions/${sessionId}/runs`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config: { ...config, schema_version: 1, capture: { rotation_degrees: Number(rotation), mirrored } } }) });
      setRuns(old => [run, ...old]); setSelected(run.id); setOffset(0);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function importConfig(file?: File) {
    if (!file) return;
    try {
      if (file.size > 2_000_000) throw new Error('A configuração deve ter até 2 MB.');
      const value = JSON.parse(await file.text());
      if (!value || value.schema_version !== 1) throw new Error('Configuração deve usar schema_version 1.');
      setConfig(value); setRotation(String(value.capture?.rotation_degrees ?? 0)); setMirrored(Boolean(value.capture?.mirrored)); setError('');
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  async function playback() {
    if (!video.current || !selected) return;
    const ticket = ++sequence.current;
    try {
      const value = await request<{ sample: Sample | null }>(`/api/runs/${selected}/at?time_ms=${video.current.currentTime * 1000}`);
      if (ticket === sequence.current) setSample(value.sample);
    } catch { if (ticket === sequence.current) setSample(null); }
  }

  const point = sample ? (calibrated ? sample.calibrated_stimulus_px : sample.stimulus_px) : null;
  const dimensions = summary?.config.geometry;
  const activeRun = runs.some(r => r.status === 'queued' || r.status === 'running');
  return <section aria-label="Análise do olhar">
    <h4>Análise do olhar</h4>
    <p>As previsões são experimentais. A conversão para a tela exige medidas físicas; o tempo do estímulo exige correspondência temporal medida. A calibração usa somente os alvos reservados para ajuste.</p>
    <label>Rotação para deixar a câmera em pé <select value={rotation} onChange={e => setRotation(e.target.value)}>{[0, 90, 180, 270].map(v => <option key={v} value={v}>{v}°</option>)}</select></label>
    <label><input type="checkbox" checked={mirrored} onChange={e => setMirrored(e.target.checked)} /> Pixels da gravação espelhados</label>
    <p><label>Importar medidas, sincronização e protocolo (JSON v1) <input type="file" accept="application/json,.json" onChange={e => void importConfig(e.target.files?.[0])} /></label></p>
    <details><summary>Conferir configuração da próxima execução</summary><pre>{JSON.stringify({ ...config, capture: { rotation_degrees: Number(rotation), mirrored } }, null, 2)}</pre></details>
    <button type="button" onClick={() => void start()} disabled={busy || activeRun}>{busy ? 'Enviando…' : 'Executar análise'}</button>
    {error && <p role="alert">{error}</p>}
    {runs.length > 0 && <p><label>Execução <select value={selected} onChange={e => { setSelected(e.target.value); setOffset(0); }}>{runs.map(run => <option key={run.id} value={run.id}>{new Date(run.created_at).toLocaleString()} · {labels[run.status] || run.status} · {run.id.slice(0, 8)}</option>)}</select></label></p>}
    {current && <button type="button" onClick={() => {
      setConfig(current.config);
      const capture = current.config.capture as { rotation_degrees?: number; mirrored?: boolean } | undefined;
      setRotation(String(capture?.rotation_degrees ?? 0)); setMirrored(Boolean(capture?.mirrored));
    }}>Reutilizar configuração desta execução</button>}
    {current && <p aria-live="polite">{labels[current.status] || current.status}{current.progress && ` · ${current.progress.frames_processed} quadros processados`}</p>}
    {current?.error && <pre role="alert">{current.error}</pre>}
    {summary && <>
      <p>{summary.valid_frames} / {summary.frames} quadros com inferência · {(summary.invalid_fraction * 100).toFixed(1)}% inválidos · {summary.processing_seconds.toFixed(1)} s de processamento</p>
      <p>Geometria: {describe(summary.geometry_status)} · Sincronização: {describe(summary.synchronization.status)} {summary.synchronization.error_bound_ms !== undefined && `(erro declarado + residual: ${summary.synchronization.error_bound_ms.toFixed(3)} ms)`} · Calibração: {describe(summary.calibration.status)} {describe(summary.calibration.reason)}</p>
      <table><caption>Erro nos alvos de validação, sem uso no ajuste</caption><thead><tr><th>Variante</th><th>Amostras</th><th>Erro médio (px)</th><th>P95 (px)</th><th>Critérios</th></tr></thead><tbody>{Object.entries(summary.validation).map(([name, metric]) => <tr key={name}><td>{describe(name)}</td><td>{metric.evaluated_frames}</td><td>{metric.mean_error_px?.toFixed(2) ?? 'Indisponível'}</td><td>{metric.p95_error_px?.toFixed(2) ?? 'Indisponível'}</td><td>{metric.criteria_passed === null ? 'Não avaliados' : metric.criteria_passed ? 'Atendidos nesta avaliação' : 'Não atendidos'}</td></tr>)}</tbody></table>
      <p><a href={`/api/runs/${selected}/export/csv`}>Exportar CSV</a> · <a href={`/api/runs/${selected}/export/jsonl`}>Exportar JSONL</a> · <a href={`/api/runs/${selected}/summary`} download>Relatório e proveniência</a></p>
      <details><summary>Inspecionar recortes: rosto, olho esquerdo, olho direito</summary>{summary.previews.map(p => <figure key={p.frame_index}><img style={{ maxWidth: '100%' }} src={`/api/runs/${selected}/previews/${p.frame_index}`} alt={`Recortes do quadro ${p.frame_index}`} /><figcaption>Quadro {p.frame_index}</figcaption></figure>)}</details>
      <label><input type="checkbox" checked={calibrated} onChange={e => setCalibrated(e.target.checked)} /> Visualizar variante calibrada</label>
      <div style={{ position: 'relative', width: '100%', ...(dimensions ? { aspectRatio: `${dimensions.stimulus_width_px}/${dimensions.stimulus_height_px}` } : {}) }}>
        <video style={{ display: 'block', width: '100%', height: '100%' }} ref={video} controls preload="metadata" src={`/api/experiments/${experimentId}/stimulus`} onTimeUpdate={() => void playback()} onSeeked={() => void playback()} />
        {dimensions && point && point[0] >= 0 && point[0] < dimensions.stimulus_width_px && point[1] >= 0 && point[1] < dimensions.stimulus_height_px && <span aria-label="Olhar estimado" style={{ position: 'absolute', pointerEvents: 'none', left: `${point[0] / dimensions.stimulus_width_px * 100}%`, top: `${point[1] / dimensions.stimulus_height_px * 100}%`, transform: 'translate(-50%, -50%)', borderRadius: '50%', width: 14, height: 14, background: '#ff3366', border: '2px solid white' }} />}
      </div>
      <p>{sample ? `Quadro ${sample.frame_index} · estímulo ${sample.stimulus_time_ms?.toFixed(3)} ms · ponto ${point ? point.map(v => v.toFixed(2)).join(', ') + ' px' : 'indisponível'} · ${describe(sample.reason || sample.temporal_reason || sample.phase)}` : 'Sem amostra associada a este quadro do estímulo.'}</p>
      <div style={{ overflowX: 'auto' }}><table><caption>Amostras da câmera; coordenadas do vídeo original</caption><thead><tr><th>Quadro</th><th>PTS / base</th><th>Estímulo (ms)</th><th>Bruto (cm)</th><th>Tela (px)</th><th>Vídeo (px)</th><th>Validade</th></tr></thead><tbody>{samples.map(row => <tr key={row.frame_index}><td><button type="button" onClick={() => { setSample(row); if (video.current && row.stimulus_time_ms !== null) video.current.currentTime = row.stimulus_time_ms / 1000; }}>{row.frame_index}</button></td><td>{row.camera_pts} · {row.camera_time_base?.join('/')}</td><td>{row.stimulus_time_ms?.toFixed(3) ?? 'Ausente'}</td><td>{coordinates(row.prediction_cm)}</td><td>{coordinates(calibrated ? row.calibrated_screen_px : row.screen_px)}</td><td>{coordinates(calibrated ? row.calibrated_stimulus_px : row.stimulus_px)}</td><td>{describe(row.reason) || (row.phase === 'calibration' || row.phase === 'validation' ? describe(row.phase) : describe(row.temporal_reason)) || ((calibrated ? row.calibrated_outside_stimulus : row.outside_stimulus) ? 'Fora do vídeo' : row.valid ? 'Inferência válida' : 'Inválido')}</td></tr>)}</tbody></table></div>
      <button type="button" disabled={offset === 0} onClick={() => setOffset(v => Math.max(0, v - 50))}>Amostras anteriores</button> <button type="button" disabled={samples.length < 50} onClick={() => setOffset(v => v + 50)}>Próximas amostras</button>
    </>}
  </section>;
}
