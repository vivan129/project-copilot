from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.v1 import auth, projects, generate, components, subscriptions

app = FastAPI(
    title=settings.APP_NAME,
    description="AI copilot for physical engineering projects",
    version="0.1.0",
    docs_url="/docs" if settings.APP_ENV == "development" else None,
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
