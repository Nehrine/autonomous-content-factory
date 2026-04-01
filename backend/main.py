import os
import json
import zipfile
from io import BytesIO
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agents.research_agent import ResearchAgent
from agents.copywriter_agent import CopywriterAgent
from agents.editor_agent import EditorAgent
from utils.file_parser import parse_file

app = FastAPI(title="Autonomous Content Factory API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def resolve_api_key(provider: str, ui_key: str = "") -> str:
    if ui_key and ui_key.strip():
        return ui_key.strip()
    env_map = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
    }
    env_var = env_map.get(provider, "GEMINI_API_KEY")
    env_key = os.environ.get(env_var, "").strip()
    if env_key:
        return env_key
    raise HTTPException(
        status_code=400,
        detail=f"No API key found. Add {env_var}=your_key to backend/.env and restart.",
    )


def default_model(provider: str, model: str) -> str:
    if model:
        return model
    defaults = {
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-4o-mini",
        "claude": "claude-sonnet-4-5",
    }
    return defaults.get(provider, "gemini-2.5-flash")


class FullPipelineRequest(BaseModel):
    document_text: str
    # Per-content tones
    tone_blog:    str = "professional"
    tone_social:  str = "casual"
    tone_email:   str = "persuasive"
    creativity:   float = 0.5
    selected_content: list = ["blog", "social", "email"]
    api_provider: str = "gemini"
    api_key:      str = ""
    model_name:   str = ""
    conditions:   str = ""
    max_revision_loops: int = 3   # how many editor→revision cycles before giving up


class RegenerateRequest(BaseModel):
    fact_sheet:   dict
    content_type: str
    tone:         str = "professional"
    creativity:   float = 0.5
    api_provider: str = "gemini"
    api_key:      str = ""
    model_name:   str = ""
    conditions:   str = ""


@app.get("/")
async def root():
    return {"status": "ok", "message": "Autonomous Content Factory API v2"}


@app.get("/api/config")
async def get_config():
    return {
        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
        "openai_configured": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "claude_configured": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
        "default_provider":  os.environ.get("DEFAULT_PROVIDER", "gemini"),
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    allowed_extensions = {".pdf", ".txt", ".docx", ".doc"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty.")
    try:
        text = parse_file(content, ext)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {e}")
    if not text or len(text.strip()) < 20:
        raise HTTPException(status_code=422, detail="Document text too short.")
    return {"filename": file.filename, "text": text, "char_count": len(text)}


@app.post("/api/run-pipeline")
async def run_pipeline(request: FullPipelineRequest):
    if not request.document_text or len(request.document_text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Document text is too short.")

    provider = request.api_provider.lower()
    api_key  = resolve_api_key(provider, request.api_key)
    model    = default_model(provider, request.model_name)

    tones = {
        "blog":   request.tone_blog,
        "social": request.tone_social,
        "email":  request.tone_email,
    }

    # ── Step 1: Research ─────────────────────────────────────
    try:
        research   = ResearchAgent(provider, api_key, model)
        fact_sheet = research.run(request.document_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research Agent failed: {e}")

    # ── Step 2: Initial content generation ───────────────────
    try:
        copywriter = CopywriterAgent(provider, api_key, model)
        content    = copywriter.run(
            fact_sheet,
            tones=tones,
            creativity=request.creativity,
            selected=request.selected_content,
            conditions=request.conditions,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Copywriter Agent failed: {e}")

    # ── Step 3: Editor revision loop ─────────────────────────
    editor         = EditorAgent(provider, api_key, model)
    editor_result  = None
    revision_log   = []
    max_loops      = min(request.max_revision_loops, 5)

    for loop in range(max_loops):
        try:
            editor_result = editor.run(fact_sheet, content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Editor Agent failed: {e}")

        if editor_result.get("overall_status") == "approved":
            break

        # Get per-piece feedback for rejected items only
        feedback_by_type = editor.get_rejected_feedback(editor_result)

        if not feedback_by_type:
            break  # Nothing to revise

        revision_log.append({
            "loop": loop + 1,
            "rejected": list(feedback_by_type.keys()),
            "feedback": feedback_by_type,
        })

        if loop < max_loops - 1:
            try:
                content = copywriter.revise(
                    fact_sheet,
                    content,
                    feedback_by_type=feedback_by_type,
                    tones=tones,
                    conditions=request.conditions,
                    creativity=request.creativity,
                )
            except Exception:
                break  # Keep last content if revision itself fails

    return {
        "fact_sheet":    fact_sheet,
        "content":       content,
        "editor_result": editor_result,
        "revision_log":  revision_log,
        "model_used":    model,
        "provider":      provider,
    }


@app.post("/api/regenerate-json")
async def regenerate_content_json(request: dict):
    provider = request.get("api_provider", "gemini").lower()
    api_key  = resolve_api_key(provider, request.get("api_key", ""))
    model    = default_model(provider, request.get("model_name", ""))

    fact_sheet   = request.get("fact_sheet", {})
    content_type = request.get("content_type", "blog")
    tone         = request.get("tone", "professional")
    creativity   = float(request.get("creativity", 0.5))
    conditions   = request.get("conditions", "")

    if not fact_sheet:
        raise HTTPException(status_code=400, detail="fact_sheet is required.")

    try:
        copywriter = CopywriterAgent(provider, api_key, model)
        result     = copywriter.regenerate_single(fact_sheet, content_type, tone, creativity, conditions)
        return {"content_type": content_type, "content": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/export")
async def export_campaign(request: dict):
    fact_sheet = request.get("fact_sheet", {})
    content    = request.get("content", {})

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("factsheet.json", json.dumps(fact_sheet, indent=2))
        if content.get("blog"):
            zf.writestr("blog.txt", content["blog"])
        if content.get("social"):
            s = content["social"]
            zf.writestr("social.txt", "\n\n---\n\n".join(s) if isinstance(s, list) else s)
        if content.get("email"):
            zf.writestr("email.txt", content["email"])
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=campaign_kit.zip"},
    )
