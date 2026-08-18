import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    absences,
    attendance,
    auth,
    billing,
    guardians,
    health,
    parent,
    parent_auth,
    schools,
    students,
    welfare,
)

# Without this, INFO-level logs from app.core.email/push (the "log instead
# of send" dev fallback) are silently swallowed under uvicorn — Python's
# default root logger level is WARNING. The welfare job's CLI entrypoint
# sets this itself; the API needs it done here at import time instead.
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="School Attendance QR API")

# Dev-permissive CORS so the Flutter web build (served from a different
# port) can call this API from a browser. Restrict allow_origins before
# this goes anywhere near production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(schools.router)
app.include_router(billing.router)
app.include_router(auth.router)
app.include_router(parent_auth.router)
app.include_router(parent.router)
app.include_router(guardians.router)
app.include_router(students.router)
app.include_router(absences.router)
app.include_router(attendance.router)
app.include_router(welfare.router)

# Platform ops console (ARCHITECTURE.md §10) — a plain static page, not
# part of the Flutter app, served same-origin so it needs no CORS config.
# Internal tool: gated by the X-Platform-Admin-Key it prompts for, not a
# real login.
_STATIC_ADMIN_DIR = os.path.join(os.path.dirname(__file__), "static", "admin")
app.mount("/admin", StaticFiles(directory=_STATIC_ADMIN_DIR, html=True), name="admin")
