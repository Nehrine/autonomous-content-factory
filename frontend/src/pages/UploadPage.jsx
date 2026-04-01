import React, { useState, useRef, useCallback, useEffect } from 'react'
import useStore from '../store/useStore'
import { uploadFile, runPipeline, fetchConfig } from '../utils/api'
import { Upload, FileText, Play, Sparkles, ChevronDown, CheckCircle, AlertCircle, PenLine, FileUp, Type, RefreshCw } from 'lucide-react'

const PROVIDERS = [
  { id:'gemini', label:'Gemini',  emoji:'🔵', models:['gemini-2.5-flash','gemini-2.0-flash','gemini-1.5-pro'], envVar:'GEMINI_API_KEY' },
  { id:'claude', label:'Claude',  emoji:'🟣', models:['claude-sonnet-4-5','claude-opus-4-5','claude-haiku-4-5-20251001'], envVar:'ANTHROPIC_API_KEY' },
  { id:'openai', label:'OpenAI',  emoji:'🟢', models:['gpt-4o-mini','gpt-4o','gpt-3.5-turbo'], envVar:'OPENAI_API_KEY' },
]
const TONES = ['professional','formal','casual','friendly','persuasive']
const CONTENT = [
  { id:'blog',   label:'Blog',    sub:'500 words' },
  { id:'social', label:'Social',  sub:'5-post thread' },
  { id:'email',  label:'Email',   sub:'1 paragraph' },
]
const PRESETS = [
  'No pricing mentions',
  'Focus on B2B audience',
  'Include strong CTA',
  'UK English spelling',
  'Technical audience',
  'Keep it concise',
]
const sleep = ms => new Promise(r => setTimeout(r, ms))

