import React, { useEffect, useRef } from 'react'
import useStore from '../store/useStore'
import { Brain, PenTool, ShieldCheck, CheckCircle, AlertCircle, Loader, RefreshCw } from 'lucide-react'

const AGENTS = [
  { id:'research',   label:'Research Agent',   Icon:Brain,       desc:'Extracts facts · builds fact sheet',  col:'#818cf8', bg:'rgba(129,140,248,0.1)',  bd:'rgba(129,140,248,0.25)' },
  { id:'copywriter', label:'Copywriter',        Icon:PenTool,     desc:'Writes blog · social thread · email', col:'#22d3ee', bg:'rgba(34,211,238,0.1)',   bd:'rgba(34,211,238,0.25)' },
  { id:'editor',     label:'Editor-in-Chief',   Icon:ShieldCheck, desc:'Reviews · rejects · re-approves',     col:'#a78bfa', bg:'rgba(167,139,250,0.1)',  bd:'rgba(167,139,250,0.25)' },
]

const LOG_COL = { info:'var(--t2)', agent:'#a5b4fc', success:'#6ee7b7', warning:'#fcd34d', error:'#fda4af' }

const PCT = { uploading:8, researching:32, writing:62, editing:85, done:100 }

export default function PipelinePage() {
  const statuses      = useStore(s => s.agentStatuses)
  const chatLog       = useStore(s => s.chatLog)
  const stage         = useStore(s => s.pipelineStage)
  const fileName      = useStore(s => s.fileName)
  const documentText  = useStore(s => s.documentText)
  const logRef = useRef()

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [chatLog])

  const pct = PCT[stage] || 0
  const running = !['done','error'].includes(stage)

  return (
    <div style={{ minHeight:'calc(100vh - 52px)', padding:'1.5rem', maxWidth:1080, margin:'0 auto' }}>

      {/* Progress */}
      <div className="anim-fade-up" style={{ marginBottom:'1.75rem' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6 }}>
          <div>
            {fileName && <span style={{ color:'var(--t0)', fontWeight:500, fontSize:'0.85rem', marginRight:8 }}>{fileName}</span>}
            <span style={{ color:'var(--t2)', fontSize:'0.78rem' }}>Processing...</span>
          </div>
          <span className="font-mono" style={{ fontSize:'0.72rem', color:'#818cf8' }}>{pct}%</span>
        </div>
        <div style={{ height:3, background:'var(--b0)', borderRadius:3, overflow:'hidden' }}>
          <div className="shimmer-bar" style={{ width:`${pct}%`, transition:'width 0.9s ease' }} />
        </div>
        {/* Stage steps */}
        <div style={{ display:'flex', alignItems:'center', gap:0, marginTop:10 }}>
          {['uploading','researching','writing','editing'].map((s, i, arr) => {
            const stages = arr
            const si = stages.indexOf(stage)
            const done   = i < si
            const active = i === si
            return (
              <React.Fragment key={s}>
                <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:4 }}>
                  <div style={{ width:8, height:8, borderRadius:'50%', background: done ? 'var(--brand)' : active ? '#a5b4fc' : 'var(--b2)', boxShadow: active ? '0 0 8px var(--brand)' : 'none', transition:'all 0.4s' }} />
                  <span className="font-mono" style={{ fontSize:'0.58rem', textTransform:'capitalize', color: done ? '#818cf8' : active ? '#a5b4fc' : 'var(--t3)' }}>{s}</span>
                </div>
                {i < arr.length-1 && <div style={{ flex:1, height:1, background: done ? 'var(--brand)' : 'var(--b0)', margin:'0 6px 14px', transition:'background 0.4s' }} />}
              </React.Fragment>
            )
          })}
        </div>
      </div>

      {/* Agents */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, marginBottom:16 }}>
        {AGENTS.map(a => <AgentCard key={a.id} a={a} status={statuses[a.id]} />)}
      </div>

      {/* Two panels */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
        {/* Source doc */}
        <div className="card" style={{ padding:'1.25rem', height:380, display:'flex', flexDirection:'column' }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:12 }}>
            <span className="font-display" style={{ fontSize:'0.8rem', fontWeight:600, color:'var(--t0)' }}>📄 Source Document</span>
            {fileName && <span className="font-mono" style={{ fontSize:'0.65rem', color:'var(--t2)' }}>{fileName}</span>}
          </div>
          <div style={{ flex:1, overflowY:'auto' }}>
            <pre className="font-mono" style={{ fontSize:'0.69rem', color:'var(--t1)', lineHeight:1.75, whiteSpace:'pre-wrap', margin:0 }}>
              {documentText ? documentText.slice(0,2200) + (documentText.length > 2200 ? '\n\n[truncated...]' : '') : 'Loading...'}
            </pre>
          </div>
        </div>

        {/* Live feed */}
        <div className="card" style={{ padding:'1.25rem', height:380, display:'flex', flexDirection:'column' }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:12 }}>
            <span className="live-dot" />
            <span className="font-display" style={{ fontSize:'0.8rem', fontWeight:600, color:'var(--t0)' }}>Agent Feed</span>
          </div>
          <div ref={logRef} style={{ flex:1, overflowY:'auto', display:'flex', flexDirection:'column', gap:5 }}>
            {chatLog.length === 0 && <p style={{ color:'var(--t3)', fontSize:'0.74rem', textAlign:'center', marginTop:40 }}>Waiting...</p>}
            {chatLog.map(log => (
              <div key={log.id} className="anim-slide-up" style={{ display:'flex', gap:8, fontSize:'0.71rem' }}>
                <span className="font-mono" style={{ color:'var(--t3)', flexShrink:0 }}>
                  {log.ts.toLocaleTimeString('en',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}
                </span>
                <div>
                  <span style={{ color:'var(--t2)', fontWeight:500 }}>[{log.agent}] </span>
                  <span style={{ color: LOG_COL[log.type] || 'var(--t2)' }}>{log.message}</span>
                </div>
              </div>
            ))}
            {running && (
              <div style={{ display:'flex', gap:8, fontSize:'0.71rem', alignItems:'center', paddingTop:2 }}>
                <span className="font-mono" style={{ color:'var(--t3)' }}>...</span>
                <span style={{ color:'#818cf8', display:'flex', gap:3 }}>
                  <span className="tdot" /><span className="tdot" /><span className="tdot" />
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function AgentCard({ a, status }) {
  const { Icon, label, desc, col, bg, bd } = a
  const thinking   = status === 'thinking'
  const processing = status === 'processing'
  const completed  = status === 'completed'
  const error      = status === 'error'
  const active     = thinking || processing

  const ringClass = thinking ? 'ring-thinking' : processing ? 'ring-processing' : completed ? 'ring-done' : ''
  const STATUS = { idle:'Waiting', thinking:'Thinking...', processing:'Processing...', completed:'Done ✓', error:'Error' }
  const badgeStyle = {
    idle:      { bg:'var(--bg-panel)',              color:'var(--t3)' },
    thinking:  { bg:'rgba(91,110,245,0.15)',  color:'#a5b4fc' },
    processing:{ bg:'rgba(245,158,11,0.15)',  color:'#fcd34d' },
    completed: { bg:'rgba(16,185,129,0.15)',  color:'#6ee7b7' },
    error:     { bg:'rgba(244,63,94,0.15)',   color:'#fda4af' },
  }[status] || { bg:'var(--bg-panel)', color:'var(--t3)' }

  return (
    <div style={{ background:'var(--bg-card)', border:`1px solid ${active ? bd : completed ? 'rgba(16,185,129,0.25)' : 'var(--b0)'}`, borderRadius:18, padding:'1.1rem', display:'flex', flexDirection:'column', alignItems:'center', gap:10, transition:'all 0.4s', boxShadow: active ? `0 0 28px ${bg}` : 'none' }}>
      <div className={ringClass} style={{ width:56, height:56, borderRadius:16, background: completed ? 'rgba(16,185,129,0.1)' : error ? 'rgba(244,63,94,0.1)' : bg, border:`1px solid ${completed ? 'rgba(16,185,129,0.3)' : error ? 'rgba(244,63,94,0.3)' : bd}`, display:'flex', alignItems:'center', justifyContent:'center', transition:'all 0.4s' }}>
        {active     ? <Loader      size={24} color={col} className="spin" />         : null}
        {completed  ? <CheckCircle size={24} color="var(--emerald)" />               : null}
        {error      ? <AlertCircle size={24} color="var(--rose)" />                  : null}
        {status === 'idle' ? <Icon size={24} color={col} style={{ opacity:0.35 }} /> : null}
      </div>
      <div style={{ textAlign:'center' }}>
        <p className="font-display" style={{ fontSize:'0.82rem', fontWeight:600, color:'var(--t0)' }}>{label}</p>
        <p style={{ fontSize:'0.68rem', color:'var(--t2)', marginTop:3 }}>{desc}</p>
      </div>
      <div style={{ padding:'3px 12px', borderRadius:999, fontSize:'0.67rem', fontWeight:500, background:badgeStyle.bg, color:badgeStyle.color, transition:'all 0.3s' }}>
        {STATUS[status] || 'Waiting'}
      </div>
    </div>
  )
}
