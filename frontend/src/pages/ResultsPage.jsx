import React, { useState } from 'react'
import useStore from '../store/useStore'
import { regenerateContent, exportCampaign } from '../utils/api'
import { FileText, MessageSquare, Mail, Monitor, Smartphone, RefreshCw, Download, CheckCircle, XCircle, ChevronDown, ChevronUp, Copy, Check, Sparkles, GitBranch } from 'lucide-react'

const TONES = ['professional','formal','casual','friendly','persuasive']
const TABS  = [
  { id:'blog',   label:'Blog Post',     Icon:FileText },
  { id:'social', label:'Social Thread', Icon:MessageSquare },
  { id:'email',  label:'Email Teaser',  Icon:Mail },
]

export default function ResultsPage() {
  const content          = useStore(s => s.content)
  const factSheet        = useStore(s => s.factSheet)
  const editorResult     = useStore(s => s.editorResult)
  const revisionLog      = useStore(s => s.revisionLog)
  const activeTab        = useStore(s => s.activeTab)
  const setActiveTab     = useStore(s => s.setActiveTab)
  const previewMode      = useStore(s => s.previewMode)
  const setPreviewMode   = useStore(s => s.setPreviewMode)
  const updateContent    = useStore(s => s.updateContent)
  const toneBlog         = useStore(s => s.toneBlog)
  const toneSocial       = useStore(s => s.toneSocial)
  const toneEmail        = useStore(s => s.toneEmail)
  const creativity       = useStore(s => s.creativity)
  const apiProvider      = useStore(s => s.apiProvider)
  const modelName        = useStore(s => s.modelName)
  const conditions       = useStore(s => s.conditions)
  const selectedContent  = useStore(s => s.selectedContent)

  const [regenLoading,  setRegenLoading]  = useState(null)
  const [regenTone,     setRegenTone]     = useState({})
  const [exportLoading, setExportLoading] = useState(false)
  const [factOpen,      setFactOpen]      = useState(false)
  const [revOpen,       setRevOpen]       = useState(false)

  const available = TABS.filter(t => selectedContent.includes(t.id) && content?.[t.id])

  const getTone = (type) => regenTone[type] || (type==='blog' ? toneBlog : type==='social' ? toneSocial : toneEmail)

  const handleRegen = async (type) => {
    setRegenLoading(type)
    try {
      const res = await regenerateContent({ fact_sheet:factSheet, content_type:type, tone:getTone(type), creativity, api_provider:apiProvider, api_key:'', model_name:modelName||'', conditions })
      updateContent(type, res.content)
    } catch(e) { alert(`Regeneration failed: ${e.message}`) }
    finally { setRegenLoading(null) }
  }

  const handleExport = async () => {
    setExportLoading(true)
    try { await exportCampaign(factSheet, content) }
    catch(e) { alert(`Export failed: ${e.message}`) }
    finally { setExportLoading(false) }
  }

  const pieceResult  = editorResult?.[activeTab]
  const approved     = editorResult?.overall_status === 'approved'

  return (
    <div style={{ minHeight:'calc(100vh - 52px)', padding:'1.25rem', maxWidth:1300, margin:'0 auto' }} className="anim-fade-in">

      {/* Top bar */}
      <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:12, marginBottom:'1rem', flexWrap:'wrap' }}>
        <div>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
            <Sparkles size={16} color="var(--brand)" />
            <h2 className="font-display" style={{ fontSize:'1.35rem', fontWeight:700, color:'var(--t0)' }}>
              Campaign <span className="grad">Ready</span>
            </h2>
            {revisionLog.length > 0 && (
              <span style={{ fontSize:'0.68rem', color:'#a5b4fc', background:'rgba(91,110,245,0.1)', border:'1px solid rgba(91,110,245,0.25)', padding:'2px 8px', borderRadius:999, display:'flex', alignItems:'center', gap:4 }}>
                <GitBranch size={10} /> {revisionLog.length} revision{revisionLog.length!==1?'s':''}
              </span>
            )}
          </div>
          <p style={{ fontSize:'0.78rem', color:'var(--t2)' }}>
            {factSheet?.product_name && <span style={{ color:'var(--t0)' }}>{factSheet.product_name} · </span>}
            {available.length} pieces · Editor {approved ? 'approved ✓' : 'reviewed'}
          </p>
        </div>
        <button onClick={handleExport} disabled={exportLoading} className="btn btn-primary" style={{ padding:'10px 22px', fontSize:'0.85rem' }}>
          {exportLoading ? <><div style={{width:14,height:14,border:'2px solid rgba(255,255,255,0.3)',borderTopColor:'white',borderRadius:'50%'}} className="spin"/> Exporting...</> : <><Download size={14}/> Export ZIP</>}
        </button>
      </div>

      {/* Overall editor banner */}
      <div style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 16px', borderRadius:12, marginBottom:'1rem', background: approved ? 'rgba(16,185,129,0.06)' : 'rgba(245,158,11,0.06)', border:`1px solid ${approved ? 'rgba(16,185,129,0.2)' : 'rgba(245,158,11,0.2)'}`, color: approved ? '#6ee7b7' : '#fcd34d' }}>
        {approved ? <CheckCircle size={14} /> : <XCircle size={14} />}
        <span style={{ fontSize:'0.78rem', fontWeight:600 }}>{approved ? 'Editor approved all content' : 'Editor applied revisions'}</span>
        {editorResult?.scores && (
          <span className="font-mono" style={{ fontSize:'0.67rem', opacity:0.7, marginLeft:8 }}>
            accuracy {editorResult.scores.accuracy}/10 · tone {editorResult.scores.tone}/10 · completeness {editorResult.scores.completeness}/10
          </span>
        )}
        {revisionLog.length > 0 && (
          <button onClick={()=>setRevOpen(!revOpen)} style={{ marginLeft:'auto', fontSize:'0.68rem', color:'inherit', background:'none', border:'none', cursor:'pointer', display:'flex', alignItems:'center', gap:4, opacity:0.8 }}>
            {revOpen ? <ChevronUp size={12}/> : <ChevronDown size={12}/>} revision log
          </button>
        )}
      </div>

      {/* Revision log */}
      {revOpen && revisionLog.length > 0 && (
        <div className="card anim-fade-in" style={{ padding:'1rem', marginBottom:'1rem' }}>
          {revisionLog.map(r => (
            <div key={r.loop} style={{ display:'flex', gap:10, marginBottom:8, fontSize:'0.75rem' }}>
              <span className="font-mono" style={{ color:'var(--brand)', flexShrink:0 }}>Loop {r.loop}</span>
              <span style={{ color:'var(--t2)' }}>Revised: <span style={{ color:'var(--t0)' }}>{r.rejected.join(', ')}</span></span>
              {Object.entries(r.feedback || {}).map(([k,v]) => (
                <span key={k} style={{ color:'var(--t2)', marginLeft:12 }}>· {k}: <em style={{color:'var(--t1)'}}>{v.slice(0,80)}{v.length>80?'...':''}</em></span>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Main grid */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 280px', gap:14 }}>

        {/* Left: content */}
        <div style={{ minWidth:0 }}>
          {/* Tab bar */}
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:12, flexWrap:'wrap' }}>
            <div style={{ display:'flex', gap:3, padding:4, background:'var(--bg-card)', border:'1px solid var(--b0)', borderRadius:14 }}>
              {available.map(({ id, label, Icon }) => (
                <button key={id} onClick={() => setActiveTab(id)}
                  className={`btn ${activeTab===id ? 'tab-active' : 'tab-idle'}`}
                  style={{ padding:'6px 14px', borderRadius:10, fontSize:'0.78rem', gap:6, border:'1px solid' }}>
                  <Icon size={12} /> {label}
                </button>
              ))}
            </div>

            {/* Piece editor status */}
            {pieceResult && (
              <div style={{ display:'flex', alignItems:'center', gap:6, padding:'4px 10px', borderRadius:8, background: pieceResult.status==='approved' ? 'rgba(16,185,129,0.08)' : 'rgba(244,63,94,0.08)', border:`1px solid ${pieceResult.status==='approved' ? 'rgba(16,185,129,0.25)' : 'rgba(244,63,94,0.25)'}`, fontSize:'0.7rem', color: pieceResult.status==='approved' ? '#6ee7b7' : '#fda4af' }}>
                {pieceResult.status==='approved' ? <CheckCircle size={11}/> : <XCircle size={11}/>}
                {pieceResult.status==='approved' ? 'Approved' : 'Revised'}
                {pieceResult.word_count_estimate && <span style={{opacity:0.7}}> · ~{pieceResult.word_count_estimate}w</span>}
              </div>
            )}

            <div style={{ marginLeft:'auto', display:'flex', gap:4 }}>
              {[{id:'desktop',Icon:Monitor},{id:'mobile',Icon:Smartphone}].map(({id,Icon}) => (
                <button key={id} onClick={()=>setPreviewMode(id)} className="btn-icon" style={{ border:`1px solid ${previewMode===id ? 'var(--b2)' : 'var(--b0)'}`, background:previewMode===id ? 'var(--bg-hover)' : 'var(--bg-card)', color:previewMode===id ? 'var(--t0)' : 'var(--t2)' }}>
                  <Icon size={13} />
                </button>
              ))}
            </div>
          </div>

          {/* Content card */}
          <ContentPanel
            activeTab={activeTab} content={content}
            previewMode={previewMode}
            tone={getTone(activeTab)}
            onToneChange={t => setRegenTone(prev => ({...prev, [activeTab]: t}))}
            onRegen={handleRegen} regenLoading={regenLoading}
          />
        </div>

        {/* Right: fact sheet */}
        <FactSheetPanel factSheet={factSheet} open={factOpen} setOpen={setFactOpen} />
      </div>
    </div>
  )
}

function ContentPanel({ activeTab, content, previewMode, tone, onToneChange, onRegen, regenLoading }) {
  const [copied, setCopied] = useState(false)
  if (!content) return null

  const raw = content[activeTab]
  const text = Array.isArray(raw) ? raw.join('\n\n') : raw || ''
  const wordCount = text.split(/\s+/).filter(Boolean).length

  const copy = () => { navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(()=>setCopied(false),2000) }) }
  const narrow = previewMode === 'mobile'

  return (
    <div className="card" style={{ overflow:'hidden', maxWidth: narrow ? 400 : '100%' }}>
      {/* Toolbar */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'10px 16px', borderBottom:'1px solid var(--b0)', background:'rgba(255,255,255,0.01)', flexWrap:'wrap', gap:8 }}>
        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
          <span className="font-mono" style={{ fontSize:'0.67rem', color:'var(--t2)' }}>
            {activeTab==='blog' ? `~${wordCount} words` : activeTab==='social' ? `${Array.isArray(content.social)?content.social.length:0} posts` : '1 paragraph'}
          </span>
          {activeTab==='blog' && wordCount < 400 && (
            <span style={{ fontSize:'0.65rem', color:'var(--rose)', background:'rgba(244,63,94,0.08)', padding:'1px 7px', borderRadius:999, border:'1px solid rgba(244,63,94,0.2)' }}>
              ⚠ short
            </span>
          )}
        </div>

        {/* Tone selector for regeneration */}
        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
          <span style={{ fontSize:'0.67rem', color:'var(--t2)' }}>Regen tone:</span>
          <select value={tone} onChange={e => onToneChange(e.target.value)}
            style={{ background:'var(--bg-panel)', border:'1px solid var(--b1)', color:'var(--t0)', borderRadius:8, padding:'3px 24px 3px 8px', fontSize:'0.72rem', fontFamily:'DM Sans,sans-serif', outline:'none', cursor:'pointer', appearance:'none', backgroundImage:`url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%23475569' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`, backgroundRepeat:'no-repeat', backgroundPosition:'right 6px center' }}>
            {TONES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        <div style={{ display:'flex', gap:6 }}>
          <button onClick={copy} className="btn btn-ghost" style={{ padding:'4px 10px', fontSize:'0.7rem' }}>
            {copied ? <><Check size={11}/> Copied</> : <><Copy size={11}/> Copy</>}
          </button>
          <button onClick={() => onRegen(activeTab)} disabled={!!regenLoading} className="btn btn-ghost" style={{ padding:'4px 10px', fontSize:'0.7rem' }}>
            <RefreshCw size={11} style={{ animation:regenLoading===activeTab ? 'spin 0.8s linear infinite' : 'none' }} />
            {regenLoading===activeTab ? 'Writing...' : 'Regenerate'}
          </button>
        </div>
      </div>

      {/* Body */}
      <div style={{ padding:'1.25rem', maxHeight:560, overflowY:'auto' }}>
        {activeTab==='blog'   && <BlogView   text={content.blog}    narrow={narrow} />}
        {activeTab==='social' && <SocialView posts={content.social} narrow={narrow} />}
        {activeTab==='email'  && <EmailView  text={content.email} />}
      </div>
    </div>
  )
}

function BlogView({ text, narrow }) {
  if (!text) return <p style={{color:'var(--t2)',fontSize:'0.82rem'}}>No content.</p>
  const wc = text.split(/\s+/).filter(Boolean).length
  return (
    <div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:8 }}>
        <span className="font-mono" style={{ fontSize:'0.65rem', color:wc>=450&&wc<=550?'var(--emerald)':wc<400?'var(--rose)':'var(--amber)', background:wc>=450&&wc<=550?'rgba(16,185,129,0.08)':wc<400?'rgba(244,63,94,0.08)':'rgba(245,158,11,0.08)', padding:'2px 8px', borderRadius:999, border:`1px solid ${wc>=450&&wc<=550?'rgba(16,185,129,0.2)':wc<400?'rgba(244,63,94,0.2)':'rgba(245,158,11,0.2)'}` }}>
          {wc} words {wc>=450&&wc<=550?'✓':wc<400?'(too short)':'(too long)'}
        </span>
      </div>
      {text.split('\n\n').map((p, i) => (
        <p key={i} style={{ fontSize:narrow?'0.82rem':'0.88rem', color:'#cbd5e1', lineHeight:1.8, marginBottom:'1rem' }}>{p}</p>
      ))}
    </div>
  )
}

