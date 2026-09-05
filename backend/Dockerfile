FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Railway (and most PaaS hosts) inject the port to listen on via $PORT at
# runtime rather than a fixed value, so this needs shell-form CMD to expand
# it — falls back to 8000 for `docker run` locally where $PORT isn't set.
#
# app.jobs.migrate runs the platform + every tenant database's Alembic
# migrations first, on every boot — see that module's docstring for why
# this is safe to run unconditionally (idempotent) and why a single
# tenant's migration failing doesn't stop the app from starting.
CMD ["sh", "-c", "python -m app.jobs.migrate && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
