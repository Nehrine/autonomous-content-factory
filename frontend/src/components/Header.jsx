import React from 'react'
import useStore from '../store/useStore'
import { Zap, RotateCcw } from 'lucide-react'

export default function Header() {
  const stage      = useStore((s) => s.pipelineStage)
  const reset      = useStore((s) => s.resetPipeline)
  const modelUsed  = useStore((s) => s.modelUsed)
  const provider   = useStore((s) => s.apiProvider)
  const revLog     = useStore((s) => s.revisionLog)

  const isRunning = ['uploading','researching','writing','editing'].includes(stage)
  const isDone    = stage === 'done'
  const isErr     = stage === 'error'

  return (
    <header style={{ height:52, borderBottom:'1px solid var(--b0)', background:'rgba(2,4,8,0.9)', backdropFilter:'blur(16px)', WebkitBackdropFilter:'blur(16px)', position:'sticky', top:0, zIndex:100, display:'flex', alignItems:'center', padding:'0 20px', gap:12 }}>
      {/* Logo */}
      <div style={{ display:'flex', alignItems:'center', gap:9, flexShrink:0 }}>
        <div style={{ width:28, height:28, borderRadius:9, background:'linear-gradient(135deg,#4f46e5,#7c3aed)', display:'flex', alignItems:'center', justifyContent:'center', boxShadow:'0 0 14px rgba(91,110,245,0.5)' }}>
          <Zap size={13} color="white" />
        </div>
        <span className="font-display" style={{ fontSize:'0.88rem', fontWeight:700, color:'var(--t0)' }}>
          Content <span className="grad">Factory</span>
        </span>
      </div>

      {/* Stage pill */}
      {!['idle'].includes(stage) && (
        <div style={{ display:'flex', alignItems:'center', gap:7, padding:'4px 12px', borderRadius:999, border:`1px solid ${isDone ? 'rgba(16,185,129,0.3)' : isErr ? 'rgba(244,63,94,0.3)' : 'rgba(91,110,245,0.25)'}`, background:isDone ? 'rgba(16,185,129,0.07)' : isErr ? 'rgba(244,63,94,0.07)' : 'rgba(91,110,245,0.07)', marginLeft:4 }}>
          {isRunning && <span style={{ width:6, height:6, borderRadius:'50%', background:'var(--brand)', boxShadow:'0 0 6px var(--brand)', animation:'live-pulse 2s ease-in-out infinite', display:'block' }} />}
          {isDone    && <span style={{ width:6, height:6, borderRadius:'50%', background:'var(--emerald)', display:'block' }} />}
          {isErr     && <span style={{ width:6, height:6, borderRadius:'50%', background:'var(--rose)', display:'block' }} />}
          <span className="font-mono" style={{ fontSize:'0.68rem', color: isDone ? '#6ee7b7' : isErr ? '#fda4af' : '#a5b4fc' }}>
            {isDone ? `Done · ${revLog.length} revision${revLog.length !== 1 ? 's' : ''}` : isErr ? 'Error' : `${stage}...`}
          </span>
        </div>
      )}

      <div style={{ flex:1 }} />

      {/* Model badge */}
      {modelUsed && (
        <div style={{ display:'flex', alignItems:'center', gap:6, padding:'4px 11px', borderRadius:999, border:'1px solid var(--b1)', background:'var(--bg-panel)' }}>
          <span className="font-mono" style={{ fontSize:'0.65rem', color:'var(--t2)' }}>{provider}</span>
          <span style={{ color:'var(--b2)', fontSize:'0.7rem' }}>·</span>
          <span className="font-mono" style={{ fontSize:'0.65rem', color:'#818cf8' }}>{modelUsed}</span>
        </div>
      )}

      {/* Reset */}
      {stage !== 'idle' && (
        <button onClick={reset} className="btn btn-ghost" style={{ padding:'6px 12px', fontSize:'0.75rem' }}>
          <RotateCcw size={12} /> New Campaign
        </button>
      )}
    </header>
  )
}