function SocialView({ posts, narrow }) {
  const list = Array.isArray(posts) ? posts : []
  if (!list.length) return <p style={{color:'var(--t2)',fontSize:'0.82rem'}}>No posts.</p>
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
      {list.map((post, i) => (
        <div key={i} style={{ background:'var(--bg-panel)', borderRadius:14, border:'1px solid var(--b1)', padding:'14px', maxWidth:narrow?340:'100%' }}>
          <div style={{ display:'flex', gap:10 }}>
            <div style={{ width:32, height:32, borderRadius:'50%', flexShrink:0, background:`linear-gradient(135deg, hsl(${i*60},70%,50%), hsl(${i*60+40},70%,40%))`, display:'flex', alignItems:'center', justifyContent:'center', fontSize:'0.72rem', fontWeight:700, color:'white', fontFamily:'JetBrains Mono,monospace' }}>
              {i+1}
            </div>
            <div style={{ flex:1 }}>
              <p style={{ fontSize:narrow?'0.8rem':'0.85rem', color:'#e2e8f0', lineHeight:1.65 }}>{post}</p>
              <div style={{ display:'flex', justifyContent:'flex-end', marginTop:8 }}>
                <span className="font-mono" style={{ fontSize:'0.65rem', color:post.length>270?'var(--rose)':post.length>240?'var(--amber)':'var(--t3)' }}>
                  {post.length}/280
                </span>
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function EmailView({ text }) {
  if (!text) return <p style={{color:'var(--t2)',fontSize:'0.82rem'}}>No content.</p>
  const sentences = text.split(/(?<=[.!?])\s+/).filter(Boolean).length
  return (
    <div style={{ background:'var(--bg-panel)', borderRadius:14, border:'1px solid var(--b1)', padding:'1.25rem' }}>
      <div style={{ borderBottom:'1px solid var(--b0)', paddingBottom:10, marginBottom:14 }}>
        <p className="font-mono" style={{ fontSize:'0.67rem', color:'var(--t2)', marginBottom:4 }}>Subject: You need to see this →</p>
        <p className="font-mono" style={{ fontSize:'0.67rem', color:'var(--t2)' }}>To: subscribers@yourlist.com</p>
      </div>
      <p style={{ fontSize:'0.88rem', color:'#e2e8f0', lineHeight:1.8 }}>{text}</p>
      <div style={{ marginTop:10, textAlign:'right' }}>
        <span className="font-mono" style={{ fontSize:'0.65rem', color:sentences>=3&&sentences<=5?'var(--emerald)':'var(--amber)' }}>
          {sentences} sentence{sentences!==1?'s':''} {sentences>=3&&sentences<=5?'✓':'(aim for 3-5)'}
        </span>
      </div>
    </div>
  )
}

function FactSheetPanel({ factSheet, open, setOpen }) {
  if (!factSheet) return null
  return (
    <div className="card" style={{ overflow:'hidden', position:'sticky', top:68, alignSelf:'start' }}>
      <button onClick={()=>setOpen(!open)}
        style={{ width:'100%', display:'flex', alignItems:'center', justifyContent:'space-between', padding:'14px 16px', background:'none', border:'none', cursor:'pointer', color:'var(--t0)', fontFamily:'Syne,sans-serif', fontWeight:600, fontSize:'0.82rem' }}
        onMouseEnter={e=>e.currentTarget.style.background='rgba(255,255,255,0.02)'}
        onMouseLeave={e=>e.currentTarget.style.background='none'}>
        🧠 Fact Sheet
        {open ? <ChevronUp size={13} color="var(--t2)"/> : <ChevronDown size={13} color="var(--t2)"/>}
      </button>

      {open && (
        <div style={{ padding:'0 16px 16px', borderTop:'1px solid var(--b0)' }} className="anim-fade-in">
          <div style={{ display:'flex', flexDirection:'column', gap:14, paddingTop:14 }}>
            <FR label="Product"    v={factSheet.product_name} />
            <FR label="Audience"   v={factSheet.target_audience} />
            <FR label="Value Prop" v={factSheet.value_proposition} />
            {factSheet.pricing && <FR label="Pricing" v={factSheet.pricing} />}
            {factSheet.features?.length > 0 && (
              <div>
                <p style={{ fontSize:'0.62rem', textTransform:'uppercase', letterSpacing:'0.09em', color:'var(--t3)', marginBottom:6 }}>Features</p>
                {factSheet.features.map((f,i) => <div key={i} style={{display:'flex',gap:6,fontSize:'0.75rem',color:'var(--t1)',marginBottom:4}}><span style={{color:'var(--brand)',flexShrink:0}}>·</span>{f}</div>)}
              </div>
            )}
            {factSheet.flagged_ambiguities?.length > 0 && (
              <div style={{padding:'10px',borderRadius:10,background:'rgba(245,158,11,0.06)',border:'1px solid rgba(245,158,11,0.18)'}}>
                <p style={{fontSize:'0.62rem',textTransform:'uppercase',letterSpacing:'0.09em',color:'var(--amber)',marginBottom:6}}>⚠ Flagged</p>
                {factSheet.flagged_ambiguities.map((f,i) => <div key={i} style={{fontSize:'0.73rem',color:'#fbbf24',marginBottom:3}}>· {f}</div>)}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function FR({ label, v }) {
  if (!v) return null
  return (
    <div>
      <p style={{fontSize:'0.62rem',textTransform:'uppercase',letterSpacing:'0.09em',color:'var(--t3)',marginBottom:3}}>{label}</p>
      <p style={{fontSize:'0.8rem',color:'var(--t1)',lineHeight:1.55}}>{v}</p>
    </div>
  )
}
