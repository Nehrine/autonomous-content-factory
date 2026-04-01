import { create } from 'zustand'

const useStore = create((set) => ({
  // ── API ──────────────────────────────────────────────────
  apiProvider: 'gemini',
  modelName: '',
  setApiProvider: (v) => set({ apiProvider: v }),
  setModelName: (v) => set({ modelName: v }),

  // ── Document ─────────────────────────────────────────────
  documentText: '',
  fileName: '',
  setDocument: (text, name) => set({ documentText: text, fileName: name }),

  // ── Per-content tones ────────────────────────────────────
  toneBlog:   'professional',
  toneSocial: 'casual',
  toneEmail:  'persuasive',
  setToneBlog:   (v) => set({ toneBlog: v }),
  setToneSocial: (v) => set({ toneSocial: v }),
  setToneEmail:  (v) => set({ toneEmail: v }),

  // ── Other controls ───────────────────────────────────────
  creativity: 0.5,
  selectedContent: ['blog', 'social', 'email'],
  conditions: '',
  maxLoops: 3,
  setCreativity: (v) => set({ creativity: v }),
  setConditions: (v) => set({ conditions: v }),
  setMaxLoops: (v) => set({ maxLoops: v }),
  toggleContent: (type) =>
    set((s) => ({
      selectedContent: s.selectedContent.includes(type)
        ? s.selectedContent.filter((t) => t !== type)
        : [...s.selectedContent, type],
    })),

  // ── Pipeline state ───────────────────────────────────────
  pipelineStage: 'idle',
  agentStatuses: { research: 'idle', copywriter: 'idle', editor: 'idle' },
  setPipelineStage: (v) => set({ pipelineStage: v }),
  setAgentStatus: (agent, status) =>
    set((s) => ({ agentStatuses: { ...s.agentStatuses, [agent]: status } })),

  // ── Results ──────────────────────────────────────────────
  factSheet: null,
  content: null,
  editorResult: null,
  revisionLog: [],
  modelUsed: '',
  setResults: (factSheet, content, editorResult, revisionLog, modelUsed) =>
    set({ factSheet, content, editorResult, revisionLog, modelUsed }),
  updateContent: (type, value) =>
    set((s) => ({ content: { ...s.content, [type]: value } })),

  // ── Chat log ─────────────────────────────────────────────
  chatLog: [],
  addLog: (agent, message, type = 'info') =>
    set((s) => ({
      chatLog: [...s.chatLog, { id: Date.now() + Math.random(), agent, message, type, ts: new Date() }],
    })),
  clearLog: () => set({ chatLog: [] }),

  // ── UI ───────────────────────────────────────────────────
  activeTab: 'blog',
  previewMode: 'desktop',
  setActiveTab: (v) => set({ activeTab: v }),
  setPreviewMode: (v) => set({ previewMode: v }),

  // ── Error ────────────────────────────────────────────────
  error: null,
  setError: (v) => set({ error: v }),

  // ── Reset ────────────────────────────────────────────────
  resetPipeline: () => set({
    pipelineStage: 'idle',
    agentStatuses: { research: 'idle', copywriter: 'idle', editor: 'idle' },
    factSheet: null, content: null, editorResult: null, revisionLog: [], modelUsed: '',
    chatLog: [], error: null, documentText: '', fileName: '', conditions: '',
  }),
}))

export default useStore
