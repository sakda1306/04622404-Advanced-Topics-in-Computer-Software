# Salary reference table

`reference.csv` is the hand-curated reference layer of the salary view (PRD FR-21, Design.md section 7). It is labelled team-curated in the UI and is shown next to, never merged with, the advertised ranges from the job postings.

## Columns

| column | meaning |
|---|---|
| `role_id` | id from `data/roles.json` |
| `min`, `max` | THB per month |
| `measure` | always `monthly_base` (base monthly salary) |
| `level` | `entry` (starting salary) or `junior`, as the source states it |
| `match` | `exact`: the source names this role; `proxy`: the source names a closely related role, see `note` |
| `source`, `url`, `file` | publisher, article URL, saved copy in `pdf/` |
| `published_at`, `retrieved_at` | article date and the date the copy was saved |
| `note` | which source title was used, and the other sources' figures for the same role |

## Sources

| file | publisher | published | what it gives |
|---|---|---|---|
| `pdf/27-jobsdb-tech-starting-salary-guide.pdf` | Jobsdb ไทย (job board) | 8 Jun 2026 | starting base salary for 10 role groups |
| `pdf/28-x10-it-salary-update-2026.pdf` | X10 IT Outsource (IT recruiter) | 2 Feb 2026 | junior, mid and senior ranges for 6 roles |
| `pdf/29-spu-it-careers-2026.pdf` (local only) | Faculty of IT, Sripatum University | 19 Mar 2026 | starting income for 10 trending roles |

File 29 is 9.6 MB, over the 5 MB limit for committed files (GIT_FLOW.md section 4, rule 3), so it is kept on the author's machine only; cite it by its URL.

A second copy of the Jobsdb article (saved 1 Nov 2026) has the same content as file 27, so it is not committed.

## How duplicates were resolved

Several roles appear in more than one source. One row per role, chosen in this order:

1. **Jobsdb** first: a job board, explicitly "starting base salary", and it covers the most roles.
2. **X10** next: explicit junior ranges from a recruiter.
3. **SPU** last: a university promotional article whose figures run high; used only when no other source gives a range with a maximum (Data Scientist).

Entry or junior level is used for every row, because 23 of the 26 roles are `career_stage: entry` and the main users are fresh graduates. Mid and senior figures are kept in `note` where the source gives them.

## Coverage

18 of 26 roles have a row (15 exact, 3 proxy). No source gives a figure for these 8 roles, so their reference layer is empty (`reference: null` in the API) and the view shows the advertised layer and the NSO baseline only:

`mobile-developer`, `computer-engineer`, `data-architect`, `database-administrator`, `network-administrator`, `systems-administrator`, `it-project-manager`, `it-consultant`.

Roles in the sources that are not in `data/roles.json` (Blockchain Developer, IoT Specialist, Prompt Engineer, Game Developer, CTO and other executives) are not used.
