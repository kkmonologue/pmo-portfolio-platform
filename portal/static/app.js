// PMO portal: one ES module, no build step. Data comes from api/<page>.json, served live by
// `python -m portal serve` or exported as static files by `python -m portal export`.
import { html, render, useState, useEffect, useMemo, useRef } from "./vendor/preact-htm.js";

/* ------------------------------------------------------------------ data */

const cache = new Map();
function get(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(`api/${path}.json`).then((r) => {
      if (!r.ok) return r.json().catch(() => ({})).then((b) => { throw new Error(b.detail || `${r.status} ${r.statusText} for api/${path}.json`); });
      return r.json();
    }));
  }
  return cache.get(path);
}
function useData(path) {
  const [s, set] = useState({ path: null });
  useEffect(() => {
    if (!path) return;
    let live = true;
    get(path).then((data) => live && set({ path, data }), (error) => { cache.delete(path); live && set({ path, error }); });
    return () => { live = false; };
  }, [path]);
  return s.path === path ? s : {};
}

/* ------------------------------------------------------------------ routing: #/view?key=value */

function parseHash() {
  const [p, q] = location.hash.replace(/^#\/?/, "").split("?");
  return { view: p || "overview", params: Object.fromEntries(new URLSearchParams(q || "")) };
}
function hashFor(view, params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)).toString();
  return `#/${view}${q ? "?" + q : ""}`;
}
function useRoute() {
  const [r, set] = useState(parseHash());
  useEffect(() => {
    const on = () => set(parseHash());
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  return r;
}
const go = (view, params) => { location.hash = hashFor(view, params); };
const setParams = (patch) => { const r = parseHash(); go(r.view, { ...r.params, ...patch }); };
const openProject = (id) => setParams({ p: id });

/* ------------------------------------------------------------------ formatting */

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const toDate = (s) => (s ? new Date(s.length > 10 ? s : s + "T00:00:00") : null);
const fd = (s) => { const d = toDate(s); return d ? `${d.getDate()} ${MON[d.getMonth()]} ${d.getFullYear()}` : "—"; };
const fdShort = (s) => { const d = toDate(s); return d ? `${d.getDate()} ${MON[d.getMonth()]}` : "—"; };
const days = (a, b) => Math.round((toDate(a) - toDate(b)) / 864e5);
const pct = (x) => (x == null ? "—" : `${Math.round(100 * x)}%`);
const n1 = (x) => (x == null ? "—" : Number(x).toFixed(1));
const initials = (n) => (n || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

const STATUS = { active: "Active", to_report: "Awaiting close", not_started: "Not started", on_hold: "On hold", closed: "Closed", canceled: "Canceled" };
const IN_FLIGHT = ["active", "to_report", "not_started", "on_hold"];
const CATEGORY = { delivery: "Delivery", schedule: "Schedule", closure: "Closure", deadline: "Deadline", resource: "Resource", extension: "Extension", silence: "Silence", reported: "Reported in update" };
const CATEGORY_HELP = {
  delivery: "A milestone is overdue",
  schedule: "Time used runs well ahead of milestones delivered",
  closure: "Planned end date has passed",
  deadline: "Planned end within 14 days, deliverables still open",
  resource: "Owner has left, or no executor assigned",
  extension: "Extended several times",
  silence: "No status update for 30+ days",
  reported: "Latest update reads red or blocked (read from the text by the extractor)",
};
const LEVEL = { high: "High", mid: "Medium", low: "Low" };
const KIND = { new: "New project", change: "Change", close: "Close" };
const CHANGE = { end: "end date", exec: "executors", owner: "owner" };
const REQ_STATUS = { approved: "Approved", pre_approved: "Pre-approved", pending: "Pending", returned: "Returned", rejected: "Rejected" };
const REQ_CLASS = { approved: "ok", pre_approved: "ok", pending: "warn", returned: "teal", rejected: "bad" };
const OFFICE = { front: "Front office", middle: "Middle office" };
const OFFICE_LONG = { front: "Front office · regional teams", middle: "Middle office · HQ functions" };
const STATUS_COLOR = { active: "var(--s1)", to_report: "var(--s2)", not_started: "var(--s3)", on_hold: "var(--s4)" };

/* ------------------------------------------------------------------ small components */

const ICONS = {
  overview: "M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z",
  projects: "M4 6h16M4 12h16M4 18h10",
  timeline: "M3 6h9M7 12h11M5 18h8M3 3v18",
  risks: "M12 3 2 20h20zM12 10v4M12 17.5v.01",
  biweekly: "M7 3v3M17 3v3M4 8h16M5 5h14v15H5zM9 13l2 2 4-4",
  approvals: "M9 12l2 2 4-4M5 4h14v16H5z",
  board: "M12 3l8 4-8 4-8-4zM4 12l8 4 8-4M4 17l8 4 8-4",
  quality: "M4 7c0-2 16-2 16 0s-16 2-16 0M4 7v10c0 2 16 2 16 0V7M4 12c0 2 16 2 16 0",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4",
  close: "M6 6l12 12M18 6 6 18",
  menu: "M4 6h16M4 12h16M4 18h16",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z",
  spark: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z",
  github: "M9 19c-4 1.5-4-2-6-2.5M15 21v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.7 4.7 0 0 0-1.3-3.2 4.3 4.3 0 0 0-.1-3.2s-1-.3-3.4 1.3a11.7 11.7 0 0 0-6.2 0C6.6 2.8 5.6 3.1 5.6 3.1a4.3 4.3 0 0 0-.1 3.2A4.7 4.7 0 0 0 4.2 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21",
};
const Icon = ({ name }) => html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d=${ICONS[name]} /></svg>`;

const StatusPill = ({ s }) => html`<span class=${`pill st-${s}`}><i></i>${STATUS[s] || s}</span>`;
const LevelPill = ({ l }) => (l ? html`<span class=${`pill lv-${l}`}>${LEVEL[l]}</span>` : html`<span class="faint">—</span>`);
const Rag = ({ r, title }) => (r ? html`<span class=${`pill rag-${r}`} title=${title || ""}><i></i>${r[0].toUpperCase() + r.slice(1)}</span>` : html`<span class="faint">—</span>`);
let TEAM_OFFICE = {};
const Team = ({ code, office }) => html`<span class=${`tag ${office || TEAM_OFFICE[code] || ""}`}>${code}</span>`;
const Lvl = ({ l }) => (l ? html`<span class=${`lvl ${l}`} title=${`Strategic level ${l}`}>${l}</span>` : null);
const Code = ({ c }) => html`<span class="mono">${c}</span>`;
const Prog = ({ v }) => html`<div class="prog"><div class="bar"><i style=${`width:${Math.round(100 * (v || 0))}%`}></i></div><span class="small num muted">${pct(v)}</span></div>`;
const Loading = () => html`<div class="empty">Loading…</div>`;
const Failed = ({ error }) => html`<div class="card empty">Could not load data: ${String(error.message || error)}</div>`;
const Kpi = ({ l, v, s, href, alert }) => (href
  ? html`<a class=${`kpi ${alert ? "alert" : ""}`} href=${href}><span class="l">${l}</span><span class="v">${v}</span><span class="s">${s}</span></a>`
  : html`<div class=${`kpi ${alert ? "alert" : ""}`}><span class="l">${l}</span><span class="v">${v}</span><span class="s">${s}</span></div>`);
const Card = ({ title, extra, children, pad }) => html`<section class="card">
  ${title && html`<div class="card-h"><h2>${title}</h2><span class="sp"></span>${extra}</div>`}
  ${pad ? html`<div class="card-b">${children}</div>` : children}</section>`;
function Seg({ value, options, onChange }) {
  return html`<div class="seg" role="group">${options.map(([v, l]) => html`<button class=${value === v ? "on" : ""} aria-pressed=${value === v} onClick=${() => onChange(v)}>${l}</button>`)}</div>`;
}

/* tooltips: any element with data-tip */
function useTooltips() {
  useEffect(() => {
    const tip = document.createElement("div");
    tip.className = "tip";
    tip.hidden = true;
    document.body.append(tip);
    const move = (e) => {
      const t = e.target.closest?.("[data-tip]");
      if (!t) { tip.hidden = true; return; }
      tip.textContent = t.dataset.tip;
      tip.hidden = false;
      const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
      const y = e.clientY + 18 + tip.offsetHeight > innerHeight ? e.clientY - tip.offsetHeight - 10 : e.clientY + 18;
      tip.style.left = `${x}px`;
      tip.style.top = `${y}px`;
    };
    document.addEventListener("mousemove", move);
    return () => { document.removeEventListener("mousemove", move); tip.remove(); };
  }, []);
}

/* ------------------------------------------------------------------ charts (plain SVG) */

function BarChart({ data, series, height = 200 }) {
  const W = 560, H = height, pl = 30, pb = 26, pt = 12;
  const mx = Math.max(4, ...data.map((d) => Math.max(...series.map((s) => d[s.key] || 0))));
  const step = mx <= 10 ? 2 : mx <= 25 ? 5 : mx <= 60 ? 10 : 20;
  const top = Math.ceil(mx / step) * step;
  const gw = (W - pl) / data.length, bw = Math.min(18, (gw - 12) / series.length);
  const y = (v) => pt + (H - pt - pb) * (1 - v / top);
  const ticks = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);
  return html`<svg class="chart" viewBox=${`0 0 ${W} ${H}`} role="img" aria-label=${series.map((s) => s.label).join(", ") + " per period"}>
    ${ticks.map((v) => html`<line class="grid-l" x1=${pl} x2=${W} y1=${y(v)} y2=${y(v)} /><text x=${pl - 6} y=${y(v) + 4} text-anchor="end">${v}</text>`)}
    ${data.map((d, i) => {
      const x0 = pl + i * gw + (gw - bw * series.length - 2 * (series.length - 1)) / 2;
      return html`<g data-tip=${`${d.label}\n` + series.map((s) => `${s.label}: ${d[s.key] || 0}`).join("\n")}>
        <rect x=${pl + i * gw} y=${pt} width=${gw} height=${H - pt - pb} fill="transparent" />
        ${series.map((s, j) => { const v = d[s.key] || 0; return v ? html`<rect x=${x0 + j * (bw + 2)} y=${y(v)} width=${bw} height=${H - pb - y(v)} rx="2" fill=${s.color} />` : null; })}
        <text x=${pl + i * gw + gw / 2} y=${H - 8} text-anchor="middle">${d.short || d.label}</text></g>`;
    })}
    <line class="axis" x1=${pl} x2=${W} y1=${H - pb} y2=${H - pb} /></svg>`;
}
const Legend = ({ series }) => html`<div class="legend">${series.map((s) => html`<span><i style=${`background:${s.color}`}></i>${s.label}</span>`)}</div>`;
function Stack({ parts }) {
  const tot = parts.reduce((a, p) => a + p.n, 0) || 1;
  return html`<div class="stack" style="height:14px">${parts.filter((p) => p.n).map((p) => html`<i style=${`width:${(100 * p.n) / tot}%;background:${p.color}`} data-tip=${`${p.label}: ${p.n}`}></i>`)}</div>`;
}

/* ------------------------------------------------------------------ pages */

function Overview({ meta }) {
  const { data, error } = useData("overview");
  if (error) return html`<${Failed} error=${error} />`;
  if (!data) return html`<${Loading} />`;
  const k = data.kpis, rep = data.reporting, y = meta.as_of.slice(0, 4);
  const qSeries = [
    { key: "started", label: "Started", color: "var(--s1)" },
    { key: "closed", label: "Closed", color: "var(--s3)" },
    { key: "canceled", label: "Canceled", color: "var(--mute)" },
  ];
  const quarters = data.quarters.map((q) => ({ ...q, label: q.quarter, short: q.quarter.replace(/^20(\d\d) /, "'$1 ") }));
  const byOffice = (o) => ["active", "to_report", "not_started", "on_hold"].map((s) => ({ label: STATUS[s], color: STATUS_COLOR[s], n: data.status_by_office.find((r) => r.office === o && r.status === s)?.n || 0 }));
  return html`
    <p class="lead">Portfolio of the ${meta.org} PMO on ${fd(meta.as_of)}: ${k.in_flight} projects in flight across ${meta.teams.length} teams. Every figure is read from the dbt marts; nothing on this page is typed in by hand.</p>
    <div class="kpis">
      <${Kpi} l="Projects in flight" v=${k.in_flight} s=${`Front ${k.in_flight_front} · Middle ${k.in_flight_middle}`} href=${hashFor("projects", { st: "inflight" })} />
      <${Kpi} l="Active" v=${k.active} s=${`Awaiting close ${k.awaiting_close} · On hold ${k.on_hold}`} href=${hashFor("projects", { st: "active" })} />
      <${Kpi} l="Red flags" v=${k.red_flags} s="Projects with a high risk" href="#/risks" alert=${k.red_flags > 0} />
      <${Kpi} l="Overdue milestones" v=${k.milestones_overdue || 0} s="On running projects" href=${hashFor("timeline", { risk: "1" })} />
      <${Kpi} l=${`${y} started / closed`} v=${html`${k.started_this_year}<small> / ${k.closed_this_year}</small>`} s="Closed = delivered, not canceled" href=${hashFor("projects", { st: "all" })} />
      <${Kpi} l="Waiting for a decision" v=${k.pending_requests + k.board_voting} s=${`${k.pending_requests} requests · ${k.board_voting} board votes`} href="#/approvals" />
    </div>
    <div class="grid g-7-5">
      <${Card} title="Projects per quarter" extra=${html`<${Legend} series=${qSeries} />`} pad>
        <${BarChart} data=${quarters} series=${qSeries} />
      <//>
      <${Card} title="What the latest updates say" extra=${html`<span class="ai"><${Icon} name="spark" />Extracted</span>`} pad>
        <p class="small muted" style="margin:0 0 12px">RAG read from the text of each running project's latest bi-weekly update, not the colour its author picked.</p>
        <div style="display:flex;flex-direction:column;gap:10px">
          <div class="stackrow"><span class="small muted">Content</span><${Stack} parts=${[{ label: "Red", n: rep.red, color: "var(--bad)" }, { label: "Amber", n: rep.amber, color: "var(--warn)" }, { label: "Green", n: rep.green, color: "var(--ok)" }]} /><span class="small num">${rep.projects}</span></div>
        </div>
        <div class="legend" style="margin:10px 0 14px"><span><i style="background:var(--bad)"></i>Red ${rep.red}</span><span><i style="background:var(--warn)"></i>Amber ${rep.amber}</span><span><i style="background:var(--ok)"></i>Green ${rep.green}</span></div>
        <div class="note plain small"><b>${rep.stated_differs}</b> of ${rep.projects} latest updates carry a colour that doesn't match their own text${rep.stated_green_reads_worse ? html`, ${rep.stated_green_reads_worse} of them marked green` : ""}. <a href="#/biweekly">Bi-weekly view</a></div>
      <//>
    </div>
    <div class="grid g-7-5">
      <${Card} title="Teams" extra=${html`<span class="small faint">in flight by status</span>`}>
        <div class="tw"><table class="t">
          <thead><tr><th>Team</th><th>Name</th><th style="min-width:150px">In flight</th><th class="r">High risk</th><th class="r">Overdue</th><th class="r">Updated ≤30d</th></tr></thead>
          <tbody>${data.teams.map((t) => html`<tr class="click" onClick=${() => go("projects", { team: t.team_code, st: "inflight" })}>
            <td><${Team} code=${t.team_code} office=${t.office} /></td><td>${t.team_name}</td>
            <td><div class="row" style="flex-wrap:nowrap"><${Stack} parts=${[{ label: "Active", n: t.projects_active, color: STATUS_COLOR.active }, { label: "Awaiting close", n: t.projects_awaiting_close, color: STATUS_COLOR.to_report }, { label: "On hold", n: t.projects_on_hold, color: STATUS_COLOR.on_hold }]} /><span class="num small" style="width:22px;text-align:right">${t.projects_in_flight}</span></div></td>
            <td class="r num">${t.high_risk_projects ? html`<b style="color:var(--bad)">${t.high_risk_projects}</b>` : html`<span class="faint">0</span>`}</td>
            <td class="r num">${t.milestones_overdue || html`<span class="faint">0</span>`}</td>
            <td class="r num">${pct(t.share_active_updated_30d)}</td></tr>`)}</tbody>
        </table></div>
      <//>
      <div class="grid" style="align-content:start">
        <${Card} title="In flight by office" pad>
          <div style="display:flex;flex-direction:column;gap:12px">
            ${["front", "middle"].map((o) => html`<div class="stackrow"><span class="small muted">${OFFICE[o]}</span><${Stack} parts=${byOffice(o)} /><span class="small num">${byOffice(o).reduce((a, p) => a + p.n, 0)}</span></div>`)}
          </div>
          <div class="legend" style="margin-top:12px">${["active", "to_report", "not_started", "on_hold"].map((s) => html`<span><i style=${`background:${STATUS_COLOR[s]}`}></i>${STATUS[s]}</span>`)}</div>
        <//>
        <${Card} title="Top risks" extra=${html`<a class="small" href="#/risks">All risks</a>`}>
          <div class="list">${data.top_risks.map((r) => html`<a class="li" onClick=${() => openProject(r.project_id)}>
            <${LevelPill} l=${r.risk_level} />
            <div class="grow"><div class="ttl">${r.project_title}</div><div class="small faint">${r.project_code} · ${CATEGORY[r.category]} · ${r.finding}</div></div></a>`)}
          ${!data.top_risks.length && html`<div class="empty">No open risks</div>`}</div>
        <//>
      </div>
    </div>`;
}

function Projects({ meta, params }) {
  const { data, error } = useData("projects");
  const [limit, setLimit] = useState(60);
  const q = params.q || "", team = params.team || "", office = params.office || "", st = params.st || "inflight", strat = params.strat || "";
  useEffect(() => setLimit(60), [q, team, office, st, strat]);
  const rows = useMemo(() => {
    if (!data) return [];
    const ql = q.toLowerCase();
    return data.filter((p) => (!team || p.team === team) && (!office || p.office === office) && (!strat || p.strategic_level)
      && (st === "all" || (st === "inflight" ? IN_FLIGHT.includes(p.status) : p.status === st))
      && (!ql || p.code.toLowerCase().includes(ql) || p.title.toLowerCase().includes(ql) || (p.owner || "").toLowerCase().includes(ql)));
  }, [data, q, team, office, st, strat]);
  if (error) return html`<${Failed} error=${error} />`;
  if (!data) return html`<${Loading} />`;
  return html`
    <div class="filters">
      <input type="search" placeholder="Code, title or owner" value=${q} onInput=${(e) => setParams({ q: e.target.value })} aria-label="Filter projects" />
      <${Seg} value=${st} onChange=${(v) => setParams({ st: v })} options=${[["inflight", "In flight"], ["active", "Active"], ["on_hold", "On hold"], ["closed", "Closed"], ["canceled", "Canceled"], ["all", "All"]]} />
      <select value=${office} onChange=${(e) => setParams({ office: e.target.value, team: "" })} aria-label="Office">
        <option value="">All offices</option><option value="front">Front office</option><option value="middle">Middle office</option></select>
      <select value=${team} onChange=${(e) => setParams({ team: e.target.value })} aria-label="Team">
        <option value="">All teams</option>${meta.teams.filter((t) => !office || t.office === office).map((t) => html`<option value=${t.code}>${t.code} · ${t.name}</option>`)}</select>
      <label class="small row" style="gap:6px;cursor:pointer"><input type="checkbox" checked=${!!strat} onChange=${(e) => setParams({ strat: e.target.checked ? "1" : "" })} /> Strategic only</label>
      <span class="count">${rows.length} projects</span>
    </div>
    <${Card}>
      <div class="tw"><table class="t">
        <thead><tr><th>Code</th><th>Project</th><th>Team</th><th>Status</th><th>Owner</th><th>Planned end</th><th>Delivered</th><th>Latest update</th><th>Main risk</th></tr></thead>
        <tbody>${rows.slice(0, limit).map((p) => html`<tr class="click" onClick=${() => openProject(p.id)}>
          <td class="nowrap"><${Code} c=${p.code} /></td>
          <td class="nm"><div><${Lvl} l=${p.strategic_level} /> ${p.title}</div></td>
          <td><${Team} code=${p.team} office=${p.office} /></td>
          <td><${StatusPill} s=${p.status} /></td>
          <td class="nowrap">${p.owner}${p.owner_has_left ? html` <span class="pill bad" title="Owner has left">left</span>` : ""}</td>
          <td class="nowrap num">${fd(p.status === "closed" || p.status === "canceled" ? p.actual_end : p.planned_end)}${p.extension_count ? html` <span class="small faint" title=${`Extended ${p.extension_count}×`}>+${p.extension_count}</span>` : ""}</td>
          <td><${Prog} v=${p.delivery_ratio} /></td>
          <td>${IN_FLIGHT.includes(p.status) ? html`<${Rag} r=${p.rag} title=${p.stated_rag && p.stated_rag !== p.rag ? `Author typed ${p.stated_rag}` : ""} />${p.blocked ? html` <span class="pill bad">Blocked</span>` : ""}` : html`<span class="faint">—</span>`}</td>
          <td class="nowrap">${p.risk_level ? html`<span data-tip=${`${CATEGORY[p.risk_category]}: ${p.risk_finding}`}><${LevelPill} l=${p.risk_level} /></span>` : html`<span class="faint">—</span>`}</td>
        </tr>`)}</tbody>
      </table></div>
      ${!rows.length && html`<div class="empty">No projects match these filters</div>`}
      ${rows.length > limit && html`<div class="more"><button class="btn" onClick=${() => setLimit(limit + 100)}>Show ${Math.min(100, rows.length - limit)} more</button></div>`}
    <//>`;
}

function Timeline({ meta, params }) {
  const { data, error } = useData("timeline");
  const office = params.office || "", team = params.team || "", risk = params.risk || "";
  const wrap = useRef();
  useEffect(() => {
    // open the chart with today a quarter of the way in, so the past and the next months both show
    const w = wrap.current, t = w?.querySelector(".g-today");
    if (!w || !t) return;
    const label = w.querySelector(".g-l")?.offsetWidth || 320;
    w.scrollLeft += t.getBoundingClientRect().left - w.getBoundingClientRect().left - label - (w.clientWidth - label) * 0.25;
  }, [data, office, team, risk]);
  if (error) return html`<${Failed} error=${error} />`;
  if (!data) return html`<${Loading} />`;
  const asOf = meta.as_of;
  const msBy = {};
  data.milestones.forEach((m) => (msBy[m.id] ||= []).push(m));
  const ps = data.projects.filter((p) => (!office || p.office === office) && (!team || p.team === team) && (!risk || p.risk_level === "high" || (msBy[p.id] || []).some((m) => m.is_overdue)));
  // window: 6 months back to 9 months ahead, widened to fit what is shown (capped at 2 years)
  const t0 = toDate(asOf);
  let a = new Date(t0.getFullYear(), t0.getMonth() - 6, 1), b = new Date(t0.getFullYear(), t0.getMonth() + 10, 1);
  ps.forEach((p) => { const s = toDate(p.start_date), e = toDate(p.planned_end); if (s && s < a) a = new Date(s.getFullYear(), s.getMonth(), 1); if (e && e > b) b = new Date(e.getFullYear(), e.getMonth() + 1, 1); });
  const minA = new Date(t0.getFullYear() - 1, t0.getMonth(), 1), maxB = new Date(t0.getFullYear() + 1, t0.getMonth() + 1, 1);
  if (a < minA) a = minA;
  if (b > maxB) b = maxB;
  const span = b - a, X = (d) => `${Math.max(0, Math.min(100, (100 * (toDate(d) - a)) / span))}%`;
  const months = [];
  for (let d = new Date(a); d < b; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) months.push(new Date(d));
  const groups = [];
  ps.forEach((p) => { const g = groups.find((x) => x.team === p.team); g ? g.items.push(p) : groups.push({ team: p.team, office: p.office, items: [p] }); });
  const teamName = Object.fromEntries(meta.teams.map((t) => [t.code, t.name]));
  const msClass = (m) => (m.status === "accepted" ? "accepted" : m.is_overdue ? "overdue" : days(m.due_date, asOf) <= 14 ? "soon" : "");
  const minW = Math.max(900, months.length * 64 + 320);
  return html`
    <div class="filters">
      <${Seg} value=${office} onChange=${(v) => setParams({ office: v, team: "" })} options=${[["", "All"], ["front", "Front office"], ["middle", "Middle office"]]} />
      <select value=${team} onChange=${(e) => setParams({ team: e.target.value })} aria-label="Team"><option value="">All teams</option>${meta.teams.filter((t) => !office || t.office === office).map((t) => html`<option value=${t.code}>${t.code} · ${t.name}</option>`)}</select>
      <label class="small row" style="gap:6px;cursor:pointer"><input type="checkbox" checked=${!!risk} onChange=${(e) => setParams({ risk: e.target.checked ? "1" : "" })} /> High risk or overdue only</label>
      <div class="legend" style="margin-left:auto">
        <span><i style="background:var(--ok);transform:rotate(45deg)"></i>Accepted</span><span><i style="background:var(--bad);transform:rotate(45deg)"></i>Overdue</span>
        <span><i style="background:var(--warn);transform:rotate(45deg)"></i>Due ≤14 days</span><span><i style="background:var(--ink-3);transform:rotate(45deg)"></i>Planned</span>
        <span><i style="border-top:2px dotted var(--bad);height:0;width:14px;border-radius:0"></i>Extension</span></div>
    </div>
    <${Card} title=${`${ps.length} projects in flight`} extra=${html`<span class="small faint">bar = start to planned end, fill = share of milestones delivered</span>`}>
      <div class="gantt-wrap" ref=${wrap}><div class="gantt" style=${`min-width:${minW}px`}>
        <div class="g-row head"><div class="g-l small muted">Project</div><div class="g-r">
          ${months.map((m) => html`<div class="g-m" style=${`left:${X(m.toISOString().slice(0, 10))}`}><span>${m.getMonth() === 0 || m === months[0] ? `${MON[m.getMonth()]} ${m.getFullYear()}` : MON[m.getMonth()]}</span></div>`)}
        </div></div>
        ${groups.map((g) => html`
          <div class="g-row grp"><div class="g-l"><${Team} code=${g.team} office=${g.office} /> ${teamName[g.team]} <span class="faint small">${g.items.length}</span></div><div class="g-r"></div></div>
          ${g.items.map((p) => html`<div class="g-row">
            <div class="g-l" onClick=${() => openProject(p.id)} title=${p.title}><span class=${`g-dot ${p.risk_level || ""}`} data-tip=${p.risk_level ? `${LEVEL[p.risk_level]} risk` : "No open risk"}></span><span class="mono small faint" style="white-space:nowrap">${p.code}</span><span class="ttl">${p.title}</span></div>
            <div class="g-r">
              <div class="g-today" style=${`left:${X(asOf)}`}></div>
              ${p.start_date && p.planned_end && html`<div class="g-bar" style=${`left:${X(p.start_date)};width:calc(${X(p.planned_end)} - ${X(p.start_date)});--c:${STATUS_COLOR[p.status]}`} onClick=${() => openProject(p.id)}
                data-tip=${`${p.code} · ${STATUS[p.status]}\n${fd(p.start_date)} → ${fd(p.planned_end)}${p.original_end !== p.planned_end ? `\noriginally ${fd(p.original_end)}` : ""}\nDelivered ${pct(p.delivery_ratio)} · ${p.owner}`}><i style=${`width:${Math.round(100 * (p.delivery_ratio || 0))}%`}></i></div>`}
              ${p.original_end && p.planned_end && p.original_end < p.planned_end && html`<div class="g-ext" style=${`left:${X(p.original_end)};width:calc(${X(p.planned_end)} - ${X(p.original_end)})`}></div>`}
              ${(msBy[p.id] || []).filter((m) => { const d = toDate(m.status === "accepted" && m.accepted_on ? m.accepted_on : m.due_date); return d >= a && d <= b; }).map((m) => html`<div class=${`g-ms ${msClass(m)}`} style=${`left:${X(m.status === "accepted" && m.accepted_on ? m.accepted_on : m.due_date)}`}
                data-tip=${`M${m.seq} ${m.name}\n${m.status === "accepted" ? `accepted ${fd(m.accepted_on)}` : `due ${fd(m.due_date)}${m.is_overdue ? ` · ${m.days_overdue} days overdue` : ""}`}`}></div>`)}
            </div></div>`)}`)}
        ${!ps.length && html`<div class="empty">No projects match these filters</div>`}
      </div></div>
    <//>`;
}

function Risks({ params }) {
  const { data, error } = useData("risks");
  const lvl = params.lvl || "", cat = params.cat || "";
  if (error) return html`<${Failed} error=${error} />`;
  if (!data) return html`<${Loading} />`;
  const f = data.findings;
  const rows = f.filter((r) => (!lvl || r.risk_level === lvl) && (!cat || r.category === cat));
  const cats = Object.keys(CATEGORY).map((c) => ({ c, n: f.filter((r) => r.category === c).length, hi: f.filter((r) => r.category === c && r.risk_level === "high").length })).filter((x) => x.n);
  const projectsHigh = new Set(f.filter((r) => r.risk_level === "high").map((r) => r.project_id)).size;
  return html`
    <p class="lead">${f.length} findings on ${new Set(f.map((r) => r.project_id)).size} running projects, ${projectsHigh} with at least one high risk. The rules run in dbt (<span class="mono">mart_project_risks</span>); strategic projects are raised one level and paused projects are not scored.</p>
    <div class="kpis" style="grid-template-columns:repeat(auto-fill,minmax(128px,1fr))">
      ${cats.map((x) => html`<a class="kpi" href=${hashFor("risks", { ...params, cat: cat === x.c ? "" : x.c })} style=${cat === x.c ? "border-color:var(--accent)" : ""} data-tip=${CATEGORY_HELP[x.c]}>
        <span class="l">${CATEGORY[x.c]}</span><span class="v">${x.n}</span><span class="s">${x.hi ? `${x.hi} high` : "none high"}</span></a>`)}
    </div>
    <div class="filters">
      <${Seg} value=${lvl} onChange=${(v) => setParams({ lvl: v })} options=${[["", "All levels"], ["high", "High"], ["mid", "Medium"], ["low", "Low"]]} />
      ${cat && html`<button class="btn" onClick=${() => setParams({ cat: "" })}>${CATEGORY[cat]} <${Icon} name="close" /></button>`}
      <span class="count">${rows.length} findings</span>
    </div>
    <${Card}>
      <div class="tw"><table class="t">
        <thead><tr><th>Level</th><th>Category</th><th>Finding</th><th>Project</th><th>Team</th><th>Owner</th></tr></thead>
        <tbody>${rows.map((r) => html`<tr class="click" onClick=${() => openProject(r.project_id)}>
          <td><${LevelPill} l=${r.risk_level} /></td>
          <td class="nowrap">${r.category === "reported" ? html`<span class="ai"><${Icon} name="spark" /></span> ` : ""}${CATEGORY[r.category]}</td>
          <td>${r.finding}</td>
          <td class="nm"><div><span class="mono small faint">${r.project_code}</span> ${r.is_strategic ? html`<span class="lvl">S</span> ` : ""}${r.project_title}</div></td>
          <td><${Team} code=${r.team_code} office=${r.office} /></td><td class="nowrap">${r.owner_name}</td></tr>`)}</tbody>
      </table></div>
      ${!rows.length && html`<div class="empty">No findings</div>`}
    <//>
    <${Card} title="Paused projects for a PMO decision" extra=${html`<span class="small faint">${data.on_hold.length} on hold · not scored, their plan is frozen</span>`}>
      <div class="list">${data.on_hold.slice(0, 12).map((p) => html`<a class="li" onClick=${() => openProject(p.project_id)}>
        <span class="mono small faint" style="width:96px;flex:none">${p.project_code}</span><div class="grow"><div class="ttl">${p.project_title}</div><div class="small faint">${p.team_code} · ${p.owner_name}</div></div>
        <span class="small faint nowrap">${p.days_since_update == null ? "never updated" : `updated ${p.days_since_update}d ago`}</span></a>`)}</div>
    <//>`;
}

function Biweekly({ meta }) {
  const { data, error } = useData("biweekly");
  const [only, setOnly] = useState("");
  if (error) return html`<${Failed} error=${error} />`;
  if (!data) return html`<${Loading} />`;
  return html`
    <p class="lead">Project meetings alternate weekly between the front office (regional teams) and the middle office (HQ functions), so every running project posts an update every two weeks. Each update's RAG is also read from its text, so a green label on a red story stands out.</p>
    <div class="bw-tiles">${data.tracks.map((t) => {
      const done = t.projects.filter((p) => p.posted_at).length;
      const hist = t.history.slice(-10);
      return html`<div class="bw-tile">
        <span class="small muted">${OFFICE_LONG[t.track]}</span>
        <span class="d">${fd(t.upcoming)}</span>
        <span class="small muted">${days(t.upcoming, meta.as_of) === 0 ? "today" : `in ${days(t.upcoming, meta.as_of)} days`}</span>
        <div class="bw-bar"><i style=${`width:${t.projects.length ? (100 * done) / t.projects.length : 0}%`}></i></div>
        <span class="small"><b class="num">${done}</b> / ${t.projects.length} projects posted</span>
        <div class="row" style="margin-top:8px;align-items:flex-end;gap:12px"><div class="spark" style="flex:1" aria-label="Share posted on time at past meetings">${hist.map((m) => html`<i class=${m.on_time_share < 0.8 ? "lo" : ""} style=${`height:${Math.max(6, 100 * m.on_time_share)}%`} data-tip=${`${fd(m.meeting_date)}: ${m.updates} updates, ${pct(m.on_time_share)} before the meeting`}></i>`)}</div>
          <span class="small faint">on time, last ${hist.length} meetings</span></div>
      </div>`;
    })}</div>
    <div class="filters"><${Seg} value=${only} onChange=${setOnly} options=${[["", "All projects"], ["todo", "Not posted"], ["flag", "Colour doesn't match text"]]} /></div>
    ${data.tracks.map((t) => {
      const rows = t.projects.filter((p) => (only === "todo" ? !p.posted_at : only === "flag" ? p.stated_differs_from_content : true));
      return html`<${Card} title=${html`${OFFICE[t.track]} · <span class="num">${fd(t.upcoming)}</span>`} extra=${html`<span class="small faint">${rows.length} projects</span>`}>
        <div class="tw"><table class="t">
          <thead><tr><th>Code</th><th>Project</th><th>Team</th><th>Owner</th><th>Typed</th><th>Read from text</th><th>Summary</th></tr></thead>
          <tbody>${rows.map((p) => html`<tr class="click" onClick=${() => setParams({ p: p.id, tab: "updates" })}>
            <td class="nowrap"><${Code} c=${p.code} /></td><td class="nm"><div><${Lvl} l=${p.strategic_level} /> ${p.title}</div></td>
            <td><${Team} code=${p.team} office=${t.track} /></td><td class="nowrap">${p.owner}</td>
            <td>${p.posted_at ? html`<${Rag} r=${p.stated_rag} />` : html`<span class="pill neutral">Not posted</span>`}</td>
            <td class="nowrap">${p.posted_at ? html`<${Rag} r=${p.extracted_rag} />${p.extracted_blocked ? html` <span class="pill bad">Blocked</span>` : ""}${p.stated_differs_from_content ? html` <span class="pill warn" data-tip="The colour typed by the author differs from what the text says">≠</span>` : ""}` : ""}</td>
            <td class="small muted" style="max-width:380px"><div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.summary || ""}</div></td></tr>`)}</tbody>
        </table></div>
        ${!rows.length && html`<div class="empty">Nothing here</div>`}
      <//>`;
    })}`;
}

function Approvals() {
  const { data, error } = useData("approvals");
  if (error) return html`<${Failed} error=${error} />`;
  if (!data) return html`<${Loading} />`;
  const months = [...new Set(data.monthly.map((m) => m.month))].map((m) => {
    const r = Object.fromEntries(data.monthly.filter((x) => x.month === m).map((x) => [x.request_kind, x.n]));
    return { label: m, short: MON[+m.slice(5) - 1], ...r };
  });
  const series = [{ key: "new", label: "New project", color: "var(--s1)" }, { key: "change", label: "Change", color: "var(--s2)" }, { key: "close", label: "Close", color: "var(--s3)" }];
  const ReqWhat = ({ r }) => html`${KIND[r.request_kind]}${r.change_types ? html`<span class="faint"> · ${r.change_types.split(",").map((c) => CHANGE[c] || c).join(", ")}</span>` : ""}`;
  return html`
    <p class="lead">Every new project, change and closure goes through a request. The PMO pre-checks it; strategic projects then go to the board. Read-only here: decisions are taken in the source application.</p>
    <${Card} title="Waiting for a decision" extra=${html`<span class="badge">${data.pending.length}</span>`}>
      <div class="tw"><table class="t">
        <thead><tr><th>Request</th><th>Project</th><th>Team</th><th>Submitted by</th><th>Submitted</th><th class="r">Waiting</th></tr></thead>
        <tbody>${data.pending.map((r) => html`<tr class=${r.project_id ? "click" : ""} onClick=${() => r.project_id && openProject(r.project_id)}>
          <td class="nowrap"><${ReqWhat} r=${r} />${r.request_version > 1 ? html` <span class="pill teal">v${r.request_version}</span>` : ""}${r.requested_new_end ? html`<div class="small faint">new end ${fd(r.requested_new_end)}</div>` : ""}</td>
          <td class="nm"><div>${r.project_code ? html`<span class="mono small faint">${r.project_code}</span> ` : ""}${r.title}</div></td>
          <td><${Team} code=${r.team_code} /></td><td class="nowrap">${r.submitted_by}</td><td class="nowrap">${fd(r.submitted_at)}</td>
          <td class="r num">${r.waiting_days > 5 ? html`<b style="color:var(--bad)">${r.waiting_days}d</b>` : `${r.waiting_days}d`}</td></tr>`)}</tbody>
      </table></div>
      ${!data.pending.length && html`<div class="empty">Nothing waiting</div>`}
    <//>
    <div class="grid g-7-5">
      <${Card} title="Requests per month" extra=${html`<${Legend} series=${series} />`} pad><${BarChart} data=${months} series=${series} /><//>
      <${Card} title="Outcome and decision time">
        <div class="tw"><table class="t">
          <thead><tr><th>Kind</th><th class="r">Requests</th><th class="r">Returned</th><th class="r">Rejected</th><th class="r">Median days</th><th class="r">P90 days</th></tr></thead>
          <tbody>${data.by_kind.map((k) => html`<tr><td>${KIND[k.request_kind]}</td><td class="r num">${k.requests}</td>
            <td class="r num">${pct(k.returned / k.requests)}</td><td class="r num">${pct(k.rejected / k.requests)}</td>
            <td class="r num">${n1(k.median_days)}</td><td class="r num">${n1(k.p90_days)}</td></tr>`)}</tbody>
        </table></div>
        <div class="card-b small faint" style="padding-top:10px">Returned requests come back as a new version; decision time counts from each submission.</div>
      <//>
    </div>
    <${Card} title="Recent decisions">
      <div class="tw"><table class="t">
        <thead><tr><th>Decided</th><th>Request</th><th>Project</th><th>Outcome</th><th>Comment</th><th class="r">Days</th></tr></thead>
        <tbody>${data.recent.map((r) => html`<tr class=${r.project_id ? "click" : ""} onClick=${() => r.project_id && openProject(r.project_id)}>
          <td class="nowrap">${fd(r.decided_at)}</td><td class="nowrap"><${ReqWhat} r=${r} /></td>
          <td class="nm"><div>${r.project_code ? html`<span class="mono small faint">${r.project_code}</span> ` : ""}${r.title}</div></td>
          <td><span class=${`pill ${REQ_CLASS[r.request_status]}`}>${REQ_STATUS[r.request_status]}</span></td>
          <td class="small muted">${r.decision_comment || ""}</td><td class="r num">${n1(r.decision_days)}</td></tr>`)}</tbody>
      </table></div>
    <//>`;
}

