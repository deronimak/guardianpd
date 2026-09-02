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
    platform_auth,
    schools,
    staff_accounts,
    students,
    welfare,
)

# Without this, INFO-level logs from app.core.email/push (the "log instead
# of send" dev fallback) are silently swallowed under uvicorn — Python's
# default root logger level is WARNING. The welfare job's CLI entrypoint
# sets this itself; the API needs it done here at import time instead.
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="GuardianPD API")

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
app.include_router(platform_auth.router)
app.include_router(schools.router)
app.include_router(billing.router)
app.include_router(auth.router)
app.include_router(parent_auth.router)
app.include_router(parent.router)
app.include_router(guardians.router)
app.include_router(students.router)
app.include_router(staff_accounts.router)
app.include_router(absences.router)
app.include_router(attendance.router)
app.include_router(welfare.router)

# Platform ops console (ARCHITECTURE.md §10) — a plain static page, not
# part of the Flutter app, served same-origin so it needs no CORS config.
# Logs in against POST /auth/platform/login like any other client.
_STATIC_ADMIN_DIR = os.path.join(os.path.dirname(__file__), "static", "admin")
app.mount("/admin", StaticFiles(directory=_STATIC_ADMIN_DIR, html=True), name="admin")

# School Admin web console — same idea as /admin above but for one school's
# own admin (POST /auth/staff/login + role="admin"), scoped to the one
# high-volume task that's slow on a phone: bulk guardian+children entry and
# printing QR credentials. Not a web port of the whole mobile admin surface.
_STATIC_SCHOOL_ADMIN_DIR = os.path.join(os.path.dirname(__file__), "static", "school_admin")
app.mount(
    "/school-admin", StaticFiles(directory=_STATIC_SCHOOL_ADMIN_DIR, html=True), name="school_admin"
)

# Public privacy policy page, required for the Play Console listing.
_STATIC_LEGAL_DIR = os.path.join(os.path.dirname(__file__), "static", "legal")
app.mount("/privacy", StaticFiles(directory=_STATIC_LEGAL_DIR, html=True), name="legal")

# Terms of service + refund policy — Paystack's merchant verification (and
# good practice generally) expects these alongside the privacy policy.
_STATIC_TERMS_DIR = os.path.join(_STATIC_LEGAL_DIR, "terms")
app.mount("/terms", StaticFiles(directory=_STATIC_TERMS_DIR, html=True), name="terms")
_STATIC_REFUND_DIR = os.path.join(_STATIC_LEGAL_DIR, "refund")
app.mount("/refund", StaticFiles(directory=_STATIC_REFUND_DIR, html=True), name="refund")

# Account/data deletion request page — the URL Play Console's Data Safety
# form links to under "Account deletion". No self-service delete endpoint
# exists yet, so this explains the (manual, email-based) request process.
_STATIC_DELETE_ACCOUNT_DIR = os.path.join(_STATIC_LEGAL_DIR, "delete-account")
app.mount(
    "/delete-account", StaticFiles(directory=_STATIC_DELETE_ACCOUNT_DIR, html=True), name="delete_account"
)

# Where Paystack redirects a school's browser after a checkout attempt
# (see PAYSTACK_CALLBACK_URL / app/api/routes/billing.py). The actual
# invoice status update happens via the /platform/billing/webhook
# server-to-server call, not this page — it's just a human-readable landing.
_STATIC_BILLING_DIR = os.path.join(os.path.dirname(__file__), "static", "billing_thank_you")
app.mount("/billing/thank-you", StaticFiles(directory=_STATIC_BILLING_DIR, html=True), name="billing_thank_you")

# Public marketing site — Paystack's merchant verification requires an
# active website describing the business, separate from the API/consoles
# above. Mounted at "/" and registered last so it only ever catches
# requests no earlier, more specific route (API or console) already matched.
_STATIC_SITE_DIR = os.path.join(os.path.dirname(__file__), "static", "site")
app.mount("/", StaticFiles(directory=_STATIC_SITE_DIR, html=True), name="site")
