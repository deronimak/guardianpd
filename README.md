# School Attendance QR System

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design (multi-tenant model, QR security, subscription gating, welfare-email system).

## Repo layout

```
backend/    FastAPI + PostgreSQL API (platform DB + one tenant DB per school)
mobile/     Flutter app (parent + staff/admin roles in one codebase)
```

## What's scaffolded vs. not yet built

**Working now:**
- Platform DB / tenant DB split, with per-school tenant provisioning (`POST /platform/schools`)
- Signed, static, revocable QR tokens (`app/core/security.py`)
- Full scan flow: subscription gate → signature check → revocation check → per-child authorization check → attendance write, with flagged events on unauthorized attempts
- Staff login (JWT) and guardian creation + QR issuance
- Flutter app: role selection, staff login, live camera QR scanning wired to the API, parent screen placeholder

**Not yet built** (see ARCHITECTURE.md for the design):
- Real-time push notifications to guardians on scan (§5 point 5)
- Welfare/absence email job (§7) — depends on `ExpectedAbsence` UI + a scheduler, neither exists yet
- Parent account activation flow / parent login in the app
- PDF generation for the printed QR credential page
- Stripe billing integration (subscription status is currently set manually in the DB)
- Cross-database consistency handling for the platform-DB/tenant-DB writes in guardian creation and school enrollment (currently two separate commits, not atomic — see comments in `app/api/routes/guardians.py` and `schools.py`)

## Backend setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # adjust if needed
```

Start Postgres:

```bash
docker compose up -d
```

Run the platform DB migrations (currently just `create_all`; Alembic is wired up for future schema changes):

```bash
python -c "from app.db.platform import PlatformBase, engine; from app.models import platform; PlatformBase.metadata.create_all(engine)"
```

Start the API:

```bash
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for the interactive API docs.

Enroll your first school:

```bash
curl -X POST http://127.0.0.1:8000/platform/schools \
  -H "Content-Type: application/json" \
  -d '{"name":"Example High","slug":"example-high","admin_name":"Jane Admin","admin_email":"jane@example-high.test","admin_temp_password":"changeme123"}'
```

This provisions the school's own Postgres database automatically and seeds its first staff admin account.

## Mobile app setup

```bash
cd mobile
flutter pub get
flutter run
```

The API base URL is set in `lib/core/api_client.dart` — defaults to `10.0.2.2:8000` (the Android emulator's route to your host machine). Change it for a physical device or a deployed backend.

## Tenant database migrations (once schema changes are needed)

```bash
TENANT_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/tenant_example_high" \
  alembic -c alembic_tenant.ini upgrade head
```
