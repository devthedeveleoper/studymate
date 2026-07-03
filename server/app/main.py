from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# import models so they're registered with the ORM
import app.models  # noqa: F401

from app.routers import auth, documents, chat, study


from app.core.valkey import init_valkey, close_valkey

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic for the application."""
    await init_valkey()
    yield
    await close_valkey()


app = FastAPI(
    title="StudyMate API",
    description="AI-powered study assistant — upload PDFs, chat with your notes, generate flashcards and summaries.",
    version="0.1.0",
    lifespan=lifespan,
)

import os

from app.middleware.rate_limit import RateLimitMiddleware

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Add Rate Limiting (this will run after CORS validates the origin)
app.add_middleware(RateLimitMiddleware)

# CORS — allow the Vite dev server and eventual production frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # vite dev
        "http://localhost:3000",  # fallback
        FRONTEND_URL,             # production URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# mount all routers
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(study.router)


@app.get("/health", tags=["health"])
async def health_check():
    """Quick health check to verify the API is running."""
    return {"status": "ok", "service": "studymate-api"}
