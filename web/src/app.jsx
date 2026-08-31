import { useEffect, useState } from 'preact/hooks'
import * as api from './api.js'
import { Chrome } from './ui/Chrome.jsx'
import { Sessions } from './ui/Sessions.jsx'
import { NewSession } from './ui/NewSession.jsx'
import { Session } from './ui/Session.jsx'
import { Disclaimer } from './ui/Disclaimer.jsx'
import { accepted, accept } from './terms.js'

// Two views, so a hash fragment and a switch rather than a router.
const routeOf = (hash) => {
  const match = /^#\/session\/(.+)$/.exec(hash || '')
  if (match) return { view: 'session', id: match[1] }
  return { view: hash === '#/new' ? 'new' : 'list' }
}

const go = (hash) => {
  window.location.hash = hash
}

export function App() {
  const [route, setRoute] = useState(routeOf(window.location.hash))
  const [sessions, setSessions] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  // 'accept' until the terms have been agreed to, then null, then 'review'
  // whenever they are reopened from the banner.
  const [terms, setTerms] = useState(accepted() ? null : 'accept')

  useEffect(() => {
    const onHash = () => setRoute(routeOf(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [route.view, route.id])

  useEffect(() => {
    if (route.view !== 'list') return
    api.listSessions().then(setSessions, setError)
  }, [route.view])

  const create = async (body) => {
    setBusy(true)
    setError(null)
    try {
      const session = await api.createSession(body)
      go(`#/session/${session.id}`)
    } catch (problem) {
      setError(problem)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Chrome onHome={() => go('#/')} onTerms={() => setTerms('review')} />
      {terms ? (
        <Disclaimer
          mode={terms}
          onAccept={() => {
            accept()
            setTerms(null)
          }}
          onClose={() => setTerms(null)}
        />
      ) : null}
      {error ? <div class="page"><div class="error" style="margin-top: 20px;">{String(error.message)}</div></div> : null}
      {route.view === 'session' ? (
        <Session id={route.id} />
      ) : (
        <div class="page">
          {route.view === 'new' ? (
            <NewSession onCreate={create} onCancel={() => go('#/')} busy={busy} />
          ) : (
            <Sessions sessions={sessions} onOpen={(id) => go(`#/session/${id}`)} onNew={() => go('#/new')} />
          )}
        </div>
      )}
    </>
  )
}
