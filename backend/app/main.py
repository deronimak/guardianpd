import logging

from fastapi import FastAPI

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
