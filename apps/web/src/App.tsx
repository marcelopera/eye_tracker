import Experiments from './Experiments';

function App() {
  return (
    <main className="page-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Eye Tracker, página inicial">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 40 40" fill="none">
              <path d="M4 20s5.8-9 16-9 16 9 16 9-5.8 9-16 9S4 20 4 20Z" stroke="currentColor" strokeWidth="2" />
              <circle cx="20" cy="20" r="5" stroke="currentColor" strokeWidth="2" />
              <circle cx="20" cy="20" r="1.5" fill="currentColor" />
            </svg>
          </span>
          <span>Eye Tracker</span>
        </a>
        <span className="topbar-label">Experimentos</span>
      </header>
      <section className="content" aria-labelledby="page-title">
        <div className="eyebrow"><span aria-hidden="true" /> PLATAFORMA DE RASTREAMENTO OCULAR</div>
        <div className="heading-row">
          <div>
            <h1 id="page-title">Eye Tracker</h1>
            <p className="intro">Crie um experimento, receba as coletas e gere a demonstração em MP4.</p>
          </div>
        </div>
        <Experiments />
        <aside className="status-note" aria-label="Sobre o estado do projeto">
          <span className="note-mark" aria-hidden="true">i</span>
          <p>As demonstrações mostram o olhar estimado e as etapas do processamento, com o erro de validação da sessão.</p>
        </aside>
        <footer className="page-footer"><span>Eye Tracker</span></footer>
      </section>
    </main>
  );
}

export default App;
