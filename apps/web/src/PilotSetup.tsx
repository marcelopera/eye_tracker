import { useState } from 'react';

type Preparation = { config: Record<string, unknown>; issues: string[]; ready_for_pilot: boolean };
export const issues: Record<string, string> = {
  missing_camera_instrumentation: 'Coleta antiga: faltam os registros por quadro da câmera. Faça uma nova coleta com o app atualizado.',
  missing_physical_measurements: 'Informe as medidas físicas para obter o baseline na tela e erro em centímetros.',
  missing_display_geometry: 'A coleta não registrou a área da tela ou do vídeo.',
  unsupported_stimulus_rotation: 'A rotação deste estímulo precisa de conferência manual.',
  unknown_camera_clock: 'O aparelho não declara o relógio da câmera compatível; a associação temporal automática está desabilitada.',
  missing_timing_measurement: 'Informe a incerteza temporal medida no aparelho e sua evidência.',
  insufficient_camera_correspondences: 'Há poucos quadros da câmera para sincronizar.',
  missing_presented_frames: 'Faltam callbacks de quadros renderizados do estímulo.',
  missing_stimulus_timing: 'Faltam os timestamps dos quadros do arquivo de estímulo.',
  missing_settling_window: 'Defina quanto tempo excluir após cada troca de alvo.',
  missing_committed_targets: 'Faltam registros de apresentação dos alvos; ajuste e validação ficam indisponíveis.',
  missing_calibration_settings: 'A calibração está desabilitada.',
  insufficient_calibration_targets: 'O número de posições de calibração é menor que o mínimo escolhido.',
  missing_validation_targets: 'Faltam alvos independentes para medir o erro.',
  missing_acceptance_criteria: 'Defina os limites de erro e de perdas para avaliar o piloto.',
  interrupted_collection: 'A coleta foi interrompida.',
  rejected_synchronization: 'A incerteza temporal excedeu o limite escolhido.',
};
const axes = [
  { label: 'X à direita, Y para cima', value: [[1, 0], [0, -1]] },
  { label: 'X à direita, Y para baixo', value: [[1, 0], [0, 1]] },
  { label: 'X à esquerda, Y para cima', value: [[-1, 0], [0, -1]] },
  { label: 'X à esquerda, Y para baixo', value: [[-1, 0], [0, 1]] },
  { label: 'X para cima, Y à direita', value: [[0, 1], [-1, 0]] },
  { label: 'X para baixo, Y à direita', value: [[0, 1], [1, 0]] },
  { label: 'X para cima, Y à esquerda', value: [[0, -1], [-1, 0]] },
  { label: 'X para baixo, Y à esquerda', value: [[0, -1], [1, 0]] },
];