function Board() {
  const { data, error } = useData("board");
  if (error) return html`<${Failed} error=${error} />`;
  if (!data) return html`<${Loading} />`;
  const RS = { voting: ["Voting", "warn"], approved: ["Approved", "ok"], revise: ["Sent back", "teal"] };
  const decided = data.reviews.filter((r) => r.review_status !== "voting");
  const avg = decided.length ? decided.reduce((a, r) => a + (r.days_to_outcome || 0), 0) / decided.length : null;
  return html`
    <p class="lead">Projects proposed at strategic level S, A or B need a board vote after the PMO pre-check. A single objection sends the proposal back for revision.</p>
    <div class="kpis" style="grid-template-columns:repeat(4,minmax(0,1fr))">
      <${Kpi} l="Strategic projects in flight" v=${data.strategic.length} s=${["S", "A", "B"].map((l) => `${l} ${data.strategic.filter((p) => p.strategic_level === l).length}`).join(" · ")} />
      <${Kpi} l="Votes open" v=${data.reviews.filter((r) => r.review_status === "voting").length} s="Waiting for board members" />
      <${Kpi} l="Sent back for revision" v=${data.reviews.filter((r) => r.review_status === "revise").length} s=${`of ${data.reviews.length} review rounds`} />
      <${Kpi} l="Days to outcome" v=${n1(avg)} s="Average, decided rounds" />
    </div>
    <${Card} title="Strategic projects in flight">
      <div class="tw"><table class="t">
        <thead><tr><th>Level</th><th>Code</th><th>Project</th><th>Team</th><th>Status</th><th>Owner</th><th>Planned end</th><th>Delivered</th><th>Main risk</th></tr></thead>
        <tbody>${data.strategic.map((p) => html`<tr class="click" onClick=${() => openProject(p.id)}>
          <td><${Lvl} l=${p.strategic_level} /></td><td class="nowrap"><${Code} c=${p.code} /></td><td class="nm"><div>${p.title}</div></td>
          <td><${Team} code=${p.team} /></td><td><${StatusPill} s=${p.status} /></td><td class="nowrap">${p.owner}</td><td class="nowrap">${fd(p.planned_end)}</td>
          <td><${Prog} v=${p.delivery_ratio} /></td><td>${p.risk_level ? html`<span data-tip=${p.finding}><${LevelPill} l=${p.risk_level} /></span>` : html`<span class="faint">—</span>`}</td></tr>`)}</tbody>
      </table></div>
    <//>
    <${Card} title="Review rounds">
      <div class="tw"><table class="t">
        <thead><tr><th>Sent</th><th>Proposal</th><th>Team</th><th>Level</th><th>Round</th><th>Votes</th><th>Outcome</th><th class="r">Days</th></tr></thead>
        <tbody>${data.reviews.map((r) => html`<tr class=${r.project_id ? "click" : ""} onClick=${() => r.project_id && openProject(r.project_id)}>
          <td class="nowrap">${fd(r.sent_at)}</td><td class="nm"><div>${r.project_code ? html`<span class="mono small faint">${r.project_code}</span> ` : ""}${r.requested_title}</div></td>
          <td><${Team} code=${r.team_code} /></td><td><${Lvl} l=${r.strategic_level} /></td><td class="num">${r.review_round}</td>
          <td><span class="votes"><span class="vchip yes">✓ ${r.votes_yes}</span>${r.votes_no ? html`<span class="vchip no">✕ ${r.votes_no}</span>` : ""}<span class="small faint">/ ${data.voters.length}</span></span></td>
          <td><span class=${`pill ${RS[r.review_status]?.[1] || "neutral"}`}>${RS[r.review_status]?.[0] || r.review_status}</span></td>
          <td class="r num">${n1(r.days_to_outcome)}</td></tr>`)}</tbody>
      </table></div>
    <//>
    <${Card} title="Board members" pad>
      <div class="people">${data.voters.map((v) => html`<div class="person"><span class="av">${initials(v.name)}</span><span><b>${v.name}</b><small>${v.job_title}</small><small>${v.board_role === "steering" ? "Steering" : "Execution"} committee</small></span></div>`)}</div>
    <//>`;
}

