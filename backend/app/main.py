from fastapi import FastAPI

from app.api.routes import attendance, auth, guardians, health, schools, students

app = FastAPI(title="School Attendance QR API")

app.include_router(health.router)
app.include_router(schools.router)
app.include_router(auth.router)
app.include_router(guardians.router)
app.include_router(students.router)
app.include_router(attendance.router)
