"""The fictional company the whole platform is built around.

Elvanor is a made-up new energy vehicle (NEV) brand: battery-electric,
plug-in hybrid and fuel-cell cars, buses and vans. This repository models the PMO of its
international after-sales organisation: front-office teams in the markets
(Europe, the Americas, the Middle East and Africa) and middle-office
functions at the after-sales headquarters. Every team, person, project and
update is generated from the lists below and a random seed.
"""

COMPANY = {
    "name": "Elvanor (fictional)",
    "org": "Elvanor International After-sales",
    "pmo": "After-sales Project Management Office",
    "hq": "Rotterdam, NL",
    "email_domain": "elvanor.example",
}

# group R = regional after-sales team (front office), reports at the front-office project meeting
# group C = after-sales function at HQ (middle office), reports at the middle-office project meeting
# weight = relative number of projects the team starts
TEAMS = [
    # Europe
    {"code": "UKI", "en": "UK & Ireland", "group": "R", "region": "Europe", "countries": ["UK", "Ireland"], "weight": 1.4},
    {"code": "DAC", "en": "DACH", "group": "R", "region": "Europe", "countries": ["Germany", "Austria", "Switzerland"], "weight": 1.0},
    {
        "code": "BNL",
        "en": "Benelux",
        "group": "R",
        "region": "Europe",
        "countries": ["Netherlands", "Belgium", "Luxembourg"],
        "weight": 0.6,
    },
    {
        "code": "NOR",
        "en": "Nordics",
        "group": "R",
        "region": "Europe",
        "countries": ["Norway", "Sweden", "Denmark", "Finland"],
        "weight": 0.8,
    },
    {"code": "FRA", "en": "France", "group": "R", "region": "Europe", "countries": ["France"], "weight": 1.0},
    {"code": "IBR", "en": "Iberia", "group": "R", "region": "Europe", "countries": ["Spain", "Portugal"], "weight": 1.5},
    {"code": "ITA", "en": "Italy", "group": "R", "region": "Europe", "countries": ["Italy"], "weight": 1.2},
    {
        "code": "CEE",
        "en": "Central & Eastern Europe",
        "group": "R",
        "region": "Europe",
        "countries": ["Poland", "Czechia", "Hungary", "Romania"],
        "weight": 1.3,
    },
    # Americas
    {
        "code": "MXC",
        "en": "Mexico & Central America",
        "group": "R",
        "region": "Americas",
        "countries": ["Mexico", "Costa Rica", "Panama"],
        "weight": 1.2,
    },
    {"code": "BRA", "en": "Brazil", "group": "R", "region": "Americas", "countries": ["Brazil"], "weight": 1.4},
    {
        "code": "SCO",
        "en": "Southern Cone & Andes",
        "group": "R",
        "region": "Americas",
        "countries": ["Chile", "Argentina", "Colombia", "Peru"],
        "weight": 1.0,
    },
    # Middle East
    {
        "code": "GCC",
        "en": "GCC",
        "group": "R",
        "region": "Middle East",
        "countries": ["UAE", "Saudi Arabia", "Qatar", "Kuwait"],
        "weight": 1.1,
    },
    {
        "code": "TRL",
        "en": "Türkiye & Levant",
        "group": "R",
        "region": "Middle East",
        "countries": ["Türkiye", "Israel", "Jordan"],
        "weight": 0.9,
    },
    # Africa
    {"code": "NAF", "en": "North Africa", "group": "R", "region": "Africa", "countries": ["Morocco", "Egypt", "Tunisia"], "weight": 0.7},
    {
        "code": "SSA",
        "en": "Sub-Saharan Africa",
        "group": "R",
        "region": "Africa",
        "countries": ["South Africa", "Kenya", "Nigeria"],
        "weight": 0.8,
    },
    # HQ functions (middle office)
    {"code": "CUS", "en": "Customer Experience", "group": "C", "region": "HQ", "countries": [], "weight": 1.0},
    {"code": "ACA", "en": "Service Academy", "group": "C", "region": "HQ", "countries": [], "weight": 0.7},
    {"code": "SPP", "en": "Service Products & Pricing", "group": "C", "region": "HQ", "countries": [], "weight": 1.0},
    {"code": "OWX", "en": "Owner Engagement", "group": "C", "region": "HQ", "countries": [], "weight": 0.5},
    {"code": "FLT", "en": "Bus & Fleet Service", "group": "C", "region": "HQ", "countries": [], "weight": 2.0},
    {"code": "TWS", "en": "Technical Support & Warranty", "group": "C", "region": "HQ", "countries": [], "weight": 1.2},
    {"code": "PAL", "en": "Parts Supply", "group": "C", "region": "HQ", "countries": [], "weight": 1.2},
    {"code": "SNS", "en": "Service Network & Standards", "group": "C", "region": "HQ", "countries": [], "weight": 1.6},
]
# Service Network & Standards is split into sections; its projects carry one.
SECTIONS = {"SNS": ["Dealer Development", "Network Operations", "Business Planning", "Systems & Tools"]}