function Quality({ meta }) {
  const { data, error } = useData("quality");
  if (error) return html`<${Failed} error=${error} />`;
  if (!data) return html`<${Loading} />`;
  const S = { ok: ["Matches", "ok"], status_mismatch: ["Status differs", "warn"], missing_in_tracker: ["Missing in tracker", "bad"], not_in_system: ["Not in system", "teal"] };
  const tot = data.summary.reduce((a, s) => a + s.n, 0);
  const M = { project_code: "Project code", legacy_code: "Legacy code", unmatched: "No match" };
  return html`
    <p class="lead">Teams still keep the old weekly Excel tracker next to the system. dbt matches every tracker row to a project (by code, then by legacy code) and compares the two, so the PMO knows which numbers to trust.</p>
    <div class="pipe" aria-label="Data pipeline">
      <span>Source app <b>SQLite / Postgres</b></span><span class="arrow">→</span><span>Excel trackers</span><span class="arrow">→</span>
      <span>dlt <b>incremental</b></span><span class="arrow">→</span><span>DuckDB <b>raw</b></span><span class="arrow">→</span><span>dbt <b>staging · marts · tests</b></span><span class="arrow">→</span>
      <span>LLM extraction</span><span class="arrow">→</span><span>this portal</span><em class="faint" style="margin-left:6px">orchestrated by Dagster</em>
    </div>
    <div class="kpis" style="grid-template-columns:repeat(4,minmax(0,1fr))">
      ${data.summary.map((s) => html`<${Kpi} l=${S[s.status]?.[0] || s.status} v=${s.n} s=${`${pct(s.n / tot)} of tracker rows · ${data.snapshot_week}`} alert=${s.status !== "ok" && s.n > 0} />`)}
    </div>
    <div class="grid g-7-5">
      <${Card} title="Rows to fix" extra=${html`<span class="small faint">${data.issues.length}</span>`}>
        <div class="tw"><table class="t">
          <thead><tr><th>Issue</th><th>Tracker reference</th><th>Project</th><th>System</th><th>Tracker</th><th>Sheet · row</th></tr></thead>
          <tbody>${data.issues.map((r) => html`<tr class=${r.project_id ? "click" : ""} onClick=${() => r.project_id && openProject(r.project_id)}>
            <td><span class=${`pill ${S[r.reconciliation_status]?.[1]}`}>${S[r.reconciliation_status]?.[0]}</span></td>
            <td class="nowrap"><span class="mono">${r.project_ref || "—"}</span></td><td class="nm"><div>${r.project_title || html`<span class="faint">no project found</span>`}</div></td>
            <td class="nowrap">${r.system_status ? STATUS[r.system_status] || r.system_status : "—"}</td><td class="nowrap">${r.tracker_status || "—"}</td>
            <td class="small faint nowrap">${r.sheet_name ? `${r.sheet_name} · ${r.source_row}` : "—"}</td></tr>`)}</tbody>
        </table></div>
      <//>
      <div class="grid" style="align-content:start">
        <${Card} title="How rows were matched" pad>
          <div style="display:flex;flex-direction:column;gap:10px">${data.match_methods.map((m) => html`<div class="stackrow"><span class="small muted">${M[m.match_method] || m.match_method}</span>
            <div class="stack" style="height:10px"><i style=${`width:${(100 * m.n) / data.match_methods.reduce((a, x) => a + x.n, 0)}%;background:${m.match_method === "unmatched" ? "var(--bad)" : "var(--s1)"}`}></i></div><span class="small num">${m.n}</span></div>`)}</div>
        <//>
        <${Card} title="About this data" pad>
          <p class="small muted" style="margin:0 0 8px">Everything here is generated by the repository's simulator: a made-up NEV maker's after-sales PMO with ${meta.teams.length} teams. No real company data.</p>
          <p class="small muted" style="margin:0">Status updates: ${meta.extractors.map((e) => `${e.updates} read by ${e.extractor}`).join(", ")}. Data as of ${fd(meta.as_of)}, built ${fd(meta.generated_at)}.</p>
        <//>
      </div>
    </div>`;
}

