"""Tunable rates and distributions.

Values were chosen so the generated portfolio behaves like a busy international
after-sales PMO: most projects run between two months and a year, a good
share get extended, roughly a third of finished projects end up canceled
rather than closed, most projects have a single final deliverable, and
updates are often late or missing. Change them here, not in the engine.
"""

# new-project requests per working day across the whole organisation
PROPOSALS_PER_WEEKDAY = 0.75
PMO_DIRECT_SHARE = 0.12  # projects the PMO sets up itself, without a request
STRATEGIC_SHARE = 0.08  # requests that go to the review board
STRATEGIC_LEVEL_WEIGHTS = {"S": 0.15, "A": 0.45, "B": 0.40}
PLANNING_PENDING_SHARE = 0.06  # approved without dates; planned weeks later

# planned duration in days: piecewise-uniform between these deciles
DURATION_DECILES = [30, 61, 99, 121, 154, 196, 259, 305, 395, 566, 900]
MILESTONE_COUNT_WEIGHTS = {1: 62, 2: 9, 3: 12, 4: 8, 5: 3, 6: 5}
EXECUTOR_COUNT_WEIGHTS = {0: 5, 1: 70, 2: 12, 3: 4, 4: 5, 5: 2, 6: 2}
EXTERNAL_EXECUTOR_SHARE = 0.08
CROSS_TEAM_EXECUTOR_SHARE = 0.15

# PMO decisions on requests: (approve, return, reject)
NEW_REQUEST_DECISION = (0.74, 0.16, 0.10)
CHANGE_REQUEST_DECISION = (0.85, 0.10, 0.05)
CLOSE_REQUEST_DECISION = (0.90, 0.10, 0.0)
RESUBMIT_AFTER_RETURN = 0.8
PMO_DECISION_DAYS = (1, 8)

BOARD_YES = 0.93
BOARD_VOTE_DAYS = (1, 12)
BOARD_RESUBMIT_DAYS = (7, 25)

# milestone evidence
EVIDENCE_ACCEPT = 0.88
EVIDENCE_REVIEW_DAYS = (1, 5)
EVIDENCE_RESUBMIT_DAYS = (3, 12)

CLOSE_AT_MEETING = 0.85  # close reviewed at the project meeting: approved vs sent back
CLOSE_REVIEWS_PER_MEETING = 2  # agenda time is short, so pre-approved closes queue up
OWNER_READY_TO_PRESENT = 0.6
HOLD_PER_DAY = 0.0028
HOLD_REVIEW_DAYS = (60, 260)
HOLD_OUTCOME = {"resume": 0.3, "cancel": 0.5, "follow_up": 0.2}
STALE_CANCEL_AFTER_DAYS = 45  # past planned end with no request: PMO may cancel
STALE_CANCEL_PER_DAY = 0.008

DEPARTURE_PER_DAY = 0.04
REPLACE_MEMBER = 0.5
OWNER_REASSIGN_DAYS = (10, 70)

FOLLOW_UPS_PER_WEEKDAY = 0.08
POSTCLOSE_FOLLOW_UP_SHARE = 0.2

REMINDER_LEAD_DAYS = 15  # R1 / R2
BIWEEKLY_REMINDER_DAYS_BEFORE = 3  # R6
SYSTEM_GO_LIVE = "2025-03-01"  # projects created before this get a legacy tracker code
