# School Attendance QR System — Architecture Plan

## 1. Concept summary
A subscription-based (SaaS) Flutter app where you enroll multiple schools as paying tenants. Each school gets its own isolated database. Within a school:
- **Parent/Guardian**: has an account, can have multiple children linked to it, and receives a printed QR code for drop-off/pickup scanning.
- **School Admin/Staff**: scans QR codes at drop-off/pickup, manages students and guardians for their school.
- **Platform (you)**: enrolls schools, manages subscriptions/billing, provisions each school's database.

A **welfare email system** watches daily attendance and automatically emails guardians of children who weren't dropped off or picked up when expected.

## 2. Tenancy model: database-per-school

You specified each enrolled school must have its own database account, not just a shared table scoped by `school_id`. This is a real (and common) choice for school data specifically — stronger isolation for sensitive child data, trivial per-school export/deletion for compliance or offboarding, and it's easy to explain to a skeptical school administrator ("your data lives in its own database, not mixed with other schools'").

The tradeoff: every schema migration has to run across N databases instead of one, and cross-school reporting (e.g., "total scans across all schools this month" for your own ops dashboard) requires querying multiple databases and aggregating, rather than one `GROUP BY school_id`. That's the right tradeoff here given the sensitivity of the data — worth being explicit that you're accepting it.

**Two databases layers, not one:**

- **Platform DB** (single, shared): things that must exist before a school-specific DB does, and things that span schools.
- **Tenant DB** (one per school): everything specific to running that one school's attendance.

## 3. Data model

### Platform DB (central)

| Entity | Key fields | Notes |
|---|---|---|
| `School` | id, name, subdomain/slug, status (trial/active/suspended), tenant_db_connection_ref, created_at | Registry of enrolled schools + pointer to their DB |
| `Subscription` | id, school_id, plan, billing_provider_customer_id, status (trialing/active/past_due/canceled), current_period_end | Drives access — see §4 |
| `PlatformUser` (parent identity) | id, name, email/phone, password_hash, email_verified | One login identity for a parent, independent of any single school |
| `GuardianMembership` | platform_user_id, school_id, tenant_guardian_id | Maps a parent's platform login to their `Guardian` row inside each school's tenant DB — needed because a parent can have children at more than one enrolled school |
| `PlatformStaffUser` (you/your ops team) | id, name, email, role | For your own admin console, separate from school staff |

### Tenant DB (one per school)

| Entity | Key fields | Notes |
|---|---|---|
| `StaffUser` | id, name, role (admin/teacher/front_desk), email, password_hash | School's own staff, scoped to this DB automatically since the DB itself is the boundary |
| `Guardian` | id, platform_user_id (FK back to Platform DB), name, phone, email, photo_url | Local record for this school; linked to the global identity |
| `Student` | id, name, dob, class/grade, photo_url | |
| `GuardianStudentLink` | guardian_id, student_id, relationship, is_authorized_pickup | Many-to-many: multiple children per guardian, multiple authorized guardians per child |
| `QRCredential` | id, guardian_id, token (signed), issued_at, revoked_at | Signed per (guardian, school) — see §5 |
| `AttendanceEvent` | id, student_id, guardian_id, type (drop_off/pick_up), scanned_by_staff_id, timestamp, flagged, flag_reason | |
| `ExpectedAbsence` | id, student_id, date_range, reason, created_by | Parent- or staff-marked planned absence — critical input to the welfare system, see §7 |
| `SchoolCalendar` | date, is_school_day | So the welfare check doesn't fire on weekends/holidays |
| `Notification` | id, guardian_id, event_id, channel, sent_at | |

Why split it this way: a parent logs in once (Platform DB identity), and the app resolves which tenant DB(s) to query based on `GuardianMembership` rows — so a parent with one kid at School A and another at School B sees both under one login, but School A's database never has to know School B exists. Each school's QR codes and attendance stay fully inside that school's own database.

## 4. Subscription & billing