/* ------------------------------------------------------------------ project drawer */

function ProjectDrawer({ id, tab, meta }) {
  const { data, error } = useData(`projects/${id}`);
  const ref = useRef();
  const close = () => setParams({ p: "", tab: "" });
  useEffect(() => {
    const k = (e) => e.key === "Escape" && close();
    addEventListener("keydown", k);
    ref.current?.focus();
    return () => removeEventListener("keydown", k);
  }, []);
  const t = tab || "summary";
  const p = data?.project;
  const tabs = [["summary", "Summary"], ["milestones", "Milestones"], ["updates", "Updates"], ["requests", "Requests"], ["history", "History"]];
  return html`<div class="scrim" onClick=${(e) => e.target === e.currentTarget && close()}>
    <aside class="drawer" role="dialog" aria-modal="true" aria-label="Project details" tabindex="-1" ref=${ref}>
      <div class="d-h">
        <div class="row"><span class="mono muted">${p?.project_code || "…"}</span>${p && html`<${StatusPill} s=${p.status} /><${Lvl} l=${p.strategic_level} /><${Team} code=${p.team_code} office=${p.office} />`}
          <span style="flex:1"></span><button class="btn icon-btn" onClick=${close} aria-label="Close"><${Icon} name="close" /></button></div>
        <h2>${p?.project_title || (error ? "Not found" : "Loading…")}</h2>
        <div class="tabs" role="tablist">${tabs.map(([k, l]) => html`<button role="tab" aria-selected=${t === k} class=${t === k ? "on" : ""} onClick=${() => setParams({ tab: k })}>${l}${data && k !== "summary" ? html` <span class="faint small">${data[k]?.length ?? ""}</span>` : ""}</button>`)}</div>
      </div>
      <div class="d-b">
        ${error && html`<div class="empty">Could not load this project.</div>`}
        ${data && t === "summary" && html`<${Summary} d=${data} />`}
        ${data && t === "milestones" && html`<${Milestones} d=${data} asOf=${meta.as_of} />`}
        ${data && t === "updates" && html`<${Updates} d=${data} />`}
        ${data && t === "requests" && html`<${RequestList} d=${data} />`}
        ${data && t === "history" && html`<${History} d=${data} />`}
      </div>
    </aside></div>`;
}

