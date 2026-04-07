"""
Autonomous Content Factory — FastAPI backend v5.1.0

CHANGED in v5.1.0:
  - FactSheetValidation is now FATAL for density failures.
    A _DensityError from the research agent surfaces as HTTP 422
    with a clear user-facing message instead of propagating into
    copywriting and failing 53 seconds later with a confusing error.
  - Added import for _DensityError from research_agent.
  - Version bump 5.0.0 → 5.1.0.
"""
import logging
import os
import json
import zipfile
from io import BytesIO

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agents.research_agent import ResearchAgent, _DensityError
from agents.copywriter_agent import CopywriterAgent
from agents.editor_agent import EditorAgent
from utils.file_parser import parse_file
from utils.pipeline import (
    PipelineStep,
    preprocess_document,
    validate_fact_sheet,
    validate_content,
    ValidationError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("main")

app = FastAPI(title="Autonomous Content Factory", version="5.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def resolve_key(provider: str, ui_key: str = "") -> str:
    if ui_key and ui_key.strip():
        return ui_key.strip()
    env_map = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "groq":   "GROQ_API_KEY",
    }
    key = os.environ.get(env_map.get(provider, "GEMINI_API_KEY"), "").strip()
    if not key:
        var = env_map.get(provider, "GEMINI_API_KEY")
        raise HTTPException(
            400,
            f"No API key for '{provider}'. Add {var}=your_key to backend/.env and restart.",
        )
    return key


def resolve_model(provider: str, model: str) -> str:
    if model and model.strip():
        return model.strip()
    return {
        "gemini": "gemini-2.0-flash",
        "openai": "gpt-4o-mini",
        "claude": "claude-sonnet-4-5",
        "groq":   "llama-3.3-70b-versatile",
    }.get(provider, "gemini-2.5-flash")


class PipelineRequest(BaseModel):
    document_text:      str
    tone_blog:          str   = "professional"
    tone_social:        str   = "casual"
    tone_email:         str   = "persuasive"
    creativity:         float = Field(default=0.5, ge=0.0, le=1.0)
    selected_content:   list  = ["blog", "social", "email"]
    api_provider:       str   = "gemini"
    api_key:            str   = ""
    model_name:         str   = ""
    conditions:         str   = ""
    max_revision_loops: int   = Field(default=3, ge=1, le=6)


@app.get("/")
async def root():
    return {"status": "ok", "version": "5.1.0"}


@app.get("/api/config")
async def get_config():
    return {
        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
        "openai_configured": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "claude_configured": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
        "groq_configured":   bool(os.environ.get("GROQ_API_KEY", "").strip()),
        "default_provider":  os.environ.get("DEFAULT_PROVIDER", "gemini"),
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".pdf", ".txt", ".docx", ".doc"}:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Use PDF, TXT, or DOCX.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty.")
    try:
        text = parse_file(data, ext)
    except Exception as e:
        raise HTTPException(422, f"Could not parse file: {e}")
    if len(text.strip()) < 20:
        raise HTTPException(422, "Document is too short or contains no readable text.")
    return {"filename": file.filename, "text": text, "char_count": len(text)}


@app.post("/api/run-pipeline")
async def run_pipeline(req: PipelineRequest):

    # ── Stage 1: Input validation ──────────────────────────────────────────
    with PipelineStep("InputValidation"):
        if not req.document_text or len(req.document_text.strip()) < 20:
            raise HTTPException(400, "Document text is too short (minimum 20 characters).")

        provider  = req.api_provider.lower()
        api_key   = resolve_key(provider, req.api_key)
        model     = resolve_model(provider, req.model_name)
        tones     = {"blog": req.tone_blog, "social": req.tone_social, "email": req.tone_email}
        selected  = [
            c for c in req.selected_content if c in ("blog", "social", "email")
        ] or ["blog", "social", "email"]
        max_loops = max(1, min(req.max_revision_loops, 6))

        logger.info(
            "Pipeline start | provider=%s model=%s selected=%s creativity=%.2f loops=%d",
            provider, model, selected, req.creativity, max_loops,
        )

    # ── Stage 2: Preprocessing ─────────────────────────────────────────────
    with PipelineStep("Preprocessing"):
        clean_doc = preprocess_document(req.document_text, max_chars=7000)
        logger.info(
            "Document: %d chars raw → %d chars preprocessed",
            len(req.document_text), len(clean_doc),
        )

    # ── Stage 3: Research ──────────────────────────────────────────────────
    with PipelineStep("Research"):
        try:
            fact_sheet = ResearchAgent(provider, api_key, model).run(clean_doc)
        except _DensityError as e:
            raise HTTPException(422, str(e))
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                raise HTTPException(429, (
                    "Gemini API quota exceeded. "
                    "Wait ~1 minute and retry, or switch to gemini-1.5-flash which has "
                    "higher free-tier limits (15 req/min, 1500 req/day)."
                ))
            raise HTTPException(500, f"Research Agent failed: {e}")

    # ── Stage 4: Fact sheet validation ────────────────────────────────────
    with PipelineStep("FactSheetValidation"):
        try:
            validate_fact_sheet(fact_sheet)
            total_facts = (
                len(fact_sheet.get("features", []))
                + len(fact_sheet.get("key_benefits", []))
                + len(fact_sheet.get("specifications", []))
            )
            logger.info(
                "Fact sheet OK — product: '%s' | features: %d | benefits: %d | "
                "specs: %d | total_facts: %d",
                fact_sheet.get("product_name", "?"),
                len(fact_sheet.get("features", [])),
                len(fact_sheet.get("key_benefits", [])),
                len(fact_sheet.get("specifications", [])),
                total_facts,
            )
        except ValidationError as e:
            # ValidationError from validate_fact_sheet means the document is
            # too vague — return 422 so the frontend shows a useful message
            raise HTTPException(422, str(e))

    # ── Stage 5: Copywriting ───────────────────────────────────────────────
    with PipelineStep("Copywriting"):
        cw = CopywriterAgent(provider, api_key, model)
        try:
            content = cw.run(
                fact_sheet,
                tones=tones,
                creativity=req.creativity,
                selected=selected,
                conditions=req.conditions,
            )
        except ValueError as e:
            raise HTTPException(500, f"Copywriter failed after retries: {e}")
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                raise HTTPException(429, (
                    "Gemini API quota exceeded during copywriting. "
                    "Wait ~1 minute and retry, or switch to gemini-1.5-flash."
                ))
            raise HTTPException(500, f"Copywriter Agent error: {e}")

    # ── Stage 6: Output validation ─────────────────────────────────────────
    with PipelineStep("OutputValidation"):
        validation_errors = validate_content(content, selected)
        if validation_errors:
            logger.warning("Output validation issues: %s", validation_errors)
        else:
            logger.info("Output validation: all pieces passed")

    # ── Stages 7+8: Editor review + revision loop ─────────────────────────
    ed = EditorAgent(provider, api_key, model)
    editor_result = None
    revision_log  = []

    for loop in range(max_loops):
        with PipelineStep(f"EditorReview-Loop{loop + 1}"):
            try:
                editor_result = ed.run(fact_sheet, content)
            except Exception as e:
                raise HTTPException(500, f"Editor Agent failed on loop {loop + 1}: {e}")

        overall = editor_result.get("overall_status", "rejected")
        logger.info(
            "Editor loop %d: %s | scores: %s",
            loop + 1, overall, editor_result.get("scores", {})
        )

        if overall == "approved":
            logger.info("All content approved on loop %d", loop + 1)
            break

        feedback = {
            k: editor_result[k].get("feedback", "")
            for k in ["blog", "social", "email"]
            if content.get(k) and str(content[k]).strip()
        }
        if not feedback:
            editor_result["overall_status"] = "approved"
            break

        revision_log.append({
            "loop":     loop + 1,
            "rejected": list(feedback.keys()),
            "feedback": {k: v[:400] for k, v in feedback.items()},
        })

        if loop == max_loops - 1:
            logger.warning("Max loops (%d) reached — returning best result", max_loops)
            break

        with PipelineStep(f"Revision-Loop{loop + 1}"):
            try:
                content = cw.revise(
                    fact_sheet, content,
                    feedback_by_type=feedback,
                    tones=tones,
                    conditions=req.conditions,
                    creativity=req.creativity,
                )
            except Exception as e:
                revision_log[-1]["revision_error"] = str(e)
                logger.error("Revision failed on loop %d: %s", loop + 1, e)
                break

    # ── Stage 9: Response assembly ─────────────────────────────────────────
    final_status = editor_result.get("overall_status", "unknown") if editor_result else "no_review"
    logger.info("Pipeline complete | loops=%d status=%s", len(revision_log), final_status)

    return {
        "fact_sheet":    fact_sheet,
        "content":       content,
        "editor_result": editor_result,
        "revision_log":  revision_log,
        "model_used":    model,
        "provider":      provider,
    }


@app.post("/api/regenerate-json")
async def regenerate(body: dict):
    provider   = body.get("api_provider", "gemini").lower()
    api_key    = resolve_key(provider, body.get("api_key", ""))
    model      = resolve_model(provider, body.get("model_name", ""))
    fs         = body.get("fact_sheet", {})
    ctype      = body.get("content_type", "blog")
    tone_str   = body.get("tone", "professional")
    creativity = float(body.get("creativity", 0.5))
    conditions = body.get("conditions", "")
    if not fs:
        raise HTTPException(400, "fact_sheet is required.")
    try:
        result = CopywriterAgent(provider, api_key, model).regenerate_single(
            fs, ctype, tone_str, creativity, conditions
        )
        return {"content_type": ctype, "content": result}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/export")
async def export_campaign(body: dict):
    fs      = body.get("fact_sheet", {})
    content = body.get("content", {})
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("factsheet.json", json.dumps(fs, indent=2))
        if content.get("blog"):
            zf.writestr("blog.txt", content["blog"])
        if content.get("social"):
            s = content["social"]
            text = (
                ("\n\n" + "-" * 40 + "\n\n").join(s) if isinstance(s, list) else s
            )
            zf.writestr("social.txt", text)
        if content.get("email"):
            zf.writestr("email.txt", content["email"])
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=campaign_kit.zip"},
    )
