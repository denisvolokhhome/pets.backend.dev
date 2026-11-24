# Litter applications, heat cycles and the breeder calendar

## Litter applications

A breeding's existing **application form** (`breeding_application_forms`, one per breeding) is reused for two entry points:

| Source | Where the family applies | Needs |
|---|---|---|
| `litter` | Public litter page `/litter/:id` → "Apply for this litter" | form exists **and** `accepting_litter_applications = true` **and** the litter is public |
| `offspring` | Existing puppy page → "Apply for Offspring" (still continues to a prefilled message) | form exists and the puppy is published / not archived |

"Public" = breeding not `Voided`, `is_active`, breeder account active. Submissions are rejected (404/409) otherwise. Closing applications (`accepting_litter_applications = false`) stops new litter submissions only; past ones stay.

Each submission is a `litter_applications` row: `breeding_id`, `breeder_id`, `applicant_id` (+ name/email snapshot), `source`, `requested_offspring_id` (puppy page context, not an assignment), `answers` (snapshot `[{field_id,label,value}]`, so later form edits never change what was written), `status`, `assigned_offspring_id`.

Statuses: `new` → `contacted` / `waitlisted` / `declined` (set by hand), `assigned` (only via assign). One open (non-declined) application per family per litter (per puppy for the puppy flow), enforced by a check plus the partial unique index `uq_litter_applications_open_per_applicant`.

### Puppy assignment

`services/offspring_reservation.py` is shared with the waitlist's `match`:

- `reserve_offspring` is one conditional `UPDATE offsprings SET status='Reserved' WHERE status='Available' AND <no holder>`; a holder is an `assigned` litter application or a `matched` waitlist entry. Under concurrency Postgres re-checks the WHERE after the first commit, so only one request wins (see `test_simultaneous_assignments_only_one_wins`).
- `release_offspring` (undo) returns the puppy to `Available` only if it is still `Reserved` and nobody else holds it.
- The application (or waitlist entry) row is locked `FOR UPDATE` first, so one application can't take two puppies.
- Backstop: partial unique index `uq_litter_applications_assigned_offspring` (one assigned application per puppy).

Undo returns the application to `waitlisted` with its answers intact.

### Endpoints

| Method | Path | Who |
|---|---|---|
| GET | `/api/breedings/public/{id}` | public — litter page data |
| POST | `/api/breedings/public/{id}/applications` `{answers, offspring_id?}` | signed-in family |
| PUT | `/api/breedings/{id}/application-form/litter-applications` `{accepting_litter_applications}` | litter owner |
| GET | `/api/breedings/{id}/applications?status=` | litter owner |
| GET | `/api/applications/{id}` | litter owner |
| PATCH | `/api/applications/{id}/status` `{status}` | litter owner |
| POST | `/api/applications/{id}/assign` `{offspring_id}` / `.../unassign` | litter owner |

Other accounts get 404. A new submission sends the breeder an in-app notification (`type`/`related_type` = `litter_application`).

## Heat cycles, reminders, calendar

- `heat_cycles`: `pet_id`, `user_id`, `start_date` (required), `end_date` (NULL = in progress), `notes`. `Date` columns (calendar dates, no time zone). DB check `end_date >= start_date`; partial unique index allows one open cycle per dog. Female pets only (male → 422).
- `breeder_reminders`: `pet_id`, `user_id`, `remind_on`, `note`. Calendar only — no email/push in v1.
- All rows are private to the breeder (`require_breeder` + ownership; other accounts get 404).

| Method | Path |
|---|---|
| GET/POST | `/api/pets/{pet_id}/heat-cycles` |
| PUT/DELETE | `/api/heat-cycles/{id}` |
| GET/POST | `/api/pets/{pet_id}/reminders` |
| PUT/DELETE | `/api/reminders/{id}` |
| GET | `/api/calendar?start&end[&pet_id]` (≤120 days) → `pets`, `events` (heat_start / heat_end / reminder inside the range), `in_heat` (every cycle overlapping the range, incl. ones that started earlier) |

Heat History (dog modal on Pets) and the Calendar page read and write the same rows.