function Summary({ d }) {
  const p = d.project;
  return html`
    ${d.risks.length > 0 && html`<div class="card"><div class="card-h"><h2>Open risks</h2></div><div class="list">${d.risks.map((r) => html`<div class="li" style="cursor:default"><${LevelPill} l=${r.risk_level} /><div class="grow"><div>${r.finding}</div><div class="small faint">${CATEGORY[r.category]} · ${CATEGORY_HELP[r.category]}</div></div></div>`)}</div></div>`}
    <dl class="kv">
      <dt>Team</dt><dd>${p.team_name} <span class="faint">· ${OFFICE[p.office]}, ${p.region}</span></dd>
      ${p.section && html`<dt>Section</dt><dd>${p.section}</dd>`}
      <dt>Owner</dt><dd>${p.owner_name}${p.owner_has_left ? html` <span class="pill bad">has left</span>` : ""}${p.owner_name_typed && p.owner_name_typed !== p.owner_name ? html` <span class="small faint">(typed as “${p.owner_name_typed}”)</span>` : ""}</dd>
      <dt>Executors</dt><dd>${p.executor_count}${p.external_executor_count ? html` <span class="faint">(${p.external_executor_count} external)</span>` : ""}</dd>
      <dt>Start</dt><dd>${fd(p.start_date)}</dd>
      <dt>Planned end</dt><dd>${fd(p.planned_end)}${p.extension_count ? html` <span class="faint">· originally ${fd(p.original_end)}, extended ${p.extension_count}× (+${p.days_extended} days)</span>` : ""}</dd>
      ${p.actual_end && html`<dt>Ended</dt><dd>${fd(p.actual_end)}</dd>`}
      <dt>Delivered</dt><dd><div style="max-width:260px"><${Prog} v=${p.delivery_ratio} /></div><span class="small faint">${p.milestones_accepted} of ${p.milestones_planned} milestones accepted${p.milestones_overdue ? `, ${p.milestones_overdue} overdue` : ""}${p.evidence_returns ? `, evidence returned ${p.evidence_returns}×` : ""}</span></dd>
      <dt>Status updates</dt><dd>${p.status_updates}${p.last_update_at ? html` <span class="faint">· last ${fd(p.last_update_at)}${p.days_since_update != null ? ` (${p.days_since_update} days ago)` : ""}</span>` : ""}</dd>
      <dt>Requests</dt><dd>${p.change_requests} changes (${p.changes_approved} approved), ${p.close_requests} close${p.requests_returned ? html` <span class="faint">· ${p.requests_returned} returned</span>` : ""}</dd>
      ${p.legacy_code && html`<dt>Legacy code</dt><dd class="mono">${p.legacy_code}</dd>`}
      <dt>Scope</dt><dd style="white-space:pre-wrap">${p.scope}</dd>
    </dl>`;
}

