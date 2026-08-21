"""FastAPI app entry."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import init_backend_db
from .routes import auth, classes, homework, children

settings = get_settings()

app = FastAPI(title="AI Homework Reviewer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Serve uploaded media
app.mount("/media", StaticFiles(directory=str(settings.upload_dir)), name="media")


@app.on_event("startup")
def _startup() -> None:
    init_backend_db()


# Routers
app.include_router(auth.router)
app.include_router(classes.router)
app.include_router(homework.router)
app.include_router(children.router)


@app.get("/")
def root():
    return {
        "name": "AI Homework Reviewer",
        "version": app.version,
        "endpoints": ["/api/auth/*", "/api/classes/*", "/api/homework/*", "/api/children/*", "/media/*"],
        "dev_login": os.getenv("ENABLE_DEV_LOGIN", "1") == "1",
    }


@app.get("/health")
def health():
    return {"ok": True}
