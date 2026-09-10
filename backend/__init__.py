"""Backend FastAPI app for the homework reviewer mini-program.

Reuses the ai_teacher pipeline (vision, ASR, text polish, storage).
Adds:
  - WeChat code2session auth (with dev_login fallback for local testing)
  - User / Classroom / Membership models (extends ai_teacher.storage.models)
  - REST API for parent upload + teacher review
  - Background task: run services.ai_pipeline after upload
"""
__version__ = "0.1.0"