function Milestones({ d, asOf }) {
  if (!d.milestones.length) return html`<div class="empty">No milestones</div>`;
  const F = { text: "Text", screenshot: "Screenshot", email: "Email", file: "File" };
  return html`<div style="display:flex;flex-direction:column;gap:10px">${d.milestones.map((m) => {
    const cls = m.status === "accepted" ? "accepted" : m.is_overdue ? "overdue" : "";
    return html`<div class=${`ms ${cls}`} style=${m.status === "dropped" ? "opacity:.55" : ""}><span class="n">${m.seq}</span><div class="grow">
      <div class="row"><b style="font-weight:600">${m.name}</b><span style="flex:1"></span>
        ${m.status === "accepted" ? html`<span class="pill ok">Accepted ${fdShort(m.accepted_on)}</span>` : m.status === "dropped" ? html`<span class="pill neutral">Dropped</span>` : m.is_overdue ? html`<span class="pill bad">${m.days_overdue} days overdue</span>` : html`<span class="pill neutral">${m.status === "open" ? (days(m.due_date, asOf) >= 0 ? `due in ${days(m.due_date, asOf)} days` : "open") : m.status}</span>`}</div>
      <span class="small muted">Due ${fd(m.due_date)}${m.days_moved ? ` · moved ${m.days_moved > 0 ? "+" : ""}${m.days_moved} days from ${fd(m.original_due_date)}` : ""}</span>
      <span class="small faint">Evidence: ${(m.evidence_forms || "").split(",").filter(Boolean).map((f) => F[f] || f).join(", ")}${m.submissions ? ` · ${m.submissions} submission${m.submissions > 1 ? "s" : ""}` : ""}${m.times_returned ? `, returned ${m.times_returned}×` : ""}</span>
    </div></div>`;
  })}</div>`;
}

