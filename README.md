# School Attendance QR System

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design (multi-tenant model, QR security, subscription gating, welfare-email system).

## Repo layout

```
backend/    FastAPI + PostgreSQL API (platform DB + one tenant DB per school)
mobile/     Flutter app (parent + staff/admin roles in one codebase)
```

## What's scaffolded vs. not yet built

**Working now:**
- Platform DB / tenant DB split, with per-school tenant provisioning (`POST /platform/schools`, gated by a real platform-staff login — see "Platform staff accounts" below)
- Signed, static, revocable QR tokens (`app/core/security.py`)
- Full scan flow: subscription gate → signature check → revocation check → per-child authorization check → attendance write, with flagged events on unauthorized attempts
- Staff login (JWT) and guardian creation + QR issuance
- Printed QR credential as a downloadable PDF (`GET /guardians/{id}/qr-credential.pdf`)
- Welfare/absence email job (`app/jobs/welfare_check.py`), timezone-aware per school — see "Welfare email job" below
- Parent account activation + login (platform-level, spans every school a parent's children attend) and a linked-children list
- Real-time push notification fan-out on every scan (success and unauthorized-attempt cases), best-effort — one bad device token can't fail the scan or block other guardians' notifications, and dead tokens get pruned automatically — see "Push notifications" below
- Paystack checkout-session creation + webhook handling for subscription status — see "Billing" below
- Platform ops console (`/admin`, same-origin static page) to enroll schools and override subscription status, with a real login instead of curl + a shared key
- Flutter app: role selection, staff login with live camera QR scanning, parent login/activation with a real linked-children list, and (Android) real push notification registration via Firebase — see "Push notifications" for the one file you still need to add
- Parent-facing attendance history and planned-absence marking (`GET`/`POST /parent/me/schools/{slug}/students/{id}/...`) — tap a child in My Children to see it. Same authorization boundary as the scan flow: a parent can only read/write for a student they're actually linked to.
- Atomic platform-DB + tenant-DB writes (guardian creation, school enrollment) via PostgreSQL two-phase commit — see "Cross-database atomicity" below
- Real platform-staff auth (`PlatformStaffUser` login) replacing the old shared admin key — see "Platform staff accounts" below

**Not yet built** (see ARCHITECTURE.md for the design):
- Notification-preferences screen in the parent app
- **iOS is blocked in this dev environment, not just undone**: push notification wiring, and building/running the app at all, both require Xcode on macOS. This project was built entirely on Windows, which has no path to either — someone with a Mac needs to pick this up (`flutterfire configure` + `GoogleService-Info.plist`, then the standard `firebase_messaging` iOS setup)
- Paystack checkout wiring in the Flutter app itself (backend is ready; see "Billing" below)

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

Bootstrap a platform-staff account (needed before you can enroll a school — see "Platform staff accounts" below), then log in and enroll your first school:

```bash
python -m app.jobs.create_platform_staff --email you@example.com --name "Your Name"
```

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/platform/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"<what you set above>"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://127.0.0.1:8000/platform/schools \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"Example High","slug":"example-high","admin_name":"Jane Admin","admin_email":"jane@example-high.example.com","admin_temp_password":"changeme123","timezone":"America/New_York"}'
```

This provisions the school's own Postgres database automatically and seeds its first staff admin account — the `School`/`Subscription`/`StaffUser` rows across both databases are written atomically (see "Cross-database atomicity" below).

## Mobile app setup

```bash
cd mobile
flutter pub get
flutter run
```

The API base URL is set in `lib/core/api_client.dart` — defaults to `10.0.2.2:8000` (the Android emulator's route to your host machine). Change it for a physical device or a deployed backend.

## Printed QR credentials

`GET /guardians/{guardian_id}/qr-credential.pdf` (staff-authed) generates a PDF with the guardian's name, the school's name, and the QR image — deliberately no children's names or photos (ARCHITECTURE.md §5). This is what staff print and hand to a parent at enrollment.

## Parent accounts

School staff create the guardian record (`POST /guardians`) as before; that now also emails an activation code to the guardian (logged instead of sent if `SMTP_HOST` is unset, same as the welfare job). The parent then:

1. `POST /auth/parent/activate` with `{email, invite_token, password}` — sets their password, returns a JWT.
2. `POST /auth/parent/login` with `{email, password}` for subsequent logins.
3. `GET /parent/me/children` (Bearer token) — every child linked to them, aggregated across every school they touch.

Parent tokens are platform-level, not school-scoped — no `X-School-Slug` header needed for these three endpoints.

## Push notifications

On every scan, all guardians linked to the child get a push notification (success) or, for an unauthorized-guardian attempt, the *real* guardians get an alert (ARCHITECTURE.md §5/§6).

**Local dev:** leave `FIREBASE_CREDENTIALS_JSON` unset — pushes are logged instead of sent (`app/core/push.py`), same fallback pattern as email.

**Backend — to go live:** you need your own Firebase project (Firebase console → Project settings → Service accounts → Generate new private key). Set `FIREBASE_CREDENTIALS_JSON` in `.env` to that JSON key file's contents (as a single-line value).

**Mobile (Android) — wired up, needs one file from you:** the app calls `initializeAndRegisterPush()` on parent login (`lib/core/push_registration.dart`), which requests notification permission, gets a real FCM token, and registers it via `POST /parent/me/devices`. This deliberately does **not** need the Firebase CLI or `flutterfire configure` (which would require logging into your Google account) — Android-only Firebase setup just needs one file:

1. In the Firebase console for the same project as your backend key, add an Android app with package name `com.schoolqr.mobile`.
2. Download the `google-services.json` it gives you.
3. Save it as `mobile/android/app/google-services.json`.

Without that file, Android builds fail with a clear "File google-services.json is missing" error — everything else (web, Windows) is unaffected. iOS isn't wired up (needs `GoogleService-Info.plist` + Xcode, which this Windows setup can't build anyway).

Building with these plugins on Windows also needs **Developer Mode** enabled (`start ms-settings:developers`, then toggle it on) — Flutter needs symlink support to build with native Android plugins.

## Billing

Paystack checkout-session creation and a webhook that updates `Subscription.status` (`active` / `past_due` / `canceled`) are implemented (`app/api/routes/billing.py`), gated by platform-staff login like school enrollment (the webhook itself isn't — Paystack calls it directly, verified by signature instead). You need your own Paystack account:

1. Create a Plan in the Paystack dashboard and note its plan code.
2. Set `PAYSTACK_SECRET_KEY` and `PAYSTACK_PLAN_CODE` in `.env` (test-mode keys are fine for development).
3. `POST /platform/schools/{school_id}/billing/checkout-session` calls Paystack's `/transaction/initialize` and returns a `checkout_url` to redirect a school admin to. Requires the school to have a `billing_email` on file (set at enrollment, defaulting to the admin's email).
4. Register `https://<your-domain>/platform/billing/webhook` in the Paystack dashboard to receive events — webhooks are configured account-wide there, not per-session, so local testing needs a tunnel (e.g. ngrok) forwarding to `localhost:8000/platform/billing/webhook`.

Paystack signs webhooks with `PAYSTACK_SECRET_KEY` itself (HMAC-SHA512 over the raw body, in the `x-paystack-signature` header) — there's no separate webhook secret like Stripe has. Without Paystack configured, the checkout-session endpoint returns a clear `501` rather than a fake URL.

## Platform staff accounts

`POST /platform/schools` and the billing endpoints are gated by a real `PlatformStaffUser` login (`POST /auth/platform/login`, JWT with `scope: platform_ops`) — this used to be a single shared `X-Platform-Admin-Key`, which has been removed entirely.

There's no self-service signup for these accounts (they grant access to enroll schools and manage billing across every tenant), so create them with:

```bash
cd backend
python -m app.jobs.create_platform_staff --email you@example.com --name "Your Name"
```

You'll be prompted for a password interactively (not passed as an argument, so it doesn't end up in shell history). Run it again for each teammate who needs ops access.

