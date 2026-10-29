# Source data

Everything here is produced by `simulator/`. **Elvanor** is a fictional new energy vehicle (NEV) brand; the data models the PMO of its international after-sales organisation (15 regional teams across Europe, the Americas, the Middle East and Africa, 8 HQ functions, and the PMO). Staff names come from Faker locales chosen per region plus a small hand-written list; project titles, milestones and update phrases come from the lists in `simulator/company.py` and `simulator/textgen.py`. No records, names or text from a real organisation are used.

The simulator runs one day at a time from 2024-07-01. Delayed decisions (PMO approvals, board votes, evidence reviews, resubmissions, owner hand-overs, hold reviews) are scheduled on an agenda; daily checks move projects through milestones, updates, extensions and closure, and fire the reminder rules. Rates live in `simulator/calibration.py`.

## 1. PMO application database (Postgres or SQLite)

| Table | Grain | Notes for ingestion and modelling |
|---|---|---|
| `teams` | team | `team_group` R (regional) / C (HQ function) / P (PMO); `region`; `meeting_track` front (regional teams) / middle (HQ functions) |
| `people` | person | `role` pmo / manager / member; `board_role` for review-board members; `status` active / departed with `departed_on`. Replacements are new rows |
| `team_managers` | manager assignment | `valid_from` / `valid_to`, so "who managed team X on date D" is answerable (SCD2-style source) |
| `projects` | project | `code` `TEAM-YY-NNN` (strategic `TEAM-YY-ANN`); `legacy_code` `TRKYYYY-NNN` for projects started before the system went live (2025-03-01); `status` not_started / active / on_hold / to_report / closed / canceled; `strategic_level` S/A/B; `original_end` vs `planned_end` and `extension_count`; `owner_name` is free text from the request form; soft delete via `is_deleted` |
| `project_executors` | executor on a project | `person_id` null for external people (agency, importer contact) |
| `milestones` | milestone | `evidence_forms` (text, screenshot, email, file); `status` open / submitted / returned / accepted / dropped; `original_due_date` vs `due_date`. About 60% of projects have a single "Final deliverable" milestone |
| `milestone_submissions` | evidence submission | PMO `review_status` accepted / returned with comment; a returned milestone gets resubmitted |
| `requests` | request version | `kind` new / change / close; `change_types` end, exec, owner; `payload` JSON with what was asked; `status` pending / approved / returned / rejected / pre_approved; a returned request comes back as `version + 1` |
| `board_reviews` | voting round | for strategic requests; `status` voting / approved / revise; `round` increases after a "no" |
| `board_votes` | vote | one per voter per round; a single "no" closes the round |
| `meetings` | project meeting | Thursdays; `track` front in even ISO weeks, middle in odd ISO weeks |
| `status_updates` | bi-weekly update | linked to the meeting it was written for; free-text `body` |
| `follow_ups` | follow-up item | `TEAM-YY-FNN`; types incubate / postclose / monitor; may come from a project (hold converted, post-close) or turn into one |
| `project_events` | change log | created, status, owner, end_date, executors, closed_meeting with old/new values. The basis for status history and SCD2 |
| `emails` | sent email | `rule` R1–R8 or `event`; recipients as person-id lists |

Every table has `created_at` and `updated_at`. `_sim_state` is internal to the simulator and must not be ingested.

### Reminder rules

| Rule | When | To |
|---|---|---|
| R1 | 15 days before a milestone (not the last) | owner + executors |
| R2 | 15 days before the planned end | owner + executors, cc PMO |
| R3 | milestone due date passed, nothing submitted | PMO, cc owner |
| R4 | milestone 7 days overdue | owner + manager, cc PMO |
| R5 | planned end passed with no close or extension request | PMO |
| R6 | 3 days before the team's meeting, no update yet | owner, cc manager |
| R7 | request waiting for the PMO for 3+ days | PMO |
| R8 | board vote open for 3+ days | voters who haven't voted |

These make good test cases for the platform: the risk page and reminder logic built on the warehouse should reproduce them.

## 2. Legacy Excel tracker (`data/excel/PMO_tracker_<year>-W<week>.xlsx`)

The workbook the PMO used before the system, which teams kept updating in parallel. One sheet per team:

| | Regional sheets | HQ sheets |
|---|---|---|
| Sheet name | team name (`Iberia`) | `HQ - ` + team name (`HQ - Bus & Fleet Service`) |
| Header | row 1: `No., Project Code, Project Name, PIC, Status, Start, End, Extensions, Latest update` | row 1 or row 2 under a title row: `#, Ref, Project, Owner, Stage, Start date, Due date, Ext., Comments` |
| Dates | `dd/mm/yyyy` text, `TBD` | real Excel dates or `30.06.2025` text |

Other things to handle:
- Old status vocabulary: `In Progress`, `Ongoing`, `Backlog`, `Pending` (used for both not-started and on-hold), `Close report pending`, `To report`, `Closed`, `Done`, `Canceled`, `Cancelled`, and occasional blanks.
- Projects from before go-live appear under their `TRK` legacy code, not the system code.
- About 20% of rows lag 2–5 weeks behind the system (status from the past, no latest update).
- Projects finished more than 120 days ago are archived off the sheet.
- Stray blank rows and duplicated rows.

## 3. Ground-truth labels (`data/labels/status_updates.jsonl`)

One line per status update, written from the project's hidden state at the time:

```json
{"update_id": 812, "project_id": 77, "as_of": "2025-06-12", "rag": "amber", "stated_rag": "green",
 "risks": [{"category": "customs_logistics", "severity": "medium"}], "blocked": false,
 "next_milestone_date": "2025-07-03", "next_milestone_date_precision": "week"}
```

These labels are never loaded into the warehouse; they are the answer key for evaluating the LLM extractor. `stated_rag` is what the author claimed, so the gap between `stated_rag` and `rag` is measurable optimism. When the text only gives a week (`w/c 30 Jun`, `CW27`), precision is `week` and scoring should allow ±6 days.

Risk categories: `parts_shortage`, `resource_shortage`, `dealer_readiness`, `it_dependency`, `budget`, `regulatory`, `customs_logistics`, `data_quality`, `stakeholder_alignment`, `supplier_delay`.

True RAG rule: **red** if blocked, a high-severity risk, or the next milestone is more than 14 days overdue; **amber** if a medium risk or any overdue; otherwise **green**.