function Updates({ d }) {
  if (!d.updates.length) return html`<div class="empty">No status updates yet</div>`;
  return html`<div style="display:flex;flex-direction:column;gap:12px">${d.updates.map((u) => html`<div class="upd">
    <div class="upd-h"><b class="num">${fd(u.posted_at)}</b><span class="faint">for the ${OFFICE[u.meeting_track]?.toLowerCase() || ""} meeting of ${fdShort(u.meeting_date)}${u.posted_before_meeting ? "" : " · posted late"}</span><span style="flex:1"></span><span class="faint">${u.author}</span>
      ${u.stated_rag ? html`<span class="small muted">typed</span><${Rag} r=${u.stated_rag} />` : html`<span class="small faint">no colour typed</span>`}</div>
    <div class="upd-b">${u.body}</div>
    ${u.extractor && html`<div class="upd-s"><span class="ai"><${Icon} name="spark" />${u.extractor.startsWith("llm") ? "LLM" : "Rules"}</span>
      <span>reads</span><${Rag} r=${u.extracted_rag} />${u.extracted_blocked ? html`<span class="pill bad">Blocked</span>` : ""}
      ${u.stated_differs_from_content ? html`<span class="pill warn">differs from typed colour</span>` : ""}
      ${u.risks.map((r) => html`<span class=${`pill lv-${r.severity === "medium" ? "mid" : r.severity}`}>${r.category.replace(/_/g, " ")} · ${r.severity}</span>`)}
      ${u.extracted_next_milestone_date ? html`<span class="faint">next date ${fd(u.extracted_next_milestone_date)}</span>` : ""}</div>`}
  </div>`)}</div>`;
}

