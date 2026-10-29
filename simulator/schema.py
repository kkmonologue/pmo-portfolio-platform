"""Tables of the fictional PMO application (the ETL source).

The model follows how an after-sales PMO actually runs its portfolio: teams
report at two alternating bi-weekly project meetings (front office and middle office), projects are
requested and approved, milestones need evidence that the PMO accepts or
returns, changes and closures go through requests, strategic projects need a
unanimous board vote, and the system sends reminder emails.

Every table carries ``updated_at`` (or is append-only with ``created_at``) so
the ingestion layer can load incrementally. Projects are soft-deleted.
"""

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, MetaData, String, Table, Text

metadata = MetaData()


def _audit():
    return [Column("created_at", DateTime, nullable=False), Column("updated_at", DateTime, nullable=False)]


teams = Table(
    "teams",
    metadata,
    Column("team_id", Integer, primary_key=True),
    Column("code", String(8), nullable=False),
    Column("name_en", String(80), nullable=False),
    Column("team_group", String(1), nullable=False),  # R regional (front office) | C HQ function (middle office) | P PMO
    Column("region", String(16), nullable=False),  # Europe | Americas | Middle East | Africa | HQ
    Column("meeting_track", String(8), nullable=False),  # front | middle: which bi-weekly project meeting the team reports at
    *_audit(),
)

people = Table(
    "people",
    metadata,
    Column("person_id", Integer, primary_key=True),
    Column("display_name", String(120), nullable=False),
    Column("email", String(160), nullable=False),
    Column("home_team_id", Integer),
    Column("role", String(12), nullable=False),  # pmo | manager | member | viewer
    Column("job_title", String(80)),
    Column("board_role", String(12)),  # steering | execution | advisor | secretariat; null if not on the review board
    Column("status", String(10), nullable=False),  # active | departed
    Column("departed_on", Date),
    *_audit(),
)

team_managers = Table(
    "team_managers",
    metadata,
    Column("team_manager_id", Integer, primary_key=True),
    Column("team_id", Integer, nullable=False),
    Column("person_id", Integer, nullable=False),
    Column("section", String(40)),  # set when the manager only covers one section of the team
    Column("valid_from", Date, nullable=False),
    Column("valid_to", Date),
    *_audit(),
)

projects = Table(
    "projects",
    metadata,
    Column("project_id", Integer, primary_key=True),
    Column("code", String(20), nullable=False),  # TEAM-YY-NNN, strategic TEAM-YY-ANN
    Column("legacy_code", String(20)),  # TRKYYYY-NNN from the old Excel tracker, for projects started before the system
    Column("team_id", Integer, nullable=False),
    Column("section", String(40)),
    Column("title", String(200), nullable=False),
    Column("scope", Text),
    Column("owner_id", Integer),
    Column("owner_name", String(120)),  # as typed on the request form
    Column("status", String(12), nullable=False),  # not_started | active | on_hold | to_report | closed | canceled
    Column("strategic_level", String(1)),  # S | A | B, null for normal projects
    Column("start_date", Date),
    Column("planned_end", Date),
    Column("original_end", Date),
    Column("actual_end", Date),
    Column("extension_count", Integer, nullable=False),
    Column("is_deleted", Boolean, nullable=False),
    *_audit(),
)

project_executors = Table(
    "project_executors",
    metadata,
    Column("executor_id", Integer, primary_key=True),
    Column("project_id", Integer, nullable=False),
    Column("person_id", Integer),
    Column("executor_name", String(120)),  # free text; external people have no person_id
    Column("removed", Boolean, nullable=False),
    *_audit(),
)

milestones = Table(
    "milestones",
    metadata,
    Column("milestone_id", Integer, primary_key=True),
    Column("project_id", Integer, nullable=False),
    Column("seq", Integer, nullable=False),
    Column("name", String(120), nullable=False),
    Column("evidence_forms", String(60)),  # comma list: text,screenshot,email,file
    Column("original_due_date", Date, nullable=False),
    Column("due_date", Date, nullable=False),
    Column("status", String(10), nullable=False),  # open | submitted | returned | accepted | dropped
    Column("accepted_on", Date),
    *_audit(),
)

milestone_submissions = Table(
    "milestone_submissions",
    metadata,
    Column("submission_id", Integer, primary_key=True),
    Column("milestone_id", Integer, nullable=False),
    Column("submitted_by", Integer),
    Column("submitted_at", DateTime, nullable=False),
    Column("form", String(12)),
    Column("note", Text),
    Column("attachment_name", String(120)),
    Column("review_status", String(10), nullable=False),  # pending | accepted | returned
    Column("reviewed_by", Integer),
    Column("reviewed_at", DateTime),
    Column("review_comment", Text),
    *_audit(),
)

