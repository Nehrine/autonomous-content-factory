import React from 'react'
import useStore from './store/useStore'
import UploadPage from './pages/UploadPage'
import PipelinePage from './pages/PipelinePage'
import ResultsPage from './pages/ResultsPage'
import Header from './components/Header'
import { AlertTriangle, RotateCcw } from 'lucide-react'

export default function App() {
  const stage = useStore((s) => s.pipelineStage)
  const isRunning = ['uploading','researching','writing','editing'].includes(stage)
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      <Header />
      <main style={{ flex: 1, overflow: 'hidden auto' }}>
        {stage === 'idle'  && <UploadPage />}
        {isRunning         && <PipelinePage />}
        {stage === 'done'  && <ResultsPage />}
        {stage === 'error' && <ErrorView />}
      </main>
    </div>
  )
}

function ErrorView() {
  const error = useStore((s) => s.error)
  const reset = useStore((s) => s.resetPipeline)
  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', minHeight:'calc(100vh - 56px)', gap:20, padding:32, textAlign:'center' }}>
      <div style={{ width:64, height:64, borderRadius:18, background:'rgba(244,63,94,0.1)', border:'1px solid rgba(244,63,94,0.25)', display:'flex', alignItems:'center', justifyContent:'center' }}>
        <AlertTriangle size={28} color="var(--rose)" />
      </div>
      <div>
        <p className="font-display" style={{ fontSize:'1.2rem', fontWeight:700, color:'var(--t0)', marginBottom:8 }}>Pipeline Failed</p>
        <p style={{ fontSize:'0.82rem', color:'var(--t1)', maxWidth:480, lineHeight:1.65 }}>{error}</p>
      </div>
      <button onClick={reset} className="btn btn-primary" style={{ padding:'10px 24px' }}>
        <RotateCcw size={14} /> Try Again
      </button>
    </div>
  )
}