function RequestList({ d }) {
  if (!d.requests.length) return html`<div class="empty">No requests</div>`;
  return html`<div class="tw"><table class="t">
    <thead><tr><th>Submitted</th><th>Request</th><th>By</th><th>Outcome</th><th class="r">Days</th></tr></thead>
    <tbody>${d.requests.map((r) => html`<tr><td class="nowrap">${fd(r.submitted_at)}</td>
      <td>${KIND[r.request_kind]}${r.change_types ? html`<span class="faint"> · ${r.change_types.split(",").map((c) => CHANGE[c] || c).join(", ")}</span>` : ""}${r.request_version > 1 ? html` <span class="pill teal">v${r.request_version}</span>` : ""}${r.requested_new_end ? html`<div class="small faint">new end ${fd(r.requested_new_end)}</div>` : ""}${r.decision_comment ? html`<div class="small muted">${r.decision_comment}</div>` : ""}</td>
      <td class="nowrap">${r.submitted_by}</td><td><span class=${`pill ${REQ_CLASS[r.request_status]}`}>${REQ_STATUS[r.request_status]}</span></td><td class="r num">${n1(r.decision_days)}</td></tr>`)}</tbody>
  </table></div>`;
}

function History({ d }) {
  return html`<p class="small muted" style="margin:0">Each row is a version of the project in <span class="mono">dim_project_history</span> (slowly changing dimension, type 2): a new version whenever status, owner or planned end changed.</p>
    <div class="timeline">${d.history.map((h, i) => {
      const prev = d.history[i - 1];
      const changes = !prev ? ["Created"] : [prev.status !== h.status && html`Status <${StatusPill} s=${prev.status} /> <span class="arrow">→</span> <${StatusPill} s=${h.status} />`, prev.owner !== h.owner && `Owner ${prev.owner} → ${h.owner}`, prev.planned_end !== h.planned_end && `Planned end ${fd(prev.planned_end)} → ${fd(h.planned_end)}`].filter(Boolean);
      return html`<div class="tl"><span class="d">${fd(h.valid_from)}</span><div class="row" style="gap:6px">v${h.version_no} · ${changes.map((c, j) => html`${j ? html`<span class="faint">·</span>` : ""}<span>${c}</span>`)}${h.valid_to ? "" : html` <span class="pill info">current</span>`}</div></div>`;
    })}</div>`;
}

/* ------------------------------------------------------------------ shell */

const NAV = [
  ["Portfolio", [["overview", "Overview"], ["projects", "Projects"], ["timeline", "Timeline"], ["risks", "Risks"]]],
  ["Governance", [["biweekly", "Bi-weekly"], ["approvals", "Approvals"], ["board", "Strategic board"]]],
  ["Data", [["quality", "Data quality"]]],
];
const PAGES = { overview: Overview, projects: Projects, timeline: Timeline, risks: Risks, biweekly: Biweekly, approvals: Approvals, board: Board, quality: Quality };
const TITLE = Object.fromEntries(NAV.flatMap(([, items]) => items));

function Search() {
  const { data } = useData("projects");
  const [q, setQ] = useState(""), [open, setOpen] = useState(false), [i, setI] = useState(0);
  const res = useMemo(() => {
    const l = q.trim().toLowerCase();
    return !l || !data ? [] : data.filter((p) => p.code.toLowerCase().includes(l) || p.title.toLowerCase().includes(l)).slice(0, 8);
  }, [q, data]);
  const pick = (p) => { openProject(p.id); setQ(""); setOpen(false); };
  return html`<div class="search">
    <${Icon} name="search" />
    <input type="search" placeholder="Find a project" value=${q} aria-label="Find a project"
      onInput=${(e) => { setQ(e.target.value); setOpen(true); setI(0); }} onFocus=${() => setOpen(true)} onBlur=${() => setTimeout(() => setOpen(false), 150)}
      onKeyDown=${(e) => { if (e.key === "ArrowDown") { setI(Math.min(i + 1, res.length - 1)); e.preventDefault(); } else if (e.key === "ArrowUp") { setI(Math.max(i - 1, 0)); e.preventDefault(); } else if (e.key === "Enter" && res[i]) pick(res[i]); }} />
    ${open && res.length > 0 && html`<div class="res">${res.map((p, j) => html`<button class=${j === i ? "on" : ""} onMouseDown=${() => pick(p)}><span class="mono small faint" style="flex:none">${p.code}</span><span>${p.title}</span></button>`)}</div>`}
  </div>`;
}

function themeNow() {
  const t = document.documentElement.dataset.theme;
  return t || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function App() {
  const route = useRoute();
  const { data: meta, error } = useData("meta");
  const [menu, setMenu] = useState(false);
  const [theme, setTheme] = useState(themeNow());
  useTooltips();
  useEffect(() => { setMenu(false); window.scrollTo(0, 0); }, [route.view]);
  useEffect(() => { document.title = `${TITLE[route.view] || "Portal"} · Elvanor PMO`; }, [route.view]);
  const flip = () => {
    const t = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("pmo-theme", t); } catch (e) { /* storage may be blocked */ }
    setTheme(t);
  };
  if (error) return html`<div class="boot"><b>Could not load the portal data.</b><p>${String(error.message)}</p></div>`;
  if (!meta) return html`<div class="boot">Loading portfolio…</div>`;
  TEAM_OFFICE = Object.fromEntries(meta.teams.map((t) => [t.code, t.office]));
  const Page = PAGES[route.view] || Overview;
  return html`<div class="shell">
    <nav class=${`side ${menu ? "open" : ""}`} aria-label="Main">
      <div class="brand"><span class="mark"><svg viewBox="0 0 24 24" fill="none" stroke-width="2.6" stroke-linecap="round"><path d="M7 5h10M7 12h7M7 19h10M7 5v14" /></svg></span>
        <span><b>${meta.company}</b><small>After-sales PMO</small></span></div>
      ${NAV.map(([group, items]) => html`<div class="navgroup">${group}</div>${items.map(([v, l]) => html`<a class=${`nav ${route.view === v ? "on" : ""}`} href=${`#/${v}`} aria-current=${route.view === v ? "page" : null}><${Icon} name=${v} />${l}</a>`)}`)}
      <div class="side-foot">
        <span>Data as of <b class="num" style="color:var(--ink-2)">${fd(meta.as_of)}</b></span>
        <span>Fictional company, simulated data.</span>
        <a href="https://github.com/kkmonologue/pmo-portfolio-platform" class="row" style="gap:6px"><span style="width:15px;height:15px;display:inline-flex"><${Icon} name="github" /></span>Source on GitHub</a>
      </div>
    </nav>
    <div class="main">
      <header class="top">
        <button class="btn icon-btn menu-btn" onClick=${() => setMenu(!menu)} aria-label="Menu" aria-expanded=${menu}><${Icon} name="menu" /></button>
        <h1>${TITLE[route.view] || "Overview"}</h1><span class="sp"></span>
        <${Search} />
        <button class="btn icon-btn" onClick=${flip} aria-label=${`Switch to ${theme === "dark" ? "light" : "dark"} mode`}><${Icon} name=${theme === "dark" ? "sun" : "moon"} /></button>
      </header>
      <main class="content" onClick=${() => menu && setMenu(false)}><${Page} meta=${meta} params=${route.params} /></main>
    </div>
    ${route.params.p && html`<${ProjectDrawer} key=${route.params.p} id=${route.params.p} tab=${route.params.tab} meta=${meta} />`}
  </div>`;
}

render(html`<${App} />`, document.getElementById("app"));
