"""
FastAPI Server for Multi-Agent Supervisor Architecture.
Provides REST and WebSocket endpoints for PDF document analysis.
"""

import os
import shutil
import tempfile
from fastapi import FastAPI, WebSocket, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import asyncio
import json
from datetime import datetime

from src.multi_agent_orchestrator import create_orchestrator

app = FastAPI(
    title="Multi-Agent PDF Analyzer",
    description="Multi-Agent Supervisor Architecture for PDF Document Analysis",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global orchestrator
orchestrator = None


# ── Request / Response Models ──────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Request with a pre-extracted document text and query."""
    document_text: str
    query: str


class AnalyzeResponse(BaseModel):
    """Response from the analysis pipeline."""
    answer: str
    confidence: float
    evidence: List[str]
    routed_domain: str
    execution_time_ms: float
    trace: List[dict]


# ── Lifecycle ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    global orchestrator
    print("🚀 Initializing Multi-Agent Orchestrator...")
    orchestrator = create_orchestrator(verbose=False)
    print("✅ Orchestrator ready")


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "architecture": "multi-agent-supervisor",
        "domains": ["healthcare", "finance", "hr", "insurance", "education", "political"],
        "timestamp": datetime.now().isoformat()
    }


# ── PDF Upload Endpoint ───────────────────────────────────────────────────────

@app.post("/analyze-pdf", response_model=AnalyzeResponse)
async def analyze_pdf(
    file: UploadFile = File(...),
    query: str = Form(...)
):
    """
    Upload a PDF and ask a question.

    Usage:
        curl -X POST http://localhost:8000/analyze-pdf \\
          -F "file=@document.pdf" \\
          -F "query=What is the carbon footprint for 2018?"
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Save upload to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()

        start = datetime.now()
        result = orchestrator.process(pdf_path=tmp.name, query=query)
        elapsed_ms = (datetime.now() - start).total_seconds() * 1000

        return AnalyzeResponse(
            answer=result.answer,
            confidence=result.confidence,
            evidence=result.evidence,
            routed_domain=result.routing_decision.primary_domain.value if result.routing_decision else "general",
            execution_time_ms=round(elapsed_ms, 1),
            trace=result.trace.steps
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp.name)


# ── Text-Only Endpoint (no file upload) ───────────────────────────────────────

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_text(request: AnalyzeRequest):
    """
    Analyze pre-extracted document text (no PDF upload needed).

    Usage:
        curl -X POST http://localhost:8000/analyze \\
          -H "Content-Type: application/json" \\
          -d '{"document_text": "...", "query": "..."}'
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        start = datetime.now()

        # Use the router + agent directly with raw text
        supervisor = orchestrator.supervisor

        # Analyze and route
        doc_analysis = supervisor.analyze_document(request.document_text)
        routing = supervisor.route(request.query, request.document_text, doc_analysis)

        # Dynamically spawn and execute a single domain agent
        agent = orchestrator._create_agent(routing.primary_domain)
        agent_result = agent.process(
            query=request.query,
            document_content=request.document_text,
            context={"document_type": doc_analysis.document_type}
        )
        del agent

        elapsed_ms = (datetime.now() - start).total_seconds() * 1000

        return AnalyzeResponse(
            answer=agent_result.answer,
            confidence=agent_result.confidence,
            evidence=agent_result.evidence,
            routed_domain=routing.primary_domain.value,
            execution_time_ms=round(elapsed_ms, 1),
            trace=[]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── WebSocket Streaming ───────────────────────────────────────────────────────

@app.websocket("/analyze-stream")
async def websocket_analyze(websocket: WebSocket):
    """
    WebSocket endpoint for streaming analysis progress.

    Client sends: {"pdf_path": "/path/to/file.pdf", "query": "..."}
    Server streams step-by-step events, then final result.
    """
    await websocket.accept()

    try:
        data = await websocket.receive_text()
        request = json.loads(data)
        pdf_path = request.get("pdf_path", "")
        query = request.get("query", "")

        if not pdf_path or not query:
            await websocket.send_json({"type": "error", "message": "pdf_path and query required"})
            return

        # Run orchestrator (verbose mode will print, but we capture trace)
        orch = create_orchestrator(verbose=False)
        result = orch.process(pdf_path=pdf_path, query=query)

        # Stream trace steps
        for step in result.trace.steps:
            await websocket.send_json({"type": "step", **step})
            await asyncio.sleep(0.05)  # Small delay for visual effect

        # Final result
        await websocket.send_json({
            "type": "complete",
            "answer": result.answer,
            "confidence": result.confidence,
            "evidence": result.evidence,
        })

    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        await websocket.close()


if __name__ == "__main__":
    import uvicorn

    print("🚀 Starting Multi-Agent PDF Analyzer API...")
    print("📍 Upload PDF:   POST http://localhost:8000/analyze-pdf")
    print("📍 Text Input:   POST http://localhost:8000/analyze")
    print("📍 WebSocket:    ws://localhost:8000/analyze-stream")
    print("📍 API Docs:     http://localhost:8000/docs")

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