requests = Table(
    "requests",
    metadata,
    Column("request_id", Integer, primary_key=True),
    Column("kind", String(8), nullable=False),  # new | change | close
    Column("project_id", Integer),  # null for a new-project request until approved
    Column("team_id", Integer, nullable=False),
    Column("change_types", String(40)),  # for kind=change: comma list of end,exec,plan,owner
    Column("payload", Text, nullable=False),  # JSON: what was requested
    Column("reason", Text),
    Column("submitted_by", Integer, nullable=False),
    Column("submitted_at", DateTime, nullable=False),
    Column("version", Integer, nullable=False),  # a returned request is resubmitted as version + 1
    Column("status", String(12), nullable=False),  # pending | approved | returned | rejected | pre_approved (close)
    Column("decided_by", Integer),
    Column("decided_at", DateTime),
    Column("decision_comment", Text),
    *_audit(),
)

board_reviews = Table(
    "board_reviews",
    metadata,
    Column("review_id", Integer, primary_key=True),
    Column("request_id", Integer, nullable=False),
    Column("level", String(1), nullable=False),
    Column("round", Integer, nullable=False),
    Column("sent_at", DateTime, nullable=False),
    Column("status", String(8), nullable=False),  # voting | approved | revise
    Column("closed_at", DateTime),
    *_audit(),
)

board_votes = Table(
    "board_votes",
    metadata,
    Column("vote_id", Integer, primary_key=True),
    Column("review_id", Integer, nullable=False),
    Column("person_id", Integer, nullable=False),
    Column("vote", String(3), nullable=False),  # yes | no
    Column("comment", Text),
    Column("voted_at", DateTime, nullable=False),
    *_audit(),
)

meetings = Table(
    "meetings",
    metadata,
    Column("meeting_id", Integer, primary_key=True),
    Column("meeting_date", Date, nullable=False),
    Column("track", String(8), nullable=False),  # front | middle, alternating weeks
    *_audit(),
)

status_updates = Table(
    "status_updates",
    metadata,
    Column("update_id", Integer, primary_key=True),
    Column("project_id", Integer, nullable=False),
    Column("meeting_id", Integer),  # the meeting the update was written for
    Column("author_id", Integer),
    Column("posted_at", DateTime, nullable=False),
    Column("body", Text, nullable=False),
    *_audit(),
)

follow_ups = Table(
    "follow_ups",
    metadata,
    Column("follow_up_id", Integer, primary_key=True),
    Column("code", String(20), nullable=False),  # TEAM-YY-FNN
    Column("team_id", Integer, nullable=False),
    Column("follow_up_type", String(10), nullable=False),  # incubate | postclose | monitor
    Column("title", String(200), nullable=False),
    Column("owner_id", Integer),
    Column("source_project_id", Integer),
    Column("converted_project_id", Integer),
    Column("status", String(8), nullable=False),  # open | closed
    Column("closed_on", Date),
    *_audit(),
)

project_events = Table(
    "project_events",
    metadata,
    Column("event_id", Integer, primary_key=True),
    Column("project_id", Integer, nullable=False),
    Column("event_at", DateTime, nullable=False),
    Column("actor_id", Integer),
    Column("event_type", String(16), nullable=False),  # created | status | owner | end_date | executors | closed_meeting
    Column("old_value", String(120)),
    Column("new_value", String(120)),
    Column("note", Text),
    *_audit(),
)

emails = Table(
    "emails",
    metadata,
    Column("email_id", Integer, primary_key=True),
    Column("rule", String(8), nullable=False),  # R1..R8 reminder rules, or event / manual
    Column("project_id", Integer),
    Column("to_ids", String(200)),
    Column("cc_ids", String(200)),
    Column("subject", String(240), nullable=False),
    Column("body", Text),
    Column("sent_at", DateTime, nullable=False),
    *_audit(),
)

# Internal simulator bookkeeping; not part of the "application" and excluded from ingestion.
sim_state = Table("_sim_state", metadata, Column("key", String(32), primary_key=True), Column("value", Text, nullable=False))

SOURCE_TABLES = [
    teams,
    people,
    team_managers,
    projects,
    project_executors,
    milestones,
    milestone_submissions,
    requests,
    board_reviews,
    board_votes,
    meetings,
    status_updates,
    follow_ups,
    project_events,
    emails,
]
