import { useEffect, useState } from 'react'
import { AnimatedBackground } from './components/AnimatedBackground'
import { LogsDrawer } from './components/LogsDrawer'
import { SettingsDialog } from './components/SettingsDialog'
import { Toasts } from './components/Toasts'
import { TopBar } from './components/TopBar'
import { HomePage } from './pages/HomePage'
import { ProjectPage } from './pages/ProjectPage'
import { useStudio } from './store'
import './theme'

function parseHash(): { name: 'home' } | { name: 'project'; id: string } {
  const m = window.location.hash.match(/^#\/p\/([^/?#]+)/)
  return m ? { name: 'project', id: decodeURIComponent(m[1]) } : { name: 'home' }
}

export default function App() {
  const [route, setRoute] = useState(parseHash)
  const connect = useStudio((s) => s.connect)
  const loadEngines = useStudio((s) => s.loadEngines)
  const connected = useStudio((s) => s.connected)
  const backendReachable = useStudio((s) => s.backendReachable)

  useEffect(() => {
    connect()
    loadEngines()
    const onHash = () => setRoute(parseHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [connect, loadEngines])

  return (
    <div className="relative isolate flex min-h-screen flex-col text-white">
      <AnimatedBackground />
      <TopBar />
      {!connected && !backendReachable && (
        <div className="relative z-30 border-b border-line bg-white px-4 py-2 text-center text-sm text-black">
          Can’t reach the Dubby backend. Start it with <code className="rounded bg-black/10 px-1.5 font-mono">dubby serve</code> — or{' '}
          <code className="rounded bg-black/10 px-1.5 font-mono">dubby dev</code> to run the backend and this dev UI together. Retrying automatically…
        </div>
      )}
      <main className="relative z-10 flex-1">{route.name === 'project' ? <ProjectPage key={route.id} id={route.id} /> : <HomePage />}</main>
      <LogsDrawer />
      <SettingsDialog />
      <Toasts />
    </div>
  )
}
