"""
REST API Server for SciTrans

Provides programmatic access to translation services.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from pydantic import BaseModel

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning("FastAPI not available. API server disabled.")


if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="SciTrans API",
        description="REST API for scientific PDF translation",
        version="1.0.0",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request/Response models
    class TranslationRequest(BaseModel):
        source_lang: str = "en"
        target_lang: str = "fr"
        backend: str = "cascade_free"
        model: Optional[str] = None
        render_mode: str = "perfect"
        n_candidates: int = 3
        context_window: int = 2
        use_cache: bool = True

    class TranslationResponse(BaseModel):
        job_id: str
        status: str
        message: str

    class JobStatus(BaseModel):
        job_id: str
        status: str
        progress: float
        output_pdf: Optional[str] = None
        error: Optional[str] = None

    # Job storage (in production, use Redis or database)
    jobs: dict[str, dict] = {}

    @app.get("/")
    async def root():
        """API root endpoint."""
        return {
            "name": "SciTrans API",
            "version": "1.0.0",
            "status": "running",
        }

    @app.post("/translate", response_model=TranslationResponse)
    async def translate_pdf(
        background_tasks: BackgroundTasks,
        file: UploadFile,
        source_lang: str = "en",
        target_lang: str = "fr",
        backend: str = "cascade_free",
        model: Optional[str] = None,
        render_mode: str = "perfect",
    ):
        """
        Upload PDF and start translation job.

        Returns job ID for status checking.
        """
        import uuid

        from scitrans.cli.main import _get_backend
        from scitrans.pipeline import PipelineConfig, run_pipeline
        from scitrans.utils.env_loader import load_environment_variables

        load_environment_variables()

        job_id = str(uuid.uuid4())

        # Save uploaded file
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        file_path = upload_dir / f"{job_id}_{file.filename}"

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Initialize job
        jobs[job_id] = {
            "status": "processing",
            "progress": 0.0,
            "input_file": str(file_path),
            "output_file": None,
            "error": None,
        }

        # Start translation in background
        async def process_translation():
            try:
                be = _get_backend(backend, model=model or backend)
                cfg = PipelineConfig(
                    source_lang=source_lang,
                    target_lang=target_lang,
                    model=model or backend,
                    render_mode=render_mode,
                )

                output_file = upload_dir / f"{job_id}_translated.pdf"

                run_pipeline(
                    input_pdf=str(file_path),
                    output_pdf=str(output_file),
                    backend=be,
                    cfg=cfg,
                )

                jobs[job_id]["status"] = "completed"
                jobs[job_id]["progress"] = 1.0
                jobs[job_id]["output_file"] = str(output_file)

            except Exception as e:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["error"] = str(e)
                logger.error(f"Translation job {job_id} failed: {e}")

        background_tasks.add_task(process_translation)

        return TranslationResponse(
            job_id=job_id,
            status="processing",
            message="Translation started",
        )

    @app.get("/job/{job_id}", response_model=JobStatus)
    async def get_job_status(job_id: str):
        """Get translation job status."""
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")

        job = jobs[job_id]
        return JobStatus(
            job_id=job_id,
            status=job["status"],
            progress=job["progress"],
            output_pdf=job.get("output_file"),
            error=job.get("error"),
        )

    @app.get("/download/{job_id}")
    async def download_translated(job_id: str):
        """Download translated PDF."""
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")

        job = jobs[job_id]
        if job["status"] != "completed":
            raise HTTPException(status_code=400, detail="Job not completed")

        output_file = Path(job["output_file"])
        if not output_file.exists():
            raise HTTPException(status_code=404, detail="Output file not found")

        return FileResponse(
            output_file,
            media_type="application/pdf",
            filename=output_file.name,
        )

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}


def run_api_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the API server."""
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not installed. Install with: pip install fastapi uvicorn")

    import uvicorn

    uvicorn.run(app, host=host, port=port)