## Cross-database atomicity

Guardian creation and school enrollment each write to two physical databases (platform DB + one tenant DB) as a single atomic unit, via PostgreSQL two-phase commit (`app/db/twophase.py`, using SQLAlchemy's `Session(twophase=True)`) — either both writes land or neither does, even if the process crashes mid-way.

This needs `max_prepared_transactions > 0` on the Postgres server (0 — disabled — is the default); `docker-compose.yml` sets it to 20. If you're running Postgres yourself rather than via the provided compose file, set this in `postgresql.conf` and restart Postgres (it can't be changed at runtime).

## Welfare email job

Sends an email to a student's guardians if they haven't been dropped off by the school's cutoff time (or dropped off but not picked up by end of day), unless a matching `ExpectedAbsence` covers today. See ARCHITECTURE.md §7 for the design.

**Local dev (no email provider needed):** leave `SMTP_HOST` unset in `.env` — emails are logged instead of sent, so you can see exactly what would have gone out:

```bash
cd backend
python -m app.jobs.welfare_check
```

**Run it for real:** set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` in `.env` to your provider's SMTP credentials (SendGrid, SES, Postmark, etc. all support plain SMTP).

**Scheduling:** the job is meant to be triggered externally and re-run often — cutoff-time gating and its idempotency log make repeated runs safe. Every 15 minutes is reasonable.

Linux/macOS cron:
```cron
*/15 * * * * cd /path/to/backend && .venv/bin/python -m app.jobs.welfare_check >> welfare.log 2>&1
```

Windows Task Scheduler: create a task that runs `C:\path\to\backend\.venv\Scripts\python.exe -m app.jobs.welfare_check` with "Start in" set to `C:\path\to\backend`, triggered every 15 minutes.

**Timezones:** cutoff times are local wall-clock times in each school's own timezone (`School.timezone`, an IANA identifier like `America/New_York`, set at enrollment — see the ops console or the `timezone` field on `POST /platform/schools`). The job converts UTC "now" into each school's local time independently, so schools in different timezones are evaluated correctly against the same run. Uses the stdlib `zoneinfo` module; `tzdata` is bundled as a dependency since Windows has no OS-level IANA timezone database.

**Per-school controls:** each school's `welfare_email_enabled`, `drop_off_cutoff_time`, `pickup_cutoff_time`, and `timezone` live on the `School` row in the platform DB. `timezone` is set at enrollment; the others have no API endpoint to change post-enrollment yet — set directly via SQL or a Python shell for now.

## Tenant database migrations (once schema changes are needed)

```bash
TENANT_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/tenant_example_high" \
  alembic -c alembic_tenant.ini upgrade head
```
