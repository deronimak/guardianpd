# School Attendance QR System

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design (multi-tenant model, QR security, subscription gating, welfare-email system).

## Repo layout

```
backend/    FastAPI + PostgreSQL API (platform DB + one tenant DB per school)
mobile/     Flutter app (parent + staff/admin roles in one codebase)
```

## What's scaffolded vs. not yet built

**Working now:**
- Platform DB / tenant DB split, with per-school tenant provisioning (`POST /platform/schools`, gated by an admin key — see below)
- Signed, static, revocable QR tokens (`app/core/security.py`)
- Full scan flow: subscription gate → signature check → revocation check → per-child authorization check → attendance write, with flagged events on unauthorized attempts
- Staff login (JWT) and guardian creation + QR issuance
- Printed QR credential as a downloadable PDF (`GET /guardians/{id}/qr-credential.pdf`)
- Welfare/absence email job (`app/jobs/welfare_check.py`) — see "Welfare email job" below
- Parent account activation + login (platform-level, spans every school a parent's children attend) and a linked-children list
- Real-time push notification fan-out on every scan (success and unauthorized-attempt cases), best-effort — one bad device token can't fail the scan or block other guardians' notifications, and dead tokens get pruned automatically — see "Push notifications" below
- Stripe checkout-session creation + webhook handling for subscription status — see "Billing" below
- Platform ops console (`/admin`, same-origin static page) to enroll schools and override subscription status without curl
- Flutter app: role selection, staff login with live camera QR scanning, parent login/activation with a real linked-children list, and (Android) real push notification registration via Firebase — see "Push notifications" for the one file you still need to add

**Not yet built** (see ARCHITECTURE.md for the design):
- Cross-database consistency handling for the platform-DB/tenant-DB writes in guardian creation and school enrollment (currently two separate commits, not atomic — see comments in `app/api/routes/guardians.py` and `schools.py`)
- Per-school timezone handling for the welfare job (it currently compares cutoff times against naive server-local time)
- Parent-facing `ExpectedAbsence` creation (the endpoint exists but is staff-only for now — a parent-facing version is a small addition now that parent auth exists)
- Attendance history / notification-preferences screens in the parent app
- A real ops-staff auth system (`PlatformStaffUser` has no login endpoint — platform routes are gated by a single shared admin key instead, see below)
- iOS push notification wiring (Android-only for now — see "Push notifications")
- Stripe SDK wiring in the Flutter app itself (backend is ready; see "Billing" below)

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

Enroll your first school (requires the `X-Platform-Admin-Key` header — matches `PLATFORM_ADMIN_KEY` in `.env`, defaults to `change-me-dev-only`):

```bash
curl -X POST http://127.0.0.1:8000/platform/schools \
  -H "Content-Type: application/json" \
  -H "X-Platform-Admin-Key: change-me-dev-only" \
  -d '{"name":"Example High","slug":"example-high","admin_name":"Jane Admin","admin_email":"jane@example-high.example.com","admin_temp_password":"changeme123"}'
```

This provisions the school's own Postgres database automatically and seeds its first staff admin account.

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

Stripe checkout-session creation and a webhook that updates `Subscription.status` (`active` / `past_due` / `canceled`) are implemented (`app/api/routes/billing.py`), gated by `X-Platform-Admin-Key` like school enrollment. You need your own Stripe account:

1. Set `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET` in `.env` (test-mode keys are fine for development).
2. `POST /platform/schools/{school_id}/billing/checkout-session` returns a `checkout_url` to redirect a school admin to.
3. To receive webhook events locally, use the Stripe CLI: `stripe listen --forward-to localhost:8000/platform/billing/webhook` (a separate tool you'd install yourself — not set up here).

Without Stripe configured, the checkout-session endpoint returns a clear `501` rather than a fake URL.

## Platform admin key

`POST /platform/schools` and the billing endpoints are gated by a shared secret (`X-Platform-Admin-Key` header, matching `PLATFORM_ADMIN_KEY` in `.env`) rather than real per-user auth — `PlatformStaffUser` has no login endpoint yet. Change `PLATFORM_ADMIN_KEY` from its default before this goes anywhere near production.

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

**Per-school controls:** each school's `welfare_email_enabled`, `drop_off_cutoff_time`, and `pickup_cutoff_time` live on the `School` row in the platform DB (no API endpoint to change them yet — set directly via SQL or a Python shell for now).

## Tenant database migrations (once schema changes are needed)

```bash
TENANT_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/tenant_example_high" \
  alembic -c alembic_tenant.ini upgrade head
```
