import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
3. services/web/src/App.tsx
import React, { useState } from 'react'

interface Citation {
  doc_id: string
  page: number
  snippet: string
  bbox: null
}

interface ApiResponse {
  answer: string
  citations: Citation[]
}

function App() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState<ApiResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [language, setLanguage] = useState<'en' | 'fr'>('en')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return

    setLoading(true)
    setError(null)
    setResponse(null)

    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query.trim(),
          k: 6,
          lang_hint: language,
        }),
      })

      if (!res.ok) throw new Error(`API error: ${res.status}`)
      const data: ApiResponse = await res.json()
      setResponse(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.title}>Government Document Search</h1>
        <p style={styles.subtitle}>Ask questions about government documents</p>
      </header>

      <main style={styles.main}>
        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.inputGroup}>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your question..."
              style={styles.input}
              disabled={loading}
            />
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as 'en' | 'fr')}
              style={styles.select}
              disabled={loading}
            >
              <option value="en">English</option>
              <option value="fr">Français</option>
            </select>
            <button
              type="submit"
              style={loading ? { ...styles.button, ...styles.buttonDisabled } : styles.button}
              disabled={loading || !query.trim()}
            >
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>

          {error && (
            <div style={styles.error}>
              <strong>Error:</strong> {error}
            </div>
          )}

          {response && (
            <div style={styles.results}>
              <div style={styles.answer}>
                <h2 style={styles.answerTitle}>Answer</h2>
                <p style={styles.answerText}>{response.answer}</p>
              </div>

              {response.citations.length > 0 && (
                <div style={styles.citations}>
                  <h3 style={styles.citationsTitle}>Sources</h3>
                  {response.citations.map((cite, idx) => (
                    <div key={idx} style={styles.citation}>
                      <div style={styles.citationHeader}>
                        <span style={styles.citationDoc}>Document: {cite.doc_id}</span>
                        {cite.page && <span style={styles.citationPage}>Page {cite.page}</span>}
                      </div>
                      {cite.snippet && (
                        <p style={styles.citationSnippet}>{cite.snippet}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </form>
      </main>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    backgroundColor: '#f5f5f5',
  },
  header: {
    backgroundColor: '#1a1a1a',
    color: 'white',
    padding: '2rem',
    textAlign: 'center',
  },
  title: {
    fontSize: '2rem',
    marginBottom: '0.5rem',
  },
  subtitle: {
    fontSize: '1rem',
    opacity: 0.8,
  },
  main: {
    maxWidth: '900px',
    margin: '0 auto',
    padding: '2rem',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1.5rem',
  },
  inputGroup: {
    display: 'flex',
    gap: '0.5rem',
    flexWrap: 'wrap',
  },
  input: {
    flex: '1 1 300px',
    padding: '0.75rem',
    fontSize: '1rem',
    border: '1px solid #ccc',
    borderRadius: '4px',
  },
  select: {
    padding: '0.75rem',
    fontSize: '1rem',
    border: '1px solid #ccc',
    borderRadius: '4px',
    backgroundColor: 'white',
  },
  button: {
    padding: '0.75rem 2rem',
    fontSize: '1rem',
    backgroundColor: '#1a1a1a',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  buttonDisabled: {
    backgroundColor: '#999',
    cursor: 'not-allowed',
  },
  error: {
    padding: '1rem',
    backgroundColor: '#fee',
    border: '1px solid #fcc',
    borderRadius: '4px',
    color: '#c00',
  },
  results: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1.5rem',
  },
  answer: {
    backgroundColor: 'white',
    padding: '1.5rem',
    borderRadius: '8px',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
  },
  answerTitle: {
    fontSize: '1.25rem',
    marginBottom: '1rem',
    color: '#1a1a1a',
  },
  answerText: {
    fontSize: '1rem',
    lineHeight: '1.6',
    color: '#333',
  },
  citations: {
    backgroundColor: 'white',
    padding: '1.5rem',
    borderRadius: '8px',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
  },
  citationsTitle: {
    fontSize: '1.1rem',
    marginBottom: '1rem',
    color: '#1a1a1a',
  },
  citation: {
    padding: '1rem',
    marginBottom: '0.75rem',
    backgroundColor: '#f9f9f9',
    borderLeft: '3px solid #1a1a1a',
    borderRadius: '4px',
  },
  citationHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: '0.5rem',
    fontSize: '0.9rem',
  },
  citationDoc: {
    fontWeight: 'bold',
    color: '#555',
  },
  citationPage: {
    color: '#777',
  },
  citationSnippet: {
    fontSize: '0.9rem',
    color: '#666',
    fontStyle: 'italic',
  },
}

export default App
