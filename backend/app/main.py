from contextlib import asynccontextmanager
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.api.v1 import auth, projects, generate, components, subscriptions
from app.db.session import engine, Base
import app.models.user    # noqa: F401 – register models with Base
import app.models.project  # noqa: F401 – register models with Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create all tables on startup (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.APP_NAME,
    description="AI copilot for physical engineering projects",
    version="0.1.0",
    docs_url="/docs",  # temp: always enabled for debugging
)

# ─── Global error handler (temp: surface real errors) ───────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc), "trace": traceback.format_exc()[-2000:]},
    )


# ─── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "https://*.vercel.app",   # Vercel preview deployments
        "http://localhost:3000",  # local dev
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ────────────────────────────────────────────────────────────────
app.include_router(auth.router,          prefix="/api/v1/auth",          tags=["Auth"])
app.include_router(projects.router,      prefix="/api/v1/projects",      tags=["Projects"])
app.include_router(generate.router,      prefix="/api/v1/generate",      tags=["Generate"])
app.include_router(components.router,    prefix="/api/v1/components",    tags=["Components"])
app.include_router(subscriptions.router, prefix="/api/v1/subscriptions", tags=["Subscriptions"])


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/debug/db")
async def debug_db():
    """Temporary: check DB connection and table list."""
    import traceback
    from sqlalchemy import text
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            ))
            tables = [row[0] for row in result]
        db_url_safe = str(engine.url).replace(str(engine.url.password or ""), "***")
        return {"status": "ok", "tables": tables, "db_url": db_url_safe}
    except Exception as e:
        return {"status": "error", "error": str(e), "trace": traceback.format_exc()}
