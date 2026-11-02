import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';

type Stimulus = { name: string; size: number; duration: number; width: number; height: number; codec: string };
type Experiment = { id: string; name: string; description: string; state: string; code: string | null; stimulus: Stimulus | null; protocol: { label: string; phases: {name: string}[] } | null; pending: string[] };

export default function Experiments() {
  const [items, setItems] = useState<Experiment[]>([]);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Experiment | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const xhr = useRef<XMLHttpRequest | null>(null);
  const key = useRef(crypto.randomUUID());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/experiments?limit=50&offset=${offset}`);
      if (!response.ok) throw new Error();
      const data = await response.json() as { items: Experiment[] };
      setItems(data.items); setError('');
    } catch { setError('Não foi possível carregar os experimentos. Verifique a conexão e tente novamente.'); }
    finally { setLoading(false); }
  }, [offset]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => () => { xhr.current?.abort(); }, []);
  function open(item: Experiment | null) {
    setSelected(item); setName(item?.name ?? ''); setDescription(item?.description ?? ''); setFile(null);
    key.current = crypto.randomUUID(); setError(''); setEditing(true);
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (busy) return; setBusy(true); setError('');
    try {
      const response = await fetch(selected ? `/api/experiments/${selected.id}` : '/api/experiments', {
        method: selected ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json', ...(selected ? {} : { 'Idempotency-Key': key.current }) },
        body: JSON.stringify({ name, description }),
      });
      if (!response.ok) throw new Error(response.status === 409 ? 'Esta tentativa já foi usada com outros dados ou o experimento foi publicado.' : 'Não foi possível salvar o rascunho. Confira os campos e tente novamente.');
      setSelected(await response.json() as Experiment); await load();
    } catch (err) { setError(err instanceof Error ? err.message : 'Não foi possível salvar o rascunho.'); }
    finally { setBusy(false); }
  }
  async function action(path: string, method: string) {
    if (!selected || busy) return; setBusy(true); setPublishing(path === 'publish'); setError('');
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`/api/experiments/${selected.id}/${path}`, { method, signal: controller.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Não foi possível concluir a operação.');
      setSelected(data as Experiment);
    } catch (err) { setError(controller.signal.aborted ? 'A API demorou para responder. Confira o estado do experimento e tente novamente.' : err instanceof Error ? err.message : 'Falha na operação.'); }
    finally { window.clearTimeout(timeout); setBusy(false); setPublishing(false); }
  }
  function upload() {
    if (!selected || !file || busy) return;
    setBusy(true); setError(''); setProgress(0);
    const request = new XMLHttpRequest(); xhr.current = request;
    request.open('PUT', `/api/experiments/${selected.id}/stimulus`);
    request.timeout = 300_000;
    request.upload.onprogress = event => { if (event.lengthComputable) setProgress(Math.round(event.loaded / event.total * 100)); };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) { setSelected(JSON.parse(request.responseText) as Experiment); setFile(null); }
      else { try { setError(JSON.parse(request.responseText).detail || 'Falha no envio.'); } catch { setError(request.status === 413 ? 'Vídeo excede o limite de 100 MB.' : 'Falha no envio.'); } }
    };
    request.onerror = () => setError('A conexão foi interrompida durante o envio. Confira a conexão com o servidor e se o navegador está em modo offline; depois tente novamente.');
    request.ontimeout = () => setError('O envio demorou mais de 5 minutos. Verifique a conexão e tente novamente.');
    request.onabort = () => setError('Envio cancelado.');
    request.onloadend = () => { xhr.current = null; setBusy(false); setProgress(null); };
    const form = new FormData(); form.append('file', file); request.send(form);
  }
  const published = selected?.state === 'published';
  return <section className="detail-card experiments" aria-labelledby="experiments-title">
    <div className="heading-row"><div><h2 id="experiments-title">Experimentos</h2><p>Crie e retome seus experimentos.</p></div><button className="refresh-button" type="button" onClick={() => open(null)} disabled={busy}>Novo experimento</button></div>
    {error && <p role="alert" className="experiment-error">{error}</p>}
    {editing ? <>
      <form onSubmit={event => void save(event)}>
        <label>Nome <input value={name} onChange={event => setName(event.target.value)} required maxLength={200} disabled={busy || published} /></label>
        <label>Descrição <textarea value={description} onChange={event => setDescription(event.target.value)} maxLength={5000} disabled={busy || published} /></label>
        {!published && <button className="refresh-button" disabled={busy || !name.trim()}>{busy ? 'Aguarde…' : 'Salvar rascunho'}</button>}
      </form>
      {selected && <>
        <h3>Vídeo de estímulo</h3><p>MP4 H.264, até 30 segundos e 100 MB. Depois de selecionar o arquivo, clique em Enviar vídeo e aguarde a confirmação.</p>
        {!selected.stimulus && <p className="experiment-pending" role="status">Nenhum vídeo enviado.</p>}
        {selected.stimulus && <><p>Vídeo enviado: {selected.stimulus.name} · {selected.stimulus.duration.toFixed(1)} s · {selected.stimulus.width} × {selected.stimulus.height}</p><video controls src={`/api/experiments/${selected.id}/stimulus`} /></>}
        {!published && <><label>Selecionar vídeo <input type="file" accept="video/mp4" onChange={event => setFile(event.target.files?.[0] ?? null)} disabled={busy} /></label>
          <div className="experiment-actions"><button type="button" className="refresh-button" onClick={upload} disabled={busy || !file}>Enviar vídeo</button>{progress !== null && <><progress max="100" value={progress} aria-label="Progresso do envio" /><span>{progress}%</span><button type="button" className="refresh-button" onClick={() => xhr.current?.abort()}>Cancelar envio</button></>}</div></>}
        <h3>Protocolo</h3><p>Android provisório: marcador A, calibração, descanso, estímulo, validação e marcador B. As posições e durações ainda precisam de validação científica.</p>
        {!published && <button className="refresh-button" type="button" disabled={busy} onClick={() => void action('protocol', 'PUT')}>{selected.protocol ? 'Protocolo selecionado' : 'Selecionar protocolo provisório'}</button>}
        <h3>Revisão</h3><p>{selected.name} · {selected.stimulus?.name ?? 'Vídeo pendente'} · {selected.protocol?.label ?? 'Protocolo pendente'}</p>
        {selected.protocol && <p>Fases: {selected.protocol.phases.map(phase => phase.name.replace(/_/g, ' ')).join(' → ')}. Alvos: 2 segundos por posição; descanso: 2 segundos; marcadores: dois flashes de 200 ms.</p>}
        {selected.pending.length > 0 && <div className="experiment-pending" role="status"><strong>Para publicar:</strong><ul>{selected.pending.map(item => <li key={item}>{item}</li>)}</ul></div>}
        {published ? <p role="status">Publicado. Código: <strong>{selected.code}</strong></p> : <button className="refresh-button" type="button" disabled={busy || selected.pending.length > 0} onClick={() => void action('publish', 'POST')}>{publishing ? 'Publicando…' : 'Publicar experimento'}</button>}
      </>}
      <p><button className="refresh-button" type="button" disabled={busy} onClick={() => { setEditing(false); setError(''); void load(); }}>Voltar à lista</button></p>
    </> : <>
      {loading ? <p>Carregando experimentos…</p> : items.length === 0 ? <p>Nenhum experimento nesta página.</p> : <ul className="experiment-list">{items.map(item => <li key={item.id}><div><strong>{item.name}</strong><p>{item.code ? `Publicado · ${item.code}` : 'Rascunho'}</p></div><button className="refresh-button" type="button" onClick={() => open(item)}>Abrir</button></li>)}</ul>}
      <div className="experiment-actions"><button className="refresh-button" type="button" onClick={() => void load()} disabled={loading}>Atualizar lista</button><button className="refresh-button" type="button" onClick={() => setOffset(Math.max(0, offset - 50))} disabled={loading || offset === 0}>Anterior</button><button className="refresh-button" type="button" onClick={() => setOffset(offset + 50)} disabled={loading || items.length < 50}>Próxima</button></div>
    </>}
  </section>;
}