- Use a payment provider with subscription support (Stripe is the standard choice) rather than building billing logic yourself.
- **Decision: full scan lockout on lapsed payment.** A school in `past_due` or `canceled` keeps read/export access to existing records (schools need their attendance history even if they stop paying), but loses three things: new QR issuance, **QR scan validation**, and the welfare email job. This means a lapsed school can't log *any* attendance at all — including for children who already have a printed code — until payment is resolved. That's a real operational consequence (a school could be scanning-blind for a day over a billing hiccup), so the scan-validation endpoint has to check `Subscription.status` on every single scan, not just at issuance time, and the app should surface a clear "subscription inactive, contact your account rep" error to staff rather than a generic failure — this will get reported as a bug otherwise.
- Billing events arrive via webhook (payment succeeded/failed, subscription canceled) and update `Subscription` in the Platform DB — this is the one place billing logic touches, it never reaches into tenant DBs.
- School enrollment (your side): create `School` row → provision new tenant database + run migrations → create first `StaffUser` (school admin) → send them an invite → `Subscription` starts in `trialing` or `active` depending on your sales flow.

## 5. QR code security model

**Decision: static QR.** Each guardian gets one permanent, printed QR code per school (not a rotating/TOTP-style code). It doesn't expire on its own — it's valid until manually revoked (lost code, guardian removed, etc.). This is simpler to print, hand out, and laminate than any rotating scheme, but it means the security has to come from *what happens when it's scanned*, not from the code itself changing. A **static printed QR code is a photo away from being cloned**, so the compensating controls are:

1. **Signed token, not raw ID.** QR encodes a signed payload (`guardian_id + school_id + random_secret`, HMAC-signed server-side). Prevents forgery of arbitrary codes, and scoping the token to `school_id` means a leaked token can't even be tested against the wrong tenant DB.
2. **Server-side revocation.** Lost/stolen code → admin revokes in that school's DB, reissues a new one. Validation must be a live API call, not local decode-only trust (admin app still caches briefly for offline tolerance, §6).
3. **Authorization check at scan time, not just identity.** The API separately checks `GuardianStudentLink.is_authorized_pickup` for the specific child. Valid guardian scanning for a child they're not linked to → hard block.
4. **Live photo capture on scan** (recommended for MVP+1, not MVP). Cheap deterrent against code-sharing, useful in disputes.
5. **Real-time notification to *all* guardians** linked to that child, not just the scanning one — turns every other guardian into a passive fraud detector.
6. **Anomaly flagging**: duplicate scans in a short window, pickup with no matching drop-off, scans outside authorized hours.

**Printed QR credential contents.** Each printed page shows the guardian's **name** and the school's name, plus the QR image itself. Deliberately *not* printed: the linked children's names or photos. If a physical page is lost or dropped, it should only reveal whose credential it is — not which children it's tied to. That link is still fully enforced server-side at scan time (point 3 above) regardless of what's on the page; leaving it off the printout is a free reduction in what a found/stolen page can expose. Generated as a PDF, server-side, from the school's enrollment screen — the signed token is composed on the backend and never constructed on-device.

## 6. Key flows

**Drop-off / Pickup (happy path)**
1. Staff opens scanner, scans guardian's QR.
2. App calls `POST /attendance/scan` (routed to that school's tenant DB) with token + staff_id + selected child.
3. Backend validates token + authorization link, writes `AttendanceEvent`, triggers notifications to all linked guardians.
4. Staff sees child's photo + name as visual confirmation before releasing the child.

**Temporary/one-off authorized pickup** (e.g. grandparent covering for a day) — short-lived separate QR/override code, doesn't touch the permanent guardian credential.

**Unauthorized attempt** — real guardian, wrong/unlinked child → hard block, `flagged` event, alert to school admin + real guardians.

**Lost QR code** — guardian reports it, admin revokes + reissues.

## 7. Welfare email system (automated absence alerts)

**Goal**: if a child isn't dropped off (or isn't picked up) on a day they're expected, guardians get an automated email — and ideally school staff see it flagged too, since "child never arrived and nobody knows why" is a safety issue that deserves a human follow-up, not just an email fired into the void.

**Why this needs a "planned absence" concept before it needs an email sender**: without a way for a parent to say "she's sick today, she's not coming in," every legitimate sick day or vacation triggers a false alarm — and a system that cries wolf daily gets ignored, which defeats the purpose. So `ExpectedAbsence` (§3) has to exist and be easy for a parent to set from the app *before* this feature is trustworthy.

**Daily job, per school (respecting each tenant DB and each school's own schedule):**
1. Runs shortly after that school's configured drop-off cutoff time (e.g., 30–60 min after normal start, configurable per school).
2. Skips entirely if `SchoolCalendar` says today isn't a school day.
3. For each active `Student` with no `drop_off` `AttendanceEvent` today and no matching `ExpectedAbsence`: send a welfare email to all linked guardians, and create a flagged item on the staff dashboard.
4. A second pass runs near end-of-day for pickup: any student with a `drop_off` today but no `pick_up` by the school's cutoff → same treatment (this one's arguably more urgent — the child is confirmed on-site with no confirmed release).
5. Log every alert sent (`Notification` row) so it's auditable and doesn't double-send if the job retries.

