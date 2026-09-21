FROM python:3.12-slim

WORKDIR /app

# postgresql-client provides pg_dump, used by app/jobs/backup_databases.py.
# Debian trixie's default client (v17) dumping a v16 server (Railway's
# Postgres image) is a supported cross-version combination for a plain
# schema+data dump — pg_dump only requires special version-matching for
# server-specific catalog features this app's schema doesn't use.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

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
