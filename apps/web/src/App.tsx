import { useCallback, useEffect, useRef, useState } from 'react';

type Health = {
  status: 'ok' | string;
  service: string;
  version: string;
};

type ApiInfo = {
  name: string;
  version: string;
  description: string;
  capabilities: {
    session_upload: boolean;
    gaze_processing: boolean;
  };
};

type ApiSnapshot = {
  health: Health;
  info: ApiInfo;
};

type ConnectionState = 'loading' | 'connected' | 'error';

async function readJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal,
  });

  if (!response.ok) {
    throw new Error(`A API respondeu com status ${response.status}.`);
  }

  return (await response.json()) as T;
}

function CapabilityValue({ value }: { value: boolean | undefined }) {
  if (value === undefined) {
    return <span className="capability-value capability-pending">Aguardando API</span>;
  }

  return (
    <span className={`capability-value ${value ? 'capability-ready' : 'capability-pending'}`}>
      {value ? 'Disponível' : 'Em preparação'}
    </span>
  );
}

function App() {
  const [state, setState] = useState<ConnectionState>('loading');
  const [snapshot, setSnapshot] = useState<ApiSnapshot | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const requestNumber = useRef(0);
  const requestController = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    const currentRequest = ++requestNumber.current;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const timeout = window.setTimeout(() => {
      controller.abort(new DOMException('A API não respondeu no prazo.', 'TimeoutError'));
    }, 10_000);

    setState('loading');
    setErrorMessage('');

    try {
      const [health, info] = await Promise.all([
        readJson<Health>('/api/health', controller.signal),
        readJson<ApiInfo>('/api/info', controller.signal),
      ]);

      if (health.status !== 'ok') {
        throw new Error('A API ainda não está pronta.');
      }

      if (currentRequest !== requestNumber.current) return;
      setSnapshot({ health, info });
      setState('connected');
    } catch (error) {
      if (currentRequest !== requestNumber.current) return;

      const timedOut = controller.signal.reason?.name === 'TimeoutError';
      const wasCancelled = controller.signal.aborted;
      controller.abort();

      if (wasCancelled && !timedOut) return;
      setState('error');
      setErrorMessage(timedOut
        ? 'A API não respondeu dentro do tempo esperado.'
        : error instanceof Error
          ? error.message
          : 'Não foi possível confirmar a conexão com a API.');
    } finally {
      window.clearTimeout(timeout);
      if (currentRequest === requestNumber.current) {
        requestController.current = null;
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => {
      ++requestNumber.current;
      requestController.current?.abort();
      requestController.current = null;
    };
  }, [refresh]);

  const connected = state === 'connected' && snapshot !== null;
  const serviceName = snapshot?.info.name ?? 'Eye Tracker API';

  return (
    <main className="page-shell" aria-busy={state === 'loading'}>
      <header className="topbar">
        <a className="brand" href="/" aria-label="Eye Tracker, página inicial">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 40 40" fill="none">
              <path
                d="M4 20s5.8-9 16-9 16 9 16 9-5.8 9-16 9S4 20 4 20Z"
                stroke="currentColor"
                strokeWidth="2"
              />
              <circle cx="20" cy="20" r="5" stroke="currentColor" strokeWidth="2" />
              <circle cx="20" cy="20" r="1.5" fill="currentColor" />
            </svg>
          </span>
          <span>Eye Tracker</span>
        </a>
        <span className="topbar-label">Monitor de serviço</span>
      </header>

      <section className="content" aria-labelledby="page-title">
        <div className="eyebrow"><span aria-hidden="true" /> PLATAFORMA DE RASTREAMENTO OCULAR</div>
        <div className="heading-row">
          <div>
            <h1 id="page-title">Eye Tracker</h1>
            <p className="intro">
              Acompanhe a disponibilidade da API e o estado das capacidades da plataforma.
            </p>
          </div>
          <button
            className="refresh-button"
            type="button"
            onClick={() => void refresh()}
            disabled={state === 'loading'}
          >
            <svg
              className={state === 'loading' ? 'refresh-icon is-spinning' : 'refresh-icon'}
              viewBox="0 0 20 20"
              fill="none"
              aria-hidden="true"
            >
              <path d="M16.5 9.2A6.5 6.5 0 0 0 5 5.1L3.5 6.5M3.5 6.5V3.8M3.5 6.5h2.8M3.5 10.8A6.5 6.5 0 0 0 15 14.9l1.5-1.4m0 0v2.7m0-2.7h-2.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {state === 'loading' ? 'Atualizando' : 'Recarregar'}
          </button>
        </div>

        <section className={`connection-card ${state}`} aria-labelledby="connection-heading">
          <div className="connection-main">
            <div className={`connection-icon ${state}`} aria-hidden="true">
              {state === 'loading' ? (
                <span className="loading-ring" />
              ) : state === 'connected' ? (
                <svg viewBox="0 0 24 24" fill="none"><path d="m6 12.5 4 4L18.5 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none"><path d="M12 7v5m0 4h.01M4.9 19h14.2c1.2 0 1.9-1.3 1.3-2.3L13.3 4.5a1.5 1.5 0 0 0-2.6 0L3.6 16.7c-.6 1 .1 2.3 1.3 2.3Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
              )}
            </div>
            <div>
              <p className="card-label" id="connection-heading">Conexão com a API</p>
              <p className="connection-status" role="status" aria-live="polite">
                {state === 'loading' && 'Verificando conexão…'}
                {state === 'connected' && 'API conectada'}
                {state === 'error' && 'API indisponível'}
              </p>
            </div>
          </div>
          <div className="connection-details">
            <span className={`status-dot ${state}`} aria-hidden="true" />
            <span>
              {state === 'loading' && 'Consultando serviço'}
              {state === 'connected' && 'Serviço respondendo'}
              {state === 'error' && 'Aguardando resposta'}
            </span>
          </div>
          {state === 'error' && (
            <p className="error-message" role="alert">
              {errorMessage || 'Não foi possível confirmar a conexão com a API agora.'}
            </p>
          )}
        </section>

        <section className="details-grid" aria-label="Detalhes do serviço e capacidades">
          <article className="detail-card service-card">
            <div className="section-heading">
              <span className="section-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none"><rect x="4" y="4" width="16" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.6"/><rect x="4" y="14" width="16" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.6"/><path d="M7 7h.01M7 17h.01M10 7h7M10 17h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
              </span>
              <div>
                <h2>Serviço</h2>
                <p>Estado informado pela API</p>
              </div>
            </div>
            <dl className="service-properties">
              <div>
                <dt>Nome</dt>
                <dd>{connected ? serviceName : '—'}</dd>
              </div>
              <div>
                <dt>Versão</dt>
                <dd>{connected && snapshot ? snapshot.health.version : '—'}</dd>
              </div>
            </dl>
            {connected && snapshot && snapshot.info.description && (
              <p className="service-description">{snapshot.info.description}</p>
            )}
          </article>

          <article className="detail-card capabilities-card">
            <div className="section-heading">
              <span className="section-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.6"/><path d="M12 8v4l2.5 2.5M4.5 5.5l2 2M19.5 5.5l-2 2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </span>
              <div>
                <h2>Capacidades</h2>
                <p>Disponibilidade atual da plataforma</p>
              </div>
            </div>
            <ul className="capability-list">
              <li>
                <span className="capability-name">Coleta em Android</span>
                <span className="capability-value capability-pending">Em verificação</span>
              </li>
              <li>
                <span className="capability-name">Processamento do olhar</span>
                <CapabilityValue value={connected && snapshot ? snapshot.info.capabilities.gaze_processing : undefined} />
              </li>
              <li>
                <span className="capability-name">Envio de sessões</span>
                <CapabilityValue value={connected && snapshot ? snapshot.info.capabilities.session_upload : undefined} />
              </li>
            </ul>
          </article>
        </section>

        <aside className="status-note" aria-label="Sobre o estado do projeto">
          <span className="note-mark" aria-hidden="true">i</span>
          <p>
            A coleta no aparelho ainda precisa de validação. O envio de sessões e o processamento do olhar serão disponibilizados nas próximas etapas.
          </p>
        </aside>

        <footer className="page-footer">
          <span>Eye Tracker <span aria-hidden="true">·</span> {connected && snapshot ? `v${snapshot.info.version}` : 'serviço web'}</span>
          <a href="/docs" target="_blank" rel="noreferrer">
            Documentação da API
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M6 3h7v7M13 3 7 9M11 9v3a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </a>
        </footer>
      </section>
    </main>
  );
}

export default App;