# Project themes. {c} = a country of the team. Written for this repo, not taken from any real portfolio.
REGIONAL_THEMES = [
    "Service network expansion in {c}",
    "{c} authorised repairer onboarding",
    "HV technician certification for {c} workshops",
    "{c} roadside assistance provider tender",
    "Workshop equipment rollout {c}",
    "{c} dealer service KPI dashboard",
    "Fleet customer maintenance contract {c}",
    "Bodyshop partner network {c}",
    "{c} parts warehouse stock optimisation",
    "Service retention campaign {c}",
    "{c} warranty claim quality improvement",
    "Customer complaint handling SLA {c}",
    "{c} mobile service van pilot",
    "Local service pricing review {c}",
    "{c} charger installation partner programme",
    "Right-hand-drive service readiness {c}",
    "{c} extended warranty product launch",
    "Climate readiness campaign {c}",
    "PHEV service training for {c} dealers",
]
CENTRAL_THEMES = {
    "CUS": [
        "Multilingual contact centre consolidation",
        "Customer satisfaction survey redesign",
        "Complaint escalation process",
        "Roadside assistance performance review",
        "Customer callback automation",
    ],
    "ACA": [
        "Technician e-learning catalogue",
        "Regional training centre setup",
        "Master technician programme",
        "Trainer certification scheme",
        "Training records migration",
    ],
    "SPP": [
        "Service package pricing model",
        "Extended warranty portfolio",
        "Prepaid maintenance plans",
        "Accessory sales uplift",
        "Service revenue reporting",
    ],
    "OWX": ["Owner app service booking", "Connected-car service reminders", "Owner community events", "Service NPS follow-up flow"],
    "FLT": [
        "Electric bus fleet maintenance model",
        "Depot charging service contracts",
        "Bus battery health monitoring",
        "Coach operator service SLA",
        "Van fleet uptime programme",
        "Bus spare parts consignment stock",
        "City bus warranty process",
        "Fuel-cell bus service readiness",
        "Hydrogen refuelling partner support",
    ],
    "TWS": [
        "Warranty claim automation",
        "Technical hotline knowledge base",
        "Field fix campaign process",
        "Goodwill policy update",
        "Supplier cost recovery",
        "Repeat repair analysis",
    ],
    "PAL": [
        "Regional parts distribution centre",
        "Parts availability dashboard",
        "Back-order reduction",
        "VOR parts fast lane",
        "Customs clearance process for parts",
        "Parts pricing harmonisation",
    ],
    "SNS": [
        "Dealer standards audit",
        "Service portal migration",
        "Workshop process standard",
        "Service data warehouse",
        "Diagnostic tool rollout",
        "Service operations handbook",
    ],
}

# Faker locales by region (Latin-script names only). "arab" uses the hand-written list below.
LOCALES_BY_REGION = {
    "Europe": {"en_GB": 0.18, "de_DE": 0.17, "nl_NL": 0.1, "fr_FR": 0.15, "es_ES": 0.14, "it_IT": 0.12, "pl_PL": 0.09, "sv_SE": 0.05},
    "Americas": {"es_MX": 0.4, "pt_BR": 0.35, "es_CL": 0.12, "es_CO": 0.1, "en_US": 0.03},
    "Middle East": {"arab": 0.5, "tr_TR": 0.2, "en_IN": 0.2, "en_GB": 0.1},
    "Africa": {"arab": 0.25, "fr_FR": 0.15, "en_KE": 0.3, "zu_ZA": 0.2, "en_GB": 0.1},
    "HQ": {
        "nl_NL": 0.22,
        "en_GB": 0.16,
        "de_DE": 0.14,
        "fr_FR": 0.1,
        "es_ES": 0.1,
        "it_IT": 0.08,
        "pl_PL": 0.08,
        "en_IN": 0.07,
        "pt_BR": 0.05,
    },
}
ARAB_GIVEN = [
    "Ahmed",
    "Omar",
    "Khalid",
    "Youssef",
    "Hassan",
    "Fatima",
    "Layla",
    "Mariam",
    "Rami",
    "Tariq",
    "Nour",
    "Salma",
    "Karim",
    "Huda",
]
ARAB_FAMILY = ["Al Mansouri", "Haddad", "Nasser", "El Amrani", "Saleh", "Al Harbi", "Khoury", "Benali", "Farouk", "Al Qasimi", "Mansour"]

# Milestones: projects with one milestone have only the final deliverable, as in a typical PMO tracker.
FINAL_MILESTONE = "Final deliverable"
MILESTONE_POOL = [
    "Kick-off and plan agreed",
    "Current-state analysis",
    "Solution concept approved",
    "Supplier / partner selected",
    "Pilot started",
    "Pilot evaluated",
    "Rollout to first markets",
    "Training delivered",
    "Process handed over to line",
]
EVIDENCE_FORMS = ["text", "screenshot", "email", "file"]

# Strategic governance: a review board votes unanimously on S/A/B projects.
STRATEGIC_LEVELS = {"S": "Strategic", "A": "Key", "B": "Enabler"}

FOLLOW_UP_TYPES = {
    "incubate": "Not mature yet; incubate and decide whether it becomes a project",
    "postclose": "Track results for a period after a project closes",
    "monitor": "Needs follow-up but does not meet the bar for a project",
}

# Risks people write about in status updates (ground truth for the extractor).
RISK_CATEGORIES = [
    "parts_shortage",
    "resource_shortage",
    "dealer_readiness",
    "it_dependency",
    "budget",
    "regulatory",
    "customs_logistics",
    "data_quality",
    "stakeholder_alignment",
    "supplier_delay",
]
