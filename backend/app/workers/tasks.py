"""
Celery background tasks for async AI project generation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from celery import Celery
from celery.utils.log import get_task_logger

from app.config import settings

logger = get_task_logger(__name__)

# ── Celery app ────────────────────────────────────────────────────────────────
celery_app = Celery(
    "project_copilot",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 min hard limit
    task_soft_time_limit=270,  # 4.5 min soft limit
)


# ── Redis helper for WebSocket progress pushes ────────────────────────────────
def push_progress(redis_key: str, event: str, data: dict) -> None:
    """Push a progress event to Redis for WebSocket pickup."""
    try:
        import redis as redis_lib

        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        message = json.dumps({"event": event, "data": data, "ts": datetime.now(timezone.utc).isoformat()})
        r.rpush(redis_key, message)
        r.expire(redis_key, 600)  # 10 min TTL
    except Exception as e:
        logger.warning("Redis push failed: %s", e)


# ── Task ──────────────────────────────────────────────────────────────────────
@celery_app.task(bind=True, name="generate_project_blueprint")
def generate_project_blueprint(self, input_data: dict, project_id: str, user_id: str):
    """
    Async task: generate a blueprint via Claude and save to DB.
    Progress events are pushed to Redis so WebSocket can relay them live.
    """
    redis_key = f"gen_progress:{project_id}"

    try:
        push_progress(redis_key, "progress", {"step": "🚀 Starting generation...", "pct": 5})

        # Import inside task to avoid circular imports
        from app.services.ai_service import ai_service

        # Run async code in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        blueprint = None
        errors = []

        async def _run():
            nonlocal blueprint
            async for event_type, data in ai_service.generate_blueprint_stream(input_data):
                if event_type == "progress":
                    push_progress(redis_key, "progress", data)
                elif event_type == "blueprint":
                    blueprint = data
                elif event_type == "error":
                    errors.append(data)
                    push_progress(redis_key, "error", {"message": data})

        loop.run_until_complete(_run())
        loop.close()

        if errors:
            push_progress(redis_key, "failed", {"message": errors[0]})
            return {"status": "failed", "error": errors[0]}

        if not blueprint:
            push_progress(redis_key, "failed", {"message": "No blueprint generated"})
            return {"status": "failed", "error": "No blueprint generated"}

        # Save blueprint to DB (best-effort)
        try:
            _save_blueprint_sync(project_id, user_id, input_data, blueprint)
        except Exception as save_err:
            logger.error("DB save failed: %s", save_err)
            # Still surface the blueprint to the user

        push_progress(redis_key, "complete", {"blueprint": blueprint, "project_id": project_id})
        return {"status": "success", "project_id": project_id, "blueprint": blueprint}

    except Exception as exc:
        logger.exception("generate_project_blueprint failed: %s", exc)
        push_progress(redis_key, "failed", {"message": str(exc)})
        self.update_state(state="FAILURE", meta={"exc": str(exc)})
        raise


def _save_blueprint_sync(project_id: str, user_id: str, input_data: dict, blueprint: dict) -> None:
    """
    Synchronous DB save — runs inside the Celery worker process.
    Uses a dedicated sync DB session (not async).
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
        engine = create_engine(sync_url, pool_pre_ping=True)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            # Import here to avoid early model loading
            from app.models.project import Project, ProjectBlueprint, ProjectInput

            project = session.get(Project, project_id)
            if project:
                project.status = "complete"
                project.title = blueprint.get("title", project.title)
                project.emoji = blueprint.get("emoji", "🤖")

                # Remove old blueprint if exists
                old_bp = session.query(ProjectBlueprint).filter_by(project_id=project_id).first()
                if old_bp:
                    session.delete(old_bp)

                bp = ProjectBlueprint(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    title=blueprint.get("title", ""),
                    tagline=blueprint.get("tagline", ""),
                    difficulty=blueprint.get("difficulty", 5),
                    estimated_hours=blueprint.get("estimated_hours", 8),
                    wow_factor=blueprint.get("wow_factor", ""),
                    science_fair_tips=blueprint.get("science_fair_tips", ""),
                    next_level_upgrades=blueprint.get("next_level_upgrades", []),
                    common_mistakes=blueprint.get("common_mistakes", []),
                    presentation_script=blueprint.get("presentation_script", ""),
                )
                session.add(bp)
                session.commit()
    except Exception as e:
        logger.error("_save_blueprint_sync error: %s", e)
        # Non-fatal — blueprint is still returned via Redis
