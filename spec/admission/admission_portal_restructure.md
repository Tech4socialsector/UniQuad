# Admission Portal Restructure — Implementation Plan

Branch: `nlsat-admission-review-changes` · Created: 2026-10-22

Splits the admission website pages (`slcm/www`) into four groups so the folder tells you who a page is for:

| Group | Folder | Who uses it |
|---|---|---|
| Shared by all candidates | `www/admission/` | NLSAT Domestic + NLSAT International + PACE |
| Shared by NLSAT candidates | `www/nlsat/` | NLSAT Domestic + NLSAT International |
| NLSAT Domestic only | `www/nlsatadmissions/` | Indian Nationals |
| NLSAT International only | `www/nlsat-international/` | International candidates |
| PACE only | `www/paceadmissions/` | PACE candidates |
| Application form (unchanged) | `www/application_form/` | NLSAT Domestic + International |

**Rule for shared (`www/admission/`) pages:** they are never opened by their folder path. Each one gets
a candidate-prefixed URL through a route rule, so the URL says whose page it is:

- NLSAT candidate → `/nlsat/my-profile`, `/nlsat/helpdesk`, `/nlsat/announcement/<name>`
- PACE candidate → `/pace/my-profile`, `/pace/helpdesk`, `/pace/announcement/<name>`

Both prefixes render the same file. Links inside the shared layout, navbar and sidebar pick the prefix
from the candidate (see step 3.2).

---

## 1. Target file structure

```
slcm/www/
│
├── admission/                           ← shared by NLSAT DOM + NLSAT INTL + PACE (never addressed directly)
│   ├── __init__.py
│   ├── admission_base.html / .py            layout (includes navbar + footer; .py returns 404 on direct URL)
│   ├── _navbar.html / _navbar.py            navbar + mobile drawer      (.py: context fn + 404 on direct URL)
│   ├── _footer.html / _footer.py            footer                      (.py: context fn + 404 on direct URL)
│   ├── _sidebar.html / _sidebar.py          sidebar macros              (.py: context fn + 404 on direct URL)
│   ├── profile.html / profile.py            → /nlsat/my-profile            · /pace/my-profile
│   ├── helpdesk.html / helpdesk.py          → /nlsat/helpdesk              · /pace/helpdesk
│   └── announcement/
│       ├── __init__.py
│       └── announcement_detail.html / .py   → /nlsat/announcement/<name>   · /pace/announcement/<name>
│
├── nlsat/                               ← shared by NLSAT DOM + NLSAT INTL (Applicant role)
│   ├── __init__.py
│   ├── dashboard.html / .py                 → /nlsat/dashboard              (was merit-and-scholarship/admission_dashboard)
│   ├── scholarships/
│   │   ├── index.html / .py                 → /nlsat/scholarships           (was merit-and-scholarship/scholarships)
│   │   └── apply.html / .py                 → /nlsat/scholarships/apply     (was merit-and-scholarship/apply)
│   ├── my-applications/
│   │   ├── __init__.py
│   │   └── index.html / .py                 → /nlsat/my-applications
│   ├── view_application/
│   │   └── index.html / .py                 → /nlsat/view_application
│   ├── offer_letter/
│   │   ├── offer-letter-list.html / .py     → /nlsat/offer_letter/offer-letter-list
│   │   ├── offer-letter-detail.html / .py   → /nlsat/offer_letter/offer-letter-detail
│   │   └── cancellation_form.html           → /nlsat/offer_letter/cancellation_form
│   ├── eligibility/                         (API modules — paths stay slcm.www.nlsat.eligibility.*)
│   │   ├── entrance_test_seat_allocation.html / .py
│   │   └── interview_management.html / .py
│   └── application-status.html / .py       → /nlsat/application-status    (was www/admission-status)
│
├── nlsatadmissions/                     ← NLSAT Domestic only
│   ├── index.html / .py                     → /nlsatadmissions
│   ├── login.html / .py                     → /nlsatadmissions/login
│   └── program_detail.html / .py            → /nlsatadmissions/<slug>
│
├── nlsat-international/                 ← NLSAT International only
│   ├── index.html / .py                     → /nlsat-international
│   ├── login.html / .py                     → /nlsat-international/login
│   └── program_detail.html / .py            → /nlsat-international/<slug>
│
├── paceadmissions/                      ← PACE only
│   ├── index.html / .py                     → /paceadmissions/admission          (route rule)
│   ├── pace_programme_details.html / .py    → /paceadmissions/admission/<name>   (route rule)
│   ├── login.html / .py  (+ css/login.css)  → /paceadmissions/login
│   ├── forgot_password.html                 → /paceadmissions/forgot_password
│   ├── update_password.html                 → /paceadmissions/update_password
│   ├── application-card/
│   │   └── index.html / .py                 → /paceadmissions/application-card   (was www/pace_application_card)
│   └── progress-tracker/
│       └── index.html / .py                 → /paceadmissions/progress-tracker   (was www/pace_progress_tracker)
│
└── application_form/                    ← NLSAT DOM + INTL — NOT moved (route + API paths unchanged)
    ├── index.html / .py                     → /application_form
    └── start/index.html / .py               → /application_form/start
```

