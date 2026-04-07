# Autonomous Content Factory

A production-ready multi-agent AI marketing pipeline that transforms any document into a full content campaign using three specialized AI agents.

## Solution

The Autonomous Content Factory solves the problem of content inconsistency and creative burnout by introducing a multi-agent AI pipeline that automates the entire content creation process from a single input document.

Instead of manually rewriting content for different platforms, the system uses specialized AI agents that work together in a structured workflow:

## Agent Descriptions

### 1\. Research Agent (`research_agent.py`)

* Parses raw document text
* Extracts: product name, features, specs, target audience, value proposition
* Flags ambiguous or unverifiable claims
* Produces structured JSON fact sheet
* **Rule**: Zero hallucination — only uses source document

### 2\. Copywriter Agent (`copywriter_agent.py`)

* Takes fact sheet as input
* Generates: 500-word blog post, 5 social posts (≤280 chars), email teaser
* Tone is dynamically controlled (professional/casual/formal/friendly/persuasive)
* Creativity slider adjusts temperature and style guidance

### 3\. Editor-in-Chief Agent (`editor_agent.py`)

* Cross-checks content against fact sheet
* Detects hallucinated features, fake claims, tone mismatches
* Returns approval status + scores (accuracy, tone, completeness)
* If rejected, copywriter auto-revises with correction note
\---

## Quick Start (After Extracting ZIP)

### Step 1 — Prerequisites

Make sure you have installed:

* **Python 3.10+** → https://python.org
* **Node.js 18+** → https://nodejs.org
* A **Gemini API Key** (free) → https://aistudio.google.com/app/apikey

  * OR an **OpenAI API Key** → https://platform.openai.com/api-keys
  * OR a **GROQ API Key** → https://console.groq.com/keys

### Step 2 — Set Up the Backend

Open a terminal and run:

```bash
cd autonomous-content-factory/backend

# Create a virtual environment (recommended)
python -m venv venv

# Activate it:
# On Windows:
venv\\\\\\\\Scripts\\\\\\\\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the backend server
uvicorn main:app --reload --port 8000
```

You should see: `Uvicorn running on http://127.0.0.1:8000`

### Step 3 — Set Up the Frontend

Open a **second terminal** window:

```bash
cd autonomous-content-factory/frontend

# Install Node dependencies
npm install

# Start the frontend dev server
npm run dev
```

You should see: `Local: http://localhost:5173`

### Step 4 — Open the App

Open your browser and go to:

```
http://localhost:5173
```

### Step 5 — Use the App

1. **Select API Provider** — Choose GROQ (recommended) or OpenAI or Gemini
2. **Enter your API Key** — Paste your key (it stays in your browser, never stored)
3. **Choose a Model** — Default is `gemini-2.0-flash` (fast + capable)
4. **Upload a Document** — PDF, TXT, or DOCX (product spec, brief, etc.)
5. **Click "Start Campaign"** — Watch three agents work in real time
6. **Review \& Export** — Edit, regenerate specific pieces, download ZIP

\---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Frontend (React/Vite)                  │
│  UploadPage → PipelinePage (Agent Room) → ResultsPage   │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP (proxied)
┌────────────────────────▼────────────────────────────────┐
│                  Backend (FastAPI)                        │
│  POST /api/upload  →  parse PDF/TXT/DOCX                │
│  POST /api/run-pipeline  →  3-agent pipeline            │
│  POST /api/regenerate-json  →  single content piece     │
│  POST /api/export  →  ZIP download                      │
└────────┬──────────────────────────────────┬─────────────┘
         │                                  │
┌────────▼────────┐  ┌──────────────┐  ┌───▼──────────────┐
│  Research Agent │  │  Copywriter  │  │  Editor Agent    │
│  Fact Sheet JSON│→ │  Blog+Social │→ │  Approve/Reject  │
│  No hallucination│  │  +Email      │  │  Scores content  │
└─────────────────┘  └──────────────┘  └──────────────────┘
         │                   │                   │
         └───────────────────┴───────────────────┘
                         │
              ┌──────────▼──────────┐
              │   AI Client Wrapper │
              │  Gemini  │  OpenAI  │
              └─────────────────────┘
```

\---

## 📁 Project Structure

```
autonomous-content-factory/
├── backend/
│   ├── main.py                  # FastAPI app + all routes
│   ├── requirements.txt
│   ├── agents/
│   │   ├── research\\\\\\\_agent.py
│   │   ├── copywriter\\\\\\\_agent.py
│   │   └── editor\\\\\\\_agent.py
│   └── utils/
│       ├── ai\\\\\\\_client.py         # Gemini + OpenAI wrapper
│       └── file\\\\\\\_parser.py       # PDF/TXT/DOCX parser
└── frontend/
    ├── index.html
    ├── vite.config.js
    ├── tailwind.config.js
    ├── package.json
    └── src/
        ├── App.jsx
        ├── main.jsx
        ├── index.css
        ├── store/
        │   └── useStore.js      # Zustand global state
        ├── pages/
        │   ├── UploadPage.jsx
        │   ├── PipelinePage.jsx
        │   └── ResultsPage.jsx
        ├── components/
        │   ├── Header.jsx
        │   └── Sidebar.jsx
        └── utils/
            └── api.js           # Frontend API calls
```

\---

## ⚙️ Configuration

|Setting|Where|Description|
|-|-|-|
|API Key|Browser UI|Entered per-session, never stored on server|
|API Provider|Browser UI|Gemini or OpenAI|
|Model|Browser UI|Choose from dropdown|
|Tone|Sidebar|5 tone options|
|Creativity|Sidebar slider|0% (safe) → 100% (creative)|
|Content Types|Sidebar checkboxes|Blog / Social / Email|

\---

## 🔧 Troubleshooting

**Backend won't start?**

* Make sure you activated your virtualenv
* Run `pip install -r requirements.txt` again

**"API key is required" error?**

* Make sure you entered your key in the API Configuration box on the upload page

**"Could not parse file" error?**

* Ensure the file is not password-protected
* For PDFs, ensure they contain real text (not scanned images)

**CORS errors in browser?**

* Make sure both servers are running (port 8000 and 5173)
* The Vite dev server proxies `/api` to `localhost:8000` automatically

**Frontend styles broken?**

* Run `npm install` inside the `frontend/` folder

\---

## Export

Click **"Export Campaign Kit"** to download a `campaign\\\\\\\_kit.zip` containing:

* `blog.txt` — full blog post
* `social.txt` — all 5 social posts
* `email.txt` — email teaser paragraph
* `factsheet.json` — structured product data

\---

## Tech Stack

* **Frontend**: React 18 + Vite + Tailwind CSS + Zustand
* **Backend**: FastAPI + Uvicorn
* **AI**: google-genai SDK (Gemini) / openai SDK / Groq API
* **Parsing**: PyPDF2, python-docx
* **Fonts**: Syne (display), DM Sans (body), JetBrains Mono