**Delivery**: transactional email provider (SendGrid, Postgres, or AWS SES) — not the same channel as the push notifications in §5, since welfare alerts need to reach a parent even if they haven't opened the app in weeks and push has gone stale.

**Sensitivity note**: this feature directly touches child safety. False negatives (a genuine no-show that doesn't alert) and false positives (routine alerts training parents to ignore them) are both real failure modes worth testing deliberately — this is not a "ship it and see" feature.

## 8. Parent account & onboarding

**Decision: school-initiated enrollment**, not open self-registration — self-registration would let a stranger claim to be someone's guardian:
1. School staff enrolls a student and the guardian(s), creating the `GuardianStudentLink` from their side (using info the school already collected at enrollment).
2. Staff prints the guardian's QR credential page (name + school name + QR, per §5) directly from the enrollment screen and hands it over physically — this is the primary handoff, not something the parent generates themselves.
3. Parent separately gets an email/SMS invite to activate their `PlatformUser` account (set password / verify), which is what lets them view attendance history and manage notification/absence settings — the printed QR itself doesn't require the parent to ever log in.
4. Once active, the parent's single login surfaces every child linked to them, across every enrolled school (via `GuardianMembership`), each school still producing its own separate printed QR (QR is per guardian *per school*, since scanning always happens against one school's tenant DB).
5. Parent can request additional children be linked — school staff approves, since that's a trust decision the school should own, not the app.

## 9. Backend architecture

- **API**: REST (NestJS or FastAPI). NestJS pairs naturally if you want TypeScript across app+backend.
- **Database**: PostgreSQL — one Platform DB, one Tenant DB per school (§2). A connection-routing layer resolves `school_id` → tenant connection at request time.
- **Auth**: JWT. Parent/staff both authenticate against the Platform DB first (`PlatformUser` / a platform-level staff-login-resolver), then requests carry a resolved `school_id` used to route to the right tenant DB.
- **Push notifications**: Firebase Cloud Messaging.
- **Email**: separate transactional provider from push (§7).
- **Scheduled jobs**: a job runner (e.g., a queue + worker, or cron) iterates all active schools and runs the welfare check per tenant DB — needs to be designed so one school's slow/broken DB connection doesn't stall the others.
- **Offline tolerance for the admin scanner**: cache today's authorized guardian↔student links + revocation list on-device each morning; queue scan writes if offline; sync + reconcile revocations immediately once back online.

## 10. App structure (Flutter)

Single codebase, role-gated:
- **Parent view**: my children (across schools if applicable), QR code per school, attendance history, mark planned absence, notification/email preferences.
- **Staff/Admin view**: scanner, today's roster, flagged-event + welfare-alert review, student/guardian management, request-to-link approvals.
- **Platform/ops view** (likely a separate web console, not the mobile app): school enrollment, subscription status, cross-school metrics.

Suggested packages: `mobile_scanner` for camera QR reading; QR image generation should stay server-side (app just renders whatever the API returns) so the signed token construction never lives on-device.

## 11. MVP scope vs. Phase 2

**MVP**
- School enrollment + tenant DB provisioning (can be a manual/scripted step initially, doesn't need a self-serve signup flow yet).
- Basic subscription gating (even just "active/inactive" before wiring up full Stripe billing).
- Staff login, guardian invite + multi-child linking, QR issuance, scan → attendance log, push notification on scan.
- Welfare email for no-drop-off only (skip the end-of-day no-pickup pass initially), with manual planned-absence marking.
- Basic offline queueing for the scanner.

**Phase 2+**
- Full Stripe billing + self-serve trial signup, live photo-on-scan, anomaly detection, end-of-day no-pickup alerts, temporary pickup delegation, platform ops console, SIS integrations, pickup ETA.

## 12. Suggested next steps
1. Stand up the Platform DB schema + tenant-provisioning script (create DB, run migrations, seed first school admin) — this underlies everything else.
2. Define the API contract (OpenAPI) including the routing layer (`platform user → school_id → tenant connection`).
3. Build signed-QR issuance/validation — still the riskiest piece, now scoped per-school.
4. Build the happy-path scan flow end to end for one school.
5. Add the welfare job once `ExpectedAbsence` and normal attendance logging are solid — it depends on both being trustworthy first.