export default function PilotSetup({ sessionId, onPrepared }: { sessionId: string; onPrepared: (value: Record<string, unknown>, captureRecorded: boolean) => void }) {
  const [values, setValues] = useState<Record<string, string>>({ max_error_ms: '50', settling_ms: '500', C: '100', epsilon: '1', gamma: '0.01', min_samples: '30', min_targets: '5', max_mean_error_px: '100', max_invalid_fraction: '0.2' });
  const [axis, setAxis] = useState(0);
  const [kernel, setKernel] = useState('linear');
  const [calibrate, setCalibrate] = useState(true);
  const [result, setResult] = useState<Preparation | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const field = (key: string, label: string, numeric = true) => <label key={key}>{label}<input type={numeric ? 'number' : 'text'} step={numeric ? 'any' : undefined} value={values[key] ?? ''} onChange={e => { setValues(old => ({ ...old, [key]: e.target.value })); setResult(null); }} /></label>;
  async function prepare() {
    setBusy(true); setError(''); setResult(null);
    try {
      const numeric = (key: string) => {
        if (!values[key]?.trim() || !Number.isFinite(Number(values[key]))) throw new Error('Preencha os campos numéricos do grupo selecionado.');
        return Number(values[key]);
      };
      const settings: Record<string, unknown> = { settling_ms: numeric('settling_ms'),
        criteria: { max_mean_error_px: numeric('max_mean_error_px'), max_invalid_fraction: numeric('max_invalid_fraction') } };
      const physical = ['screen_width_mm', 'screen_height_mm', 'camera_x_mm', 'camera_y_mm'];
      if (physical.some(key => values[key]?.trim())) {
        if (!values.measurement_evidence?.trim() || !values.axes_evidence?.trim()) throw new Error('Registre como as dimensões e os eixos foram conferidos.');
        settings.physical = { ...Object.fromEntries(physical.map(key => [key, numeric(key)])), model_axes: axes[axis].value,
          measurement_evidence: values.measurement_evidence, axes_evidence: values.axes_evidence };
      }
      if (values.measurement_error_ms?.trim()) {
        if (!values.timing_evidence?.trim()) throw new Error('Registre a evidência da medição temporal.');
        settings.timing = { measurement_error_ms: numeric('measurement_error_ms'), max_error_ms: numeric('max_error_ms'), evidence: values.timing_evidence };
      }
      if (calibrate) settings.calibration = { kernel, ...Object.fromEntries(['C', 'epsilon', 'gamma', 'min_samples', 'min_targets'].map(key => [key, numeric(key)])) };
      const response = await fetch(`/api/sessions/${sessionId}/analysis-config`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ settings }) });
      const value = await response.json();
      if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Medidas inválidas.');
      setResult(value); onPrepared(value.config, !value.issues.includes('missing_camera_instrumentation'));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return <details><summary>Preparar análise a partir desta coleta</summary>
    <p>Tempos, orientação, alvos e área do vídeo vêm do app. Complete as medidas do aparelho. Os valores iniciais de calibração e aceitação são propostas para piloto; revise-os antes da avaliação.</p>
    <fieldset><legend>Dimensões na orientação da coleta (opcional para inferência bruta)</legend>
      {field('screen_width_mm', 'Largura da área ativa da tela (mm)')}{field('screen_height_mm', 'Altura da área ativa da tela (mm)')}
      {field('camera_x_mm', 'Centro da câmera: distância à borda esquerda da tela (mm)')}{field('camera_y_mm', 'Centro da câmera: distância à borda superior (mm; negativa se acima)')}
      {field('measurement_evidence', 'Referência da medição física', false)}
      <label>Eixos do modelo na tela<select value={axis} onChange={e => { setAxis(Number(e.target.value)); setResult(null); }}>{axes.map((item, i) => <option key={i} value={i}>{item.label}</option>)}</select></label>
      {field('axes_evidence', 'Como os eixos foram conferidos', false)}
    </fieldset>
    <fieldset><legend>Correspondência temporal e fixação</legend>
      <p>A incerteza deve incluir exposição da câmera, renderização dos alvos e apresentação no display. Callbacks do sistema precisam de conferência no aparelho.</p>
      {field('measurement_error_ms', 'Incerteza temporal medida (ms)')}{field('max_error_ms', 'Maior incerteza temporal aceita (ms)')}
      {field('timing_evidence', 'Método e referência da medição temporal', false)}{field('settling_ms', 'Excluir após cada troca de alvo (ms)')}
    </fieldset>
    <fieldset><legend>Ajuste por sessão</legend>
      <label><input type="checkbox" checked={calibrate} onChange={e => { setCalibrate(e.target.checked); setResult(null); }} /> Calibrar com os alvos reservados para ajuste</label>
      {calibrate && <><label>Kernel<select value={kernel} onChange={e => { setKernel(e.target.value); setResult(null); }}><option value="linear">Linear</option><option value="rbf">RBF</option></select></label>
        {field('C', 'C')}{field('epsilon', 'Epsilon (px)')}{field('gamma', 'Gamma (RBF)')}{field('min_samples', 'Mínimo de quadros de calibração')}{field('min_targets', 'Mínimo de posições distintas')}</>}
    </fieldset>
    <fieldset><legend>Critérios escolhidos antes da validação</legend>{field('max_mean_error_px', 'Maior erro médio aceito (px)')}{field('max_invalid_fraction', 'Maior fração de perdas aceita (0 a 1)')}</fieldset>
    <button type="button" onClick={() => void prepare()} disabled={busy}>{busy ? 'Preparando…' : 'Gerar configuração desta coleta'}</button>
    {error && <p role="alert">{error}</p>}
    {result && <div role="status"><p>{result.ready_for_pilot ? 'Configuração completa para executar o piloto. A precisão será medida nos alvos de validação.' : 'Configuração parcial carregada. Pendências:'}</p>
      <ul>{result.issues.map(issue => <li key={issue}>{issues[issue] || issue}</li>)}</ul></div>}
  </details>;
}
