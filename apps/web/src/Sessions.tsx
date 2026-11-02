import { useCallback, useEffect, useState } from 'react';

type Session = { id: string; local_id: string; participant_code: string; receipt_status: 'pending' | 'received'; processing_status: 'unavailable' };

export default function Sessions({ experimentId }: { experimentId: string }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(false);
    fetch(`/api/experiments/${encodeURIComponent(experimentId)}/sessions?limit=50&offset=${offset}`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(); return response.json() as Promise<Session[]>; })
      .then(setSessions)
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [experimentId, offset, revision]);

  return <section aria-label="Coletas">
    <h3>Coletas</h3>
    <p>O recebimento indica apenas que os arquivos passaram pelas verificações de envio. Processamento e resultados ainda não estão disponíveis.</p>
    {error ? <p role="alert">Não foi possível carregar as coletas.</p> : loading ? <p>Carregando coletas…</p> : sessions.length === 0 ? <p>Nenhuma coleta nesta página.</p> :
      <ul className="experiment-list">{sessions.map(session => <li key={session.id}><div>
        <strong>Participante: {session.participant_code}</strong>
        <p>Sessão: {session.id}</p><p>Identificador local: {session.local_id}</p>
        <p>{session.receipt_status === 'received' ? 'Arquivos recebidos' : 'Aguardando arquivos'} · Processamento indisponível</p>
        {session.receipt_status === 'received' && <details><summary>Inspecionar arquivos originais</summary>
          <p>Vídeo da câmera e eventos originais do protótipo. Os relógios não estão sincronizados com o estímulo; esses arquivos não são resultados de olhar.</p>
          <video controls preload="none" src={`/api/sessions/${encodeURIComponent(session.id)}/video`} />
          <p><a href={`/api/sessions/${encodeURIComponent(session.id)}/events`} download={`sessao-${session.id}.json`}>Baixar eventos originais</a></p>
        </details>}
      </div></li>)}</ul>}
    <div className="experiment-actions">
      <button className="refresh-button" type="button" onClick={refresh} disabled={loading}>Atualizar coletas</button>
      <button className="refresh-button" type="button" onClick={() => setOffset(Math.max(0, offset - 50))} disabled={loading || offset === 0}>Anterior</button>
      <button className="refresh-button" type="button" onClick={() => setOffset(offset + 50)} disabled={loading || sessions.length < 50}>Próxima</button>
    </div>
  </section>;
}