---

## 2. Route map (final)

### 2.1 Shared by all candidates (`www/admission/`) — route rules

| URL (NLSAT) | URL (PACE) | `to_route` |
|---|---|---|
| `/nlsat/my-profile` | `/pace/my-profile` | `admission/profile` |
| `/nlsat/helpdesk` | `/pace/helpdesk` | `admission/helpdesk` |
| `/nlsat/announcement/<name>` | `/pace/announcement/<name>` | `admission/announcement/announcement_detail` |

### 2.2 Shared by NLSAT candidates (`www/nlsat/`) — folder routes

| URL | File |
|---|---|
| `/nlsat/dashboard` | `nlsat/dashboard` |
| `/nlsat/scholarships` | `nlsat/scholarships/index` |
| `/nlsat/scholarships/apply` | `nlsat/scholarships/apply` |
| `/nlsat/my-applications` | `nlsat/my-applications/index` |
| `/nlsat/view_application` | `nlsat/view_application/index` |
| `/nlsat/offer_letter/offer-letter-list` · `-detail` · `cancellation_form` | `nlsat/offer_letter/*` |
| `/nlsat/eligibility/entrance_test_seat_allocation` · `interview_management` | `nlsat/eligibility/*` |
| `/nlsat/application-status` | `nlsat/application-status` |
| `/application_form` · `/application_form/start` | `application_form/*` (unchanged) |

### 2.3 Portal-only

| URL | File | Portal |
|---|---|---|
| `/nlsatadmissions` · `/nlsatadmissions/login` · `/nlsatadmissions/<slug>` | `nlsatadmissions/*` | DOM |
| `/nlsat-international` · `/nlsat-international/login` · `/nlsat-international/<slug>` | `nlsat-international/*` | INTL |
| `/paceadmissions/admission` · `/paceadmissions/admission/<name>` | `paceadmissions/index`, `pace_programme_details` | PACE |
| `/paceadmissions/login` · `/forgot_password` · `/update_password` | `paceadmissions/*` | PACE |
| `/paceadmissions/application-card` | `paceadmissions/application-card/index` | PACE |
| `/paceadmissions/progress-tracker` | `paceadmissions/progress-tracker/index` | PACE |

### 2.4 Legacy URLs → redirects (`website_redirects`, 301, query string forwarded)

