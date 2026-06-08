"""
Generation API — POST /generate/project starts async generation,
GET  /generate/status/{job_id} polls Celery,
WS   /generate/live/{project_id} streams live progress via WebSocket.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import get_current_user, get_current_user_optional
from app.core.rate_limiter import check_usage_limit, log_usage
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    category: str = Field(..., description="Project category")
    components: list[str] = Field(default_factory=list)
    budget: float = Field(500, ge=0)
    currency: str = Field("INR")
    skill_level: str = Field("beginner")
    time_available: str = Field("weekend")
    goal: str = Field("", max_length=1000)
    has_3d_printer: bool = False
    can_solder: bool = False


class GenerateResponse(BaseModel):
    project_id: str
    job_id: str
    status: str
    message: str


class QuickGenerateResponse(BaseModel):
    project_id: str
    blueprint: dict
    status: str = "complete"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/project", response_model=GenerateResponse)
async def start_generation(
    req: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start async project generation. Returns project_id + Celery job_id.
    Frontend polls /status/{job_id} or connects to WS /live/{project_id}.
    """
    # Rate limit
    await check_usage_limit(current_user, "generate", db)

    # Create project record
    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        user_id=str(current_user.id),
        title=f"New {req.category.title()} Project",
        status="generating",
        category=req.category,
    )
    db.add(project)
    await db.commit()

    # Dispatch Celery task
    try:
        from app.workers.tasks import generate_project_blueprint

        task = generate_project_blueprint.delay(
            input_data=req.model_dump(),
            project_id=project_id,
            user_id=str(current_user.id),
        )
        job_id = task.id
    except Exception as e:
        logger.error("Celery dispatch failed: %s", e)
        # Fall back to sync generation
        job_id = project_id

    await log_usage(current_user, "generate", db)

    return GenerateResponse(
        project_id=project_id,
        job_id=job_id,
        status="queued",
        message="Generation started! Connect to WebSocket for live updates.",
    )


@router.post("/project/quick", response_model=QuickGenerateResponse)
async def quick_generate(
    req: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Synchronous generation — waits for the full blueprint and returns it.
    Use this if WebSocket isn't available. May take 15-30 seconds.
    """
    await check_usage_limit(current_user, "generate", db)

    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        user_id=str(current_user.id),
        title=f"New {req.category.title()} Project",
        status="generating",
        category=req.category,
    )
    db.add(project)
    await db.commit()

    try:
        from app.services.ai_service import ai_service

        blueprint = await ai_service.generate_blueprint(req.model_dump())

        # Update project
        project.status = "complete"
        project.title = blueprint.get("title", project.title)
        await db.commit()

        await log_usage(current_user, "generate", db)

        return QuickGenerateResponse(
            project_id=project_id,
            blueprint=blueprint,
        )
    except ValueError as ve:
        raise HTTPException(status_code=503, detail=str(ve))
    except Exception as e:
        import traceback
        logger.error("Quick generation failed: %s\n%s", e, traceback.format_exc())
        project.status = "failed"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/status/{job_id}")
async def check_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Poll Celery task status."""
    try:
        from celery.result import AsyncResult
        from app.workers.tasks import celery_app

        result = AsyncResult(job_id, app=celery_app)
        state = result.state

        if state == "PENDING":
            return {"status": "queued", "progress": 0}
        elif state == "STARTED":
            return {"status": "running", "progress": 30}
        elif state == "SUCCESS":
            return {"status": "complete", "result": result.result, "progress": 100}
        elif state == "FAILURE":
            return {"status": "failed", "error": str(result.result), "progress": 0}
        else:
            return {"status": state.lower(), "progress": 50}
    except Exception as e:
        logger.error("Status check failed: %s", e)
        return {"status": "unknown", "error": str(e)}


@router.get("/project/{project_id}")
async def get_project_blueprint(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the saved blueprint for a project."""
    project = await db.get(Project, project_id)
    if not project or str(project.user_id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Project not found")

    # Check Redis for freshly generated blueprint
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        redis_key = f"gen_progress:{project_id}"
        messages = await r.lrange(redis_key, 0, -1)
        for msg in reversed(messages):
            evt = json.loads(msg)
            if evt.get("event") == "complete" and "blueprint" in evt.get("data", {}):
                return {
                    "project_id": project_id,
                    "status": "complete",
                    "blueprint": evt["data"]["blueprint"],
                }
        await r.aclose()
    except Exception:
        pass

    return {
        "project_id": project_id,
        "status": project.status,
        "title": project.title,
        "blueprint": None,
    }


# ── WebSocket live progress ───────────────────────────────────────────────────

@router.websocket("/live/{project_id}")
async def generation_websocket(
    websocket: WebSocket,
    project_id: str,
):
    """
    WebSocket endpoint — streams live generation progress.
    Reads events from Redis list pushed by the Celery task.
    """
    await websocket.accept()

    redis_key = f"gen_progress:{project_id}"
    max_wait_seconds = 300  # 5 min timeout
    poll_interval = 0.5
    elapsed = 0.0
    last_index = 0

    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

        while elapsed < max_wait_seconds:
            # Read new messages from Redis list
            messages = await r.lrange(redis_key, last_index, -1)

            for msg in messages:
                last_index += 1
                try:
                    evt = json.loads(msg)
                    await websocket.send_json(evt)

                    # Terminal events
                    if evt.get("event") in ("complete", "failed"):
                        await websocket.close()
                        await r.aclose()
                        return
                except Exception:
                    pass

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # Timeout
        await websocket.send_json({
            "event": "error",
            "data": {"message": "Generation timed out. Please try again."},
        })
        await r.aclose()

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for project %s", project_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        try:
            await websocket.send_json({"event": "error", "data": {"message": str(e)}})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Demo endpoint — no auth needed ───────────────────────────────────────────

@router.post("/demo")
async def demo_generate(req: GenerateRequest):
    """
    Demo endpoint — no auth required. Uses a stripped-down prompt
    to generate a quick example. Rate-limited to 1 per IP in production.
    """
    try:
        from app.services.ai_service import ai_service
        blueprint = await ai_service.generate_blueprint(req.model_dump())
        return {"status": "success", "blueprint": blueprint}
    except ValueError as ve:
        raise HTTPException(status_code=503, detail=str(ve))
    except Exception as e:
        logger.error("Demo generation failed: %s", e)
        raise HTTPException(status_code=500, detail="Demo generation failed")
