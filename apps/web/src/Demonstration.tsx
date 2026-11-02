import { useCallback, useEffect, useRef, useState } from 'react';

type Run = {
  id: string;
  kind: string;
  status: string;
  error: string | null;
  demonstration_available: boolean;
  progress: { frames_processed: number; stage: string } | null;
};
const stages: Record<string, string> = {
  inference: 'Estimando o olhar', evaluation: 'Calibrando a sessão', rendering: 'Montando o MP4',
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Não foi possível concluir a solicitação.');
  return value as T;
}

export default function Demonstration({ sessionId }: { sessionId: string }) {
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const sequence = useRef(0);
  const active = run?.status === 'queued' || run?.status === 'running';

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const ticket = ++sequence.current;
    try {
      const value = await request<Run[]>(`/api/sessions/${sessionId}/runs`, { signal });
      if (ticket === sequence.current && !signal?.aborted) {
        setRun(value.find(item => item.kind === 'demonstration') ?? null);
        setError('');
      }
    } catch (e) {
      if (ticket === sequence.current && !signal?.aborted) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (ticket === sequence.current && !signal?.aborted) setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => { controller.abort(); sequence.current += 1; };
  }, [refresh]);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => { void refresh(controller.signal); }, 2000);
    return () => { window.clearInterval(timer); controller.abort(); };
  }, [active, refresh]);

  async function generate() {
    if (busy || active) return;
    sequence.current += 1;
    setBusy(true); setError('');
    try {
      const value = await request<Run>(`/api/sessions/${sessionId}/demonstration`, { method: 'POST' });
      setRun(value);
    } catch (e) {
      // Refresh an attempt that may have been accepted before a connection failure.
      await refresh();
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  return <section className="demonstration" aria-label="Demonstração em MP4">
    <div className="experiment-actions">
      <button type="button" className="refresh-button primary-button" disabled={loading || busy || active}
        onClick={() => void generate()}>
        {busy ? 'Preparando…' : active ? 'Gerando demonstração…' : run?.demonstration_available ? 'Gerar novamente' : 'Gerar demonstração em MP4'}
      </button>
      {run?.demonstration_available && <a className="refresh-button" href={`/api/runs/${run.id}/demonstration?download=true`}>Baixar MP4</a>}
      {error && !active && <button className="refresh-button" onClick={() => void refresh()}>Atualizar</button>}
    </div>
    {active && <p role="status" aria-live="polite">{run.status === 'queued' ? 'Na fila para processamento.' :
      `${stages[run.progress?.stage ?? ''] ?? 'Processando a coleta'}${run.progress ? ` · ${run.progress.frames_processed} quadros` : ''}.`}
      {' '}Você pode sair desta página e voltar depois.</p>}
    {error && <p role="alert" className="experiment-error">{error}</p>}
    {run?.status === 'failed' && <p role="alert" className="experiment-error">Não foi possível gerar o MP4. {run.error} Você pode tentar novamente.</p>}
    {run?.demonstration_available && <>
      <video className="demonstration-video" key={run.id} controls preload="metadata" src={`/api/runs/${run.id}/demonstration`} />
      <p>Estímulo com olhar estimado, câmera, recortes e pipeline. A precisão da estimativa aparece no vídeo.</p>
    </>}
  </section>;
}