| Old URL | New URL |
|---|---|
| `/nlsat/profile`, `/my-profile` | `/nlsat/my-profile` |
| `/nlsat/merit-and-scholarship/helpdesk`, `/merit-and-scholarship/helpdesk` | `/nlsat/helpdesk` |
| `/nlsat/merit-and-scholarship/admission_dashboard`, `/merit-and-scholarship/admission_dashboard`, `/admission-dashboard`, `/applicant-dashboard` | `/nlsat/dashboard` |
| `/nlsat/merit-and-scholarship/scholarships`, `/merit-and-scholarship/scholarships` | `/nlsat/scholarships` |
| `/nlsat/merit-and-scholarship/apply`, `/merit-and-scholarship/apply`, `/apply` | `/nlsat/scholarships/apply` |
| `/announcement/<name>` | `/nlsat/announcement/<name>` |
| `/admission-status` | `/nlsat/application-status` |
| `/pace_application_card` | `/paceadmissions/application-card` |
| `/pace_progress_tracker`, `/pace/progress-tracker` | `/paceadmissions/progress-tracker` |
| `/pace/admission`, `/pace/admission/<name>` | `/paceadmissions/admission`, `/paceadmissions/admission/<name>` |
| `/pace/login`, `/pace/forgot_password` | `/paceadmissions/login`, `/paceadmissions/forgot_password` |
| `/admission`, `/admission/<anything>` | `/nlsatadmissions`, `/nlsatadmissions/<anything>` (already exists — keep) |
| `/my-applications`, `/offer_letter/*`, `/view_application`, `/eligibility/*` | `/nlsat/...` (already exist — keep) |

> **Note — `/admission/...` and the new `www/admission/` folder.** The existing redirect
> `/admission/(.*) → /nlsatadmissions/\1` keeps old emailed links working. It also means the shared
> folder can't be opened by its folder path (`/admission/profile`), which is what we want: shared pages
> are only reached through `/nlsat/...` and `/pace/...` route rules. Redirects only check the incoming
> URL, so they don't affect the route rules.

---

## 3. Implementation steps

Tick each box when done. Keep commits per phase so each phase can be reverted on its own.

### Phase 1 — Shared folder `www/admission/`

- [x] 1.1 `git mv www/nlsat/admission_base.html|.py` → `www/admission/`
- [x] 1.2 `git mv www/nlsat/_navbar.*`, `_footer.*`, `_sidebar.*` → `www/admission/`
- [x] 1.3 `git mv www/nlsat/profile.html|.py` → `www/admission/profile.*`
- [x] 1.4 `git mv www/nlsat/merit-and-scholarship/helpdesk.*` → `www/admission/helpdesk.*`
- [x] 1.5 `git mv www/nlsat/announcement/` → `www/admission/announcement/`
- [x] 1.6 Add `www/admission/__init__.py`
- [x] 1.7 `hooks.py` → `jinja.methods`: `slcm.www.nlsat._navbar/_footer/_sidebar.*` → `slcm.www.admission.*`
- [x] 1.8 Every `{% extends "slcm/www/nlsat/admission_base.html" %}` → `slcm/www/admission/admission_base.html`
      (NLSAT pages, PACE pages, `application_form`, `admission-status`)
- [x] 1.9 Every `{% from "slcm/www/nlsat/_sidebar.html" import … %}` → `slcm/www/admission/_sidebar.html`
- [x] 1.10 Layout `{% include %}` paths for `_navbar.html` / `_footer.html` → `slcm/www/admission/`

### Phase 2 — NLSAT shared folder clean-up `www/nlsat/`

- [x] 2.1 `git mv nlsat/merit-and-scholarship/admission_dashboard.*` → `nlsat/dashboard.*`
- [x] 2.2 `git mv nlsat/merit-and-scholarship/scholarships.*` → `nlsat/scholarships/index.*`
- [x] 2.3 `git mv nlsat/merit-and-scholarship/apply.*` → `nlsat/scholarships/apply.*`
- [x] 2.4 Remove the now-empty `nlsat/merit-and-scholarship/`
- [x] 2.5 `git mv www/admission-status.html|.py` → `nlsat/application-status.*`
- [x] 2.6 Check `nlsat/eligibility/*` is untouched (its API paths `slcm.www.nlsat.eligibility.*` must not change)