export default function UploadPage() {
  const [inputMode, setInputMode] = useState('file')
  const [dragging,  setDragging]  = useState(false)
  const [file,      setFile]      = useState(null)
  const [rawText,   setRawText]   = useState('')
  const [loading,   setLoading]   = useState(false)
  const [err,       setErr]       = useState('')
  const [cfg,       setCfg]       = useState({})
  const [conditions, setConditions] = useState('')
  const fileRef = useRef()

  const apiProvider    = useStore(s => s.apiProvider)
  const setApiProvider = useStore(s => s.setApiProvider)
  const modelName      = useStore(s => s.modelName)
  const setModelName   = useStore(s => s.setModelName)
  const toneBlog       = useStore(s => s.toneBlog);   const setToneBlog   = useStore(s => s.setToneBlog)
  const toneSocial     = useStore(s => s.toneSocial); const setToneSocial = useStore(s => s.setToneSocial)
  const toneEmail      = useStore(s => s.toneEmail);  const setToneEmail  = useStore(s => s.setToneEmail)
  const creativity     = useStore(s => s.creativity); const setCreativity = useStore(s => s.setCreativity)
  const selectedContent = useStore(s => s.selectedContent)
  const toggleContent  = useStore(s => s.toggleContent)
  const maxLoops       = useStore(s => s.maxLoops);   const setMaxLoops   = useStore(s => s.setMaxLoops)

  const setPipelineStage = useStore(s => s.setPipelineStage)
  const setAgentStatus   = useStore(s => s.setAgentStatus)
  const setResults       = useStore(s => s.setResults)
  const addLog           = useStore(s => s.addLog)
  const clearLog         = useStore(s => s.clearLog)
  const setDocument      = useStore(s => s.setDocument)
  const setErrorStore    = useStore(s => s.setError)
  const setConditionsStore = useStore(s => s.setConditions)

  const prov = PROVIDERS.find(p => p.id === apiProvider) || PROVIDERS[0]
  const effModel = modelName || prov.models[0]
  const envOk = apiProvider === 'gemini' ? cfg.gemini_configured : apiProvider === 'claude' ? cfg.claude_configured : cfg.openai_configured
  const hasInput = inputMode === 'file' ? !!file : rawText.trim().length > 20
  const canStart = hasInput && envOk && !loading && selectedContent.length > 0

  useEffect(() => { fetchConfig().then(c => { setCfg(c); if (c.default_provider) setApiProvider(c.default_provider) }) }, [])

  const pickFile = f => {
    setErr('')
    const ext = '.' + f.name.split('.').pop().toLowerCase()
    if (!['.pdf','.txt','.docx','.doc'].includes(ext)) { setErr(`Unsupported: "${ext}"`); return }
    if (f.size > 10*1024*1024) { setErr('Max 10MB'); return }
    setFile(f)
  }
  const onDrop = useCallback(e => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files[0]) pickFile(e.dataTransfer.files[0]) }, [])

  const handleStart = async () => {
    if (!canStart) return
    setErr(''); setLoading(true); clearLog()
    setConditionsStore(conditions)
    setPipelineStage('uploading')

    try {
      let docText, docName
      if (inputMode === 'file') {
        addLog('System', `Uploading "${file.name}"...`, 'info')
        const up = await uploadFile(file)
        docText = up.text; docName = file.name
        addLog('System', `Parsed ${up.char_count.toLocaleString()} characters`, 'success')
      } else {
        docText = rawText.trim(); docName = 'manual-input.txt'
        addLog('System', `Using typed text (${docText.length} chars)`, 'success')
      }
      setDocument(docText, docName)

      // Research
      setPipelineStage('researching')
      setAgentStatus('research','thinking')
      addLog('Research Agent', 'Scanning document for facts...', 'agent')
      await sleep(400)
      setAgentStatus('research','processing')
      addLog('Research Agent', 'Extracting product details...', 'agent')

      const result = await runPipeline({
        document_text: docText,
        tone_blog: toneBlog, tone_social: toneSocial, tone_email: toneEmail,
        creativity, selected_content: selectedContent,
        api_provider: apiProvider, api_key: '', model_name: effModel,
        conditions, max_revision_loops: maxLoops,
      })

      setAgentStatus('research','completed')
      addLog('Research Agent', `✓ Product: "${result.fact_sheet?.product_name || 'N/A'}"`, 'success')

      // Copywriter
      setPipelineStage('writing')
      setAgentStatus('copywriter','thinking')
      addLog('Copywriter', 'Writing content with per-type tone settings...', 'agent')
      await sleep(300)
      setAgentStatus('copywriter','processing')
      addLog('Copywriter', `Blog: ${toneBlog} · Social: ${toneSocial} · Email: ${toneEmail}`, 'info')
      await sleep(200)
      setAgentStatus('copywriter','completed')
      addLog('Copywriter', '✓ Initial drafts complete', 'success')

      // Editor loop
      setPipelineStage('editing')
      setAgentStatus('editor','thinking')
      const revLog = result.revision_log || []
      if (revLog.length > 0) {
        revLog.forEach(r => {
          addLog('Editor', `⚡ Loop ${r.loop}: Revising ${r.rejected.join(', ')}`, 'warning')
          addLog('Copywriter', `↺ Rewriting ${r.rejected.join(', ')} based on feedback`, 'agent')
        })
      }
      setAgentStatus('editor','processing')
      await sleep(200)

      const overall = result.editor_result?.overall_status
      if (overall === 'approved') {
        setAgentStatus('editor','completed')
        addLog('Editor', `✓ All content approved after ${revLog.length} revision(s)`, 'success')
      } else {
        setAgentStatus('editor','completed')
        addLog('Editor', `✓ Published best version after ${maxLoops} revision loops`, 'success')
      }

      setResults(result.fact_sheet, result.content, result.editor_result, revLog, result.model_used)
      setPipelineStage('done')
    } catch(e) {
      const msg = e.message || 'Unknown error'
      setErrorStore(msg); addLog('System', `✗ ${msg}`, 'error')
      setPipelineStage('error')
    } finally { setLoading(false) }
  }

  const ToneRow = ({ label, value, onChange, color }) => (
    <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
      <div style={{ display:'flex', alignItems:'center', gap:6 }}>
        <span style={{ width:8, height:8, borderRadius:'50%', background:color, flexShrink:0 }} />
        <span style={{ fontSize:'0.68rem', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.08em', color:'var(--t2)' }}>{label}</span>
      </div>
      <div style={{ display:'flex', gap:4, flexWrap:'wrap' }}>
        {TONES.map(t => (
          <button key={t} onClick={() => onChange(t)}
            className={`btn ${value === t ? 'tone-active' : 'tone-idle'}`}
            style={{ padding:'4px 10px', borderRadius:8, fontSize:'0.72rem', textTransform:'capitalize', fontWeight:500, border:'1px solid' }}>
            {t}
          </button>
        ))}
      </div>
    </div>
  )

  return (
    <div style={{ minHeight:'calc(100vh - 52px)', display:'flex', alignItems:'flex-start', justifyContent:'center', padding:'2rem 1rem 3rem', position:'relative', overflow:'hidden' }}>
      {/* Background */}
      <div className="dot-bg" style={{ position:'absolute', inset:0, opacity:0.4 }} />
      <div className="orb1" style={{ position:'absolute', width:700, height:700, borderRadius:'50%', background:'radial-gradient(circle, rgba(91,110,245,0.08) 0%, transparent 65%)', top:'-20%', left:'-20%', pointerEvents:'none' }} />
      <div className="orb2" style={{ position:'absolute', width:500, height:500, borderRadius:'50%', background:'radial-gradient(circle, rgba(124,58,237,0.06) 0%, transparent 65%)', bottom:'-10%', right:'-10%', pointerEvents:'none' }} />

      <div className="anim-fade-up" style={{ width:'100%', maxWidth:700, position:'relative', zIndex:1, display:'flex', flexDirection:'column', gap:12 }}>

        {/* Hero */}
        <div style={{ textAlign:'center', padding:'1.5rem 0 1rem' }}>
          <div style={{ display:'inline-flex', alignItems:'center', gap:6, padding:'5px 14px', borderRadius:999, border:'1px solid rgba(91,110,245,0.2)', background:'rgba(91,110,245,0.07)', fontSize:'0.7rem', color:'#a5b4fc', marginBottom:16 }}>
            <Sparkles size={10} /> Multi-Agent AI · Research → Write → Edit → Approve
          </div>
          <h1 className="font-display" style={{ fontSize:'2.8rem', fontWeight:800, lineHeight:1.08, color:'var(--t0)', marginBottom:12 }}>
            Autonomous<br /><span className="grad">Content Factory</span>
          </h1>
          <p style={{ fontSize:'0.88rem', color:'var(--t1)', maxWidth:380, margin:'0 auto', lineHeight:1.7 }}>
            Upload a doc or type text. Three agents research, write, and edit until every piece is publish-ready.
          </p>
        </div>

        {/* ── Provider ── */}
        <div className="card" style={{ padding:'1rem 1.25rem' }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:10 }}>
            <span style={{ fontSize:'0.65rem', fontWeight:700, textTransform:'uppercase', letterSpacing:'0.1em', color:'var(--t2)' }}>AI Provider</span>
            {envOk
              ? <span style={{ fontSize:'0.67rem', color:'var(--emerald)', display:'flex', alignItems:'center', gap:4 }}><CheckCircle size={10} /> Key loaded from .env</span>
              : <span style={{ fontSize:'0.67rem', color:'var(--rose)', display:'flex', alignItems:'center', gap:4 }}><AlertCircle size={10} /> No key in backend/.env</span>}
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:8, marginBottom:10 }}>
            {PROVIDERS.map(p => (
              <button key={p.id} onClick={() => { setApiProvider(p.id); setModelName('') }}
                style={{ padding:'9px', borderRadius:11, border:`1px solid ${apiProvider===p.id ? 'rgba(91,110,245,0.45)' : 'var(--b1)'}`, background:apiProvider===p.id ? 'rgba(91,110,245,0.12)' : 'var(--bg-panel)', color:apiProvider===p.id ? '#c7d2fe' : 'var(--t2)', cursor:'pointer', fontSize:'0.78rem', fontFamily:'DM Sans, sans-serif', transition:'all 0.15s', display:'flex', alignItems:'center', justifyContent:'center', gap:6 }}>
                {p.emoji} {p.label}
              </button>
            ))}
          </div>
          <div style={{ position:'relative' }}>
            <select value={effModel} onChange={e => setModelName(e.target.value)} className="select">
              {prov.models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        </div>

        {/* ── Document Input ── */}
        <div className="card" style={{ padding:'1rem 1.25rem' }}>
          <div style={{ display:'flex', gap:4, marginBottom:12, padding:3, background:'var(--bg-panel)', borderRadius:11, width:'fit-content' }}>
            {[{id:'file',label:'Upload File',Icon:FileUp},{id:'text',label:'Type / Paste',Icon:PenLine}].map(({id,label,Icon}) => (
              <button key={id} onClick={() => { setInputMode(id); setErr('') }}
                className={`btn ${inputMode===id ? 'tab-active' : 'tab-idle'}`}
                style={{ padding:'6px 14px', borderRadius:8, fontSize:'0.78rem', fontWeight:500, gap:6, border:'1px solid' }}>
                <Icon size={12} /> {label}
              </button>
            ))}
          </div>

          {inputMode === 'file' ? (
            <div onDragOver={e=>{e.preventDefault();setDragging(true)}} onDragLeave={()=>setDragging(false)} onDrop={onDrop}
              onClick={() => !file && fileRef.current?.click()}
              style={{ padding:'1.5rem', borderRadius:14, border:`1.5px dashed ${dragging ? 'var(--brand)' : file ? 'rgba(16,185,129,0.4)' : 'var(--b1)'}`, background:dragging ? 'rgba(91,110,245,0.05)' : file ? 'rgba(16,185,129,0.03)' : 'var(--bg-input)', cursor:file?'default':'pointer', transition:'all 0.2s', display:'flex', flexDirection:'column', alignItems:'center', gap:10 }}>
              <input ref={fileRef} type="file" accept=".pdf,.txt,.docx,.doc" style={{display:'none'}} onChange={e=>e.target.files[0]&&pickFile(e.target.files[0])} />
              {file ? (
                <>
                  <div style={{width:44,height:44,borderRadius:12,background:'rgba(16,185,129,0.1)',border:'1px solid rgba(16,185,129,0.25)',display:'flex',alignItems:'center',justifyContent:'center'}}><FileText size={20} color="var(--emerald)"/></div>
                  <div style={{textAlign:'center'}}><p style={{color:'var(--t0)',fontWeight:500,fontSize:'0.85rem'}}>{file.name}</p><p style={{color:'var(--t2)',fontSize:'0.72rem',marginTop:2}}>{(file.size/1024).toFixed(1)} KB</p></div>
                  <button onClick={e=>{e.stopPropagation();setFile(null)}} style={{fontSize:'0.7rem',color:'var(--t2)',background:'none',border:'none',cursor:'pointer'}} onMouseEnter={e=>e.currentTarget.style.color='var(--rose)'} onMouseLeave={e=>e.currentTarget.style.color='var(--t2)'}>Remove</button>
                </>
              ) : (
                <>
                  <div style={{width:44,height:44,borderRadius:12,background:'var(--bg-panel)',border:'1px solid var(--b1)',display:'flex',alignItems:'center',justifyContent:'center'}}><Upload size={18} color="var(--t2)"/></div>
                  <div style={{textAlign:'center'}}><p style={{color:'var(--t0)',fontSize:'0.84rem',fontWeight:500}}>{dragging?'Drop it!':'Drop or click to upload'}</p><p style={{color:'var(--t2)',fontSize:'0.71rem',marginTop:3}}>PDF · TXT · DOCX · max 10MB</p></div>
                </>
              )}
            </div>
          ) : (
            <div>
              <textarea value={rawText} onChange={e=>setRawText(e.target.value)}
                placeholder={"Paste product description, spec sheet, or any text here...\n\nThe agents will extract facts and create your campaign."}
                style={{width:'100%',minHeight:150,background:'var(--bg-input)',border:'1px solid var(--b1)',borderRadius:12,padding:'12px 14px',color:'var(--t0)',fontSize:'0.84rem',fontFamily:'DM Sans, sans-serif',lineHeight:1.7,resize:'vertical',outline:'none',transition:'border-color 0.2s'}}
                onFocus={e=>e.target.style.borderColor='var(--brand)'} onBlur={e=>e.target.style.borderColor='var(--b1)'}/>
              <div style={{textAlign:'right',marginTop:4}}>
                <span className="font-mono" style={{fontSize:'0.67rem',color:rawText.length>20?'var(--emerald)':'var(--t3)'}}>
                  {rawText.length} chars {rawText.length>20?'✓':'(min 20)'}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* ── Per-content Tone ── */}
        <div className="card" style={{ padding:'1rem 1.25rem' }}>
          <div style={{ display:'flex', alignItems:'center', gap:7, marginBottom:14 }}>
            <span style={{ fontSize:'0.65rem', fontWeight:700, textTransform:'uppercase', letterSpacing:'0.1em', color:'var(--t2)' }}>Tone per Content Type</span>
            <span style={{ fontSize:'0.65rem', color:'var(--t3)', marginLeft:4 }}>— each piece gets its own voice</span>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            {selectedContent.includes('blog')   && <ToneRow label="Blog Post"     value={toneBlog}   onChange={setToneBlog}   color="#818cf8" />}
            {selectedContent.includes('social') && <ToneRow label="Social Thread" value={toneSocial} onChange={setToneSocial} color="#22d3ee" />}
            {selectedContent.includes('email')  && <ToneRow label="Email Teaser"  value={toneEmail}  onChange={setToneEmail}  color="#a78bfa" />}
          </div>
        </div>

        {/* ── Output + Creativity ── */}
        <div className="card" style={{ padding:'1rem 1.25rem' }}>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'1.25rem' }}>
            {/* Content types */}
            <div>
              <span style={{ fontSize:'0.65rem', fontWeight:700, textTransform:'uppercase', letterSpacing:'0.1em', color:'var(--t2)', display:'block', marginBottom:10 }}>Output</span>
              <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                {CONTENT.map(({id,label,sub}) => {
                  const on = selectedContent.includes(id)
                  return (
                    <button key={id} onClick={() => toggleContent(id)} className={`btn ${on ? 'cpill-on' : 'cpill-off'}`}
                      style={{ padding:'8px 14px', borderRadius:10, fontSize:'0.8rem', justifyContent:'space-between', border:'1px solid' }}>
                      <span style={{display:'flex',alignItems:'center',gap:8}}>
                        <span style={{width:14,height:14,borderRadius:4,border:`2px solid ${on?'var(--emerald)':'var(--b3)'}`,background:on?'var(--emerald)':'transparent',display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0,transition:'all 0.15s'}}>
                          {on && <svg width="8" height="6" viewBox="0 0 8 6" fill="none"><path d="M1 3L3 5L7 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                        </span>
                        {label}
                      </span>
                      <span style={{fontSize:'0.68rem',opacity:0.7}}>{sub}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Creativity + Loops */}
            <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
              <div>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:8 }}>
                  <span style={{ fontSize:'0.65rem', fontWeight:700, textTransform:'uppercase', letterSpacing:'0.1em', color:'var(--t2)' }}>Creativity</span>
                  <span className="font-mono" style={{ fontSize:'0.68rem', color:'#818cf8' }}>{Math.round(creativity*100)}%</span>
                </div>
                <input type="range" min="0" max="1" step="0.05" value={creativity} onChange={e=>setCreativity(parseFloat(e.target.value))} style={{width:'100%',accentColor:'var(--brand)',cursor:'pointer'}}/>
                <div style={{display:'flex',justifyContent:'space-between',marginTop:5,fontSize:'0.62rem',color:'var(--t3)'}}>
                  <span>Factual</span><span>Expressive</span>
                </div>
              </div>
              <div>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:8 }}>
                  <span style={{ fontSize:'0.65rem', fontWeight:700, textTransform:'uppercase', letterSpacing:'0.1em', color:'var(--t2)' }}>Revision Loops</span>
                  <span className="font-mono" style={{ fontSize:'0.68rem', color:'#818cf8' }}>{maxLoops}x</span>
                </div>
                <input type="range" min="1" max="5" step="1" value={maxLoops} onChange={e=>setMaxLoops(parseInt(e.target.value))} style={{width:'100%',accentColor:'var(--violet)',cursor:'pointer'}}/>
                <div style={{display:'flex',justifyContent:'space-between',marginTop:5,fontSize:'0.62rem',color:'var(--t3)'}}>
                  <span>1 pass</span><span>5 loops</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Conditions ── */}
        <div className="card" style={{ padding:'1rem 1.25rem' }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:10 }}>
            <span style={{ fontSize:'0.65rem', fontWeight:700, textTransform:'uppercase', letterSpacing:'0.1em', color:'var(--t2)' }}>Special Conditions <span style={{color:'var(--t3)',fontWeight:400,textTransform:'none',letterSpacing:0}}>— optional</span></span>
            {conditions && <button onClick={()=>setConditions('')} style={{fontSize:'0.67rem',color:'var(--t2)',background:'none',border:'none',cursor:'pointer'}} onMouseEnter={e=>e.currentTarget.style.color='var(--rose)'} onMouseLeave={e=>e.currentTarget.style.color='var(--t2)'}>Clear</button>}
          </div>
          <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginBottom:10 }}>
            {PRESETS.map(p => (
              <button key={p} onClick={() => setConditions(c => c ? c+'\n'+p : p)}
                style={{ padding:'4px 10px', borderRadius:999, fontSize:'0.71rem', border:'1px solid var(--b1)', background:'var(--bg-panel)', color:'var(--t2)', cursor:'pointer', fontFamily:'DM Sans, sans-serif', transition:'all 0.15s' }}
                onMouseEnter={e=>{e.currentTarget.style.borderColor='rgba(91,110,245,0.4)';e.currentTarget.style.color='#a5b4fc';e.currentTarget.style.background='rgba(91,110,245,0.07)'}}
                onMouseLeave={e=>{e.currentTarget.style.borderColor='var(--b1)';e.currentTarget.style.color='var(--t2)';e.currentTarget.style.background='var(--bg-panel)'}}>
                + {p}
              </button>
            ))}
          </div>
          <textarea value={conditions} onChange={e=>setConditions(e.target.value)}
            placeholder={"Custom instructions for all agents...\n\n• Don't mention competitor X\n• Target audience: senior executives 40-60\n• Emphasise the 30-day free trial"}
            style={{width:'100%',minHeight:90,background:'var(--bg-input)',border:'1px solid var(--b1)',borderRadius:12,padding:'10px 14px',color:'var(--t0)',fontSize:'0.82rem',fontFamily:'DM Sans, sans-serif',lineHeight:1.65,resize:'vertical',outline:'none',transition:'border-color 0.2s'}}
            onFocus={e=>e.target.style.borderColor='var(--brand)'} onBlur={e=>e.target.style.borderColor='var(--b1)'}/>
        </div>

        {/* Error */}
        {err && <div style={{padding:'10px 14px',borderRadius:10,background:'rgba(244,63,94,0.07)',border:'1px solid rgba(244,63,94,0.25)',color:'#fda4af',fontSize:'0.82rem'}}>⚠️ {err}</div>}

        {/* CTA */}
        <button onClick={handleStart} disabled={!canStart} className="btn btn-primary" style={{ width:'100%', justifyContent:'center', padding:'14px', fontSize:'0.95rem', borderRadius:16 }}>
          {loading
            ? <><div style={{width:16,height:16,border:'2px solid rgba(255,255,255,0.3)',borderTopColor:'white',borderRadius:'50%'}} className="spin"/>Launching Pipeline...</>
            : <><Play size={16}/>Generate Campaign</>}
        </button>

        <div style={{display:'flex',justifyContent:'center',gap:24,paddingBottom:8}}>
          {['🧠 Research','✍️ Write','🛡️ Edit → Revise → Approve'].map(f => <span key={f} style={{fontSize:'0.68rem',color:'var(--t3)'}}>{f}</span>)}
        </div>

      </div>
    </div>
  )


}