### Phase 3 — Candidate-prefixed routes for shared pages

- [x] 3.1 `hooks.py` → `website_route_rules`: add the six rules in §2.1; remove `/my-profile → nlsat/profile`
      and `/pace/helpdesk → nlsat/merit-and-scholarship/helpdesk`
- [x] 3.2 Helper `get_candidate_prefix()` in `slcm/admission/utils/nlsat_portal.py`:
      `"/pace"` on PACE pages (`/pace…`, `/paceadmissions…`) or for PACE-only users, otherwise `"/nlsat"`
- [x] 3.3 `_navbar.py`: `profile_url` / `helpdesk_url` built from the prefix
- [x] 3.4 `_sidebar.py`: `urls.profile` / `urls.helpdesk` built from the prefix
- [x] 3.5 Layout JS: announcement links `/nlsat/announcement/` → `<prefix>/announcement/`
- [x] 3.6 `profile.py`, `helpdesk.py`: login redirect for guests — `/pace/...` → `/paceadmissions/login`,
      `/nlsat/...` → NLSAT login (cookie / applicant category, as today)

### Phase 4 — PACE folder `www/paceadmissions/`

- [x] 4.1 `git mv www/pace_application_card/` → `www/paceadmissions/application-card/`
- [x] 4.2 `git mv www/pace_progress_tracker/` → `www/paceadmissions/progress-tracker/`
- [x] 4.3 `hooks.py`: remove the `/paceadmissions/application-card` and `/paceadmissions/progress-tracker` route
      rules (the folder now serves them); remove dead `/pace/admission`, `/pace/admission/<name>`,
      `/pace/login`, `/pace/forgot_password`, `/pace/progress-tracker` rules (`www/pace/` doesn't exist);
      remove the duplicate `/paceadmissions/forgot_password` rule
- [x] 4.4 Delete `www/paceadmissions/login.py.bak`
- [x] 4.5 Check PACE-side dotted API paths (`slcm.www.pace_application_card.*` / `slcm.www.pace_progress_tracker.*`)
      — update callers if any exist

### Phase 5 — References & redirects

- [x] 5.1 `hooks.py` → `website_redirects`: add every row of §2.4
- [x] 5.2 Remove the `/admission-dashboard` and `/apply` route rules (now redirects); remove `/applicant-dashboard`
      route rule (target `applicant_dashboard` doesn't exist)
- [x] 5.3 Rewrite links across the codebase:

      | Find | Replace |
      |---|---|
      | `/nlsat/profile` | candidate prefix + `/my-profile` (code) · `/nlsat/my-profile` (NLSAT-only places) · `/pace/my-profile` (PACE login/web form) |
      | `/nlsat/merit-and-scholarship/helpdesk` | `<prefix>/helpdesk` |
      | `/nlsat/merit-and-scholarship/admission_dashboard` | `/nlsat/dashboard` |
      | `/nlsat/merit-and-scholarship/scholarships` | `/nlsat/scholarships` |
      | `/nlsat/merit-and-scholarship/apply` | `/nlsat/scholarships/apply` |
      | `/admission-status` | `/nlsat/application-status` |
      | `/nlsat/announcement/` | `<prefix>/announcement/` |

      Places to cover: `www/**`, `slcm/admission/**` (notification_service, applicant, merit list, seat allocation,
      interview/entrance test doctypes, utils), `slcm/api/user.py`, `slcm/pace/**` (PACE web form JS, PACE emails),
      `applicant_form.js`, `public/js/stage_tracker.js`, email-template fixtures, tests
- [x] 5.4 PACE web form (`pace_application_form.js`): dashboard link → `/pace/my-profile`
- [x] 5.5 PACE login (`paceadmissions/login.*`, `update_password.html`, `api/user.py` PACE functions):
      post-login landing → `/pace/my-profile`
- [x] 5.6 NLSAT logins: post-login landing → `/nlsat/my-profile`
- [x] 5.7 Do **not** touch: applicant web form route/success URL, `www/application_form` paths & API names

### Phase 6 — Verify (local site `slcm.com`)

- [x] 6.1 `py_compile` all changed `.py`; Jinja-parse all changed templates; `node --check applicant_form.js`
- [x] 6.2 `bench --site slcm.com clear-cache && bench --site slcm.com clear-website-cache`
- [x] 6.3 Guest checks: every URL in §2 returns 200 or a redirect to the right login; partials and
      `admission/admission_base` return 404
- [x] 6.4 Every old URL in §2.4 returns 301 to the new URL (query string kept)
- [x] 6.5 Logged-in checks (Domestic applicant, International applicant, PACE applicant): every page in §2
      renders with navbar + sidebar + footer and no server error
- [x] 6.6 Prefix checks: NLSAT user's navbar/sidebar link to `/nlsat/my-profile`, `/nlsat/helpdesk`;
      PACE user's link to `/pace/my-profile`, `/pace/helpdesk`
- [x] 6.7 Logout lands on the right login (Domestic / International / PACE)
- [x] 6.8 `git grep` finds no remaining `nlsat/merit-and-scholarship`, `www/nlsat/admission_base`,
      `nlsat/_sidebar`, `nlsat/profile`, `pace_application_card/`, `pace_progress_tracker/` references
      (except redirect sources in `hooks.py`)

### Phase 7 — Deploy notes

- [ ] 7.1 `bench migrate` (runs existing patches), then `bench clear-cache` + `bench clear-website-cache`
- [ ] 7.2 Website redirects are cached — clear the cache or old URLs keep the old routing

---

## 4. Known issues found in the audit (not part of this move unless noted)

| # | Issue | Handled in |
|---|---|---|
| 1 | `/pace/admission`, `/pace/login`, `/pace/forgot_password` route to a missing `www/pace/` | Phase 4.3 + 5.1 (redirects) |
| 2 | `/applicant-dashboard` routes to a missing `applicant_dashboard` | Phase 5.2 (redirect) |
| 3 | Duplicate `/paceadmissions/forgot_password` route rule | Phase 4.3 |
| 4 | PACE web form links to the NLSAT dashboard; PACE-only users bounce to profile | Phase 5.4 |
| 5 | `/admission-status` returns 500 when no applicant matches (`'applicant' is undefined`) | Not fixed — moved as is; separate fix |
| 6 | `www/paceadmissions/login.py.bak` leftover | Phase 4.4 |
| 7 | `nlsat/my-applications` has its own older "My Profile" tab (`?tab=profile`) | Not changed — decide separately |

## 5. Progress log

| Date | Phase | Notes |
|---|---|---|
| 2026-10-22 | Plan | Plan written |
| 2026-10-22 | 1–5 | Files moved (git renames); `get_candidate_prefix()` / `get_candidate_login_url()` added to `nlsat_portal.py`; navbar, sidebar, layout JS, profile and helpdesk use the prefix; PACE logins / web form / `api/user.py` PACE paths land on `/pace/my-profile`; `hooks.py` route rules + redirects updated; dead `/pace/*`, `/applicant-dashboard` rules and duplicate forgot-password rule removed; `paceadmissions/login.py.bak` deleted |
| 2026-10-22 | 6 | Verified on `slcm.com`: 35 templates parse, all `.py` compile, no stale references. Guest: every route correct, legacy URLs 301 with query kept. Logged in as Domestic, International and a temporary PACE-only user (deleted afterwards): every shared page renders with navbar + sidebar + footer; NLSAT links use `/nlsat/...`, PACE links use `/pace/...`; PACE user on `/nlsat/dashboard` → `/pace/my-profile`. Known, unchanged: `/nlsat/application-status` 500 (issue 5); `/paceadmissions/admission` 404 locally because *Enable PACE Site* is off |
| — | 7 | Pending: run on the server at deploy time |
