// Kura-Kira dashboard in the DUIT Co-op Arcade look (duit/css/duit.css, docs/design/duit-arcade/).
// Read-only: renders /api/status and /api/spends, refreshes on /api/events. Every number and money string
// comes from the server (duit.ledger + duit.money.fmt); this file only lays them out.
"use strict";

const $ = (id) => document.getElementById(id);
const ASSETS = "duit/assets";
const FILTERS = ["person", "bucket", "category", "paid_by", "q"];
const state = { month: "", person: "", bucket: "", category: "", paid_by: "", q: "" };
let status = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const unsign = (s) => String(s).replace(/^-/, "");
const ratio = (n, d) => (d > 0 ? n / d : n > 0 ? Infinity : 0);
const pct = (n, d) => { const r = ratio(n, d); return Number.isFinite(r) ? Math.round(r * 100) : null; };
const fill = (n, d) => Math.max(0, Math.min(1, Number.isFinite(ratio(n, d)) ? ratio(n, d) : 1)) * 100;

// API status names -> design states
const STATES = { ok: "on-track", ahead: "ahead", over: "over" };
const STATE_LABEL = { "on-track": "On track", ahead: "Ahead of pace", over: "Over budget" };
const BUCKET_ICON = { weekday: "weekday", weekend: "weekend", extra: "extra", grocery: "grocery", chuchu: "paw",
                      petrol: "petrol", toll: "toll", parents: "parents", house: "house", car: "car" };
const SPRITES = ["hanz", "vanisa", "chuchu"];

const icon = (name, cls = "du-icon") => `<img class="${cls}" src="${ASSETS}/icons/${name}.svg" alt="" aria-hidden="true">`;
const sprite = (who, anim = "idle") => SPRITES.includes(who)
  ? `<span class="du-sprite" data-character="${who}" data-animation="${anim}" aria-hidden="true"></span>` : "";

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || r.statusText);
  return body;
}

function query(extra = {}) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...state, ...extra })) if (v) p.set(k, v);
  return p.toString();
}

const name = (key) => status.people[key]?.name ?? key;
const goalBuckets = () => status.bucket_order.filter((b) => b.kind !== "fixed");
const fixedBuckets = () => status.bucket_order.filter((b) => b.kind === "fixed");
const monthLabel = (m) => new Date(`${m}-01T00:00:00`).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
const shortDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

// ---- pieces -----------------------------------------------------------------------------------------
/** Progress meter: visual fill clamped to 0-100%, the real amounts in aria-valuetext. */
function meter(b, { cap = "cap", label, hero = false, pace = null, paceLabel = "" }) {
  const s = STATES[b.status] || "on-track";
  const capVal = b[cap];
  const p = pct(b.spent, capVal);
  const text = `${b.spent_fmt} of ${b[`${cap}_fmt`]} spent${p == null ? "" : `, ${p}%`}; ${STATE_LABEL[s]}` +
    (s === "over" ? `; ${unsign(b.left_fmt)} over` : "");
  const marker = pace == null ? "" : `<span class="du-marker" style="--pace:${(pace * 100).toFixed(2)}%" aria-hidden="true">${
    paceLabel ? `<span>${esc(paceLabel)}</span>` : ""}</span>`;
  return `<span class="du-meter du-status--${s}${hero ? " du-meter--hero" : ""}${s === "over" ? " du-meter--over" : ""}"
    style="--value:${fill(b.spent, capVal).toFixed(2)}%" role="progressbar" aria-label="${esc(label)}"
    aria-valuemin="0" aria-valuemax="${capVal}" aria-valuenow="${Math.max(0, Math.min(b.spent, capVal))}"
    aria-valuetext="${esc(text)}"><span class="du-meter-fill"></span>${marker}</span>`;
}

/** A bucket bar that filters the spending log when clicked. */
function budget(label, b, { cap = "cap", person = "", bucket = "", pace = null, note = "", foot = true, iconName = "" } = {}) {
  const over = b.spent > b[cap];
  const p = pct(b.spent, b[cap]);
  const footer = over
    ? `<span class="du-budget-foot"><span class="du-tag du-tag--over">OVER</span><span>${esc(unsign(b.left_fmt))} over</span></span>`
    : foot ? `<span class="du-budget-foot"><span>${p == null ? "No budget set" : `${p}%`}</span><span>${esc(b.left_fmt)} left</span></span>` : "";
  return `<button type="button" class="du-budget kk-hit" data-person="${esc(person)}" data-bucket="${esc(bucket)}"
      title="Show ${esc(label)} spends">
    <span class="du-budget-label"><strong>${iconName ? icon(iconName, "du-icon kk-bucket-icon") : ""}${esc(label)}</strong>
      <span class="du-budget-value">${esc(b.spent_fmt)} / ${esc(b[`${cap}_fmt`])}</span></span>
    ${note}${meter(b, { cap, label, pace })}${footer}
  </button>`;
}

/** "target RM100.00 + RM20.00 saved = RM120.00 can spend" (carry-over from earlier weeks of the month). */
function carryNote(w) {
  const target = `target <span class="du-number">${esc(w.target_fmt)}</span>`;
  if (!w.carry) return `<span class="kk-carry">${target}</span>`;
  const neg = w.carry < 0;
  return `<span class="kk-carry">${target} <span class="${neg ? "kk-carry-neg" : "kk-carry-pos"}">${neg ? "−" : "+"}
    <span class="du-number">${esc(unsign(w.carry_fmt))}</span> ${neg ? "overspent" : "saved"}</span>
    = <b class="du-number">${esc(w.allowance_fmt)}</b> can spend</span>`;
}

function bill(label, iconName, kind, text) {
  return `<span class="du-badge">${icon(iconName)}<span>${esc(label)}</span><span class="du-tag du-tag--${kind}">${esc(text)}</span></span>`;
}

const legend = `<div class="du-legend">${Object.entries(STATE_LABEL).map(([s, l]) =>
  `<span><i class="du-swatch du-status--${s}" aria-hidden="true"></i>${l}</span>`).join("")}</div>`;

// ---- header -----------------------------------------------------------------------------------------
function renderHeader() {
  $("party").innerHTML = sprite(status.people_order[0]) + sprite("chuchu") + sprite(status.people_order[1]);
  $("day").textContent = `day ${status.day}/${status.days}`;
  const opts = status.months.map((m) => `<option value="${m}"${m === status.month ? " selected" : ""}>${esc(monthLabel(m))}</option>`).join("");
  $("month").innerHTML = opts;
  $("f-month").innerHTML = opts;
  const i = status.months.indexOf(status.month);  // newest first
  $("month-prev").disabled = i < 0 || i >= status.months.length - 1;
  $("month-next").disabled = i <= 0;
}

// ---- combined ---------------------------------------------------------------------------------------
function renderCombined() {
  const c = status.combined, el = status.elapsed;
  const g = c.goals;
  const p = pct(g.spent, g.cap);
  const buckets = goalBuckets().map((b) => budget(b.label, c.buckets[b.key], { bucket: b.key, pace: el })).join("");
  const bills = fixedBuckets().map((b) => {
    const f = c.buckets[b.key];
    const [kind, text] = f.paid === f.count ? ["paid", "PAID"] : f.paid === 0 ? ["due", "DUE"] : ["partial", `${f.paid} of ${f.count} PAID`];
    return bill(b.label, BUCKET_ICON[b.key] || "receipt", kind, `${f.amount_fmt} · ${text}`);
  }).join("");
  $("combined").innerHTML = `
    <div class="du-combined-head">
      <h2 id="combined-title" class="du-combined-heading">${icon("coin-stack", "du-icon du-icon--large")}COMBINED</h2>
      <div>
        <div class="du-total-line">
          <strong class="du-number">${esc(g.spent_fmt)} / ${esc(g.cap_fmt)} spent${p == null ? "" : ` (${p}%)`}</strong>${legend}
        </div>
        <button type="button" class="kk-hit kk-hero" data-person="" data-bucket="" title="Show all spends">
          ${meter(g, { label: "Combined monthly goals", hero: true, pace: el, paceLabel: `Month ${Math.round(el * 100)}%` })}
        </button>
      </div>
    </div>
    <div class="du-buckets">${buckets}</div>
    <footer class="du-combined-footer">
      <div class="du-bills"><strong>Fixed bills:</strong>${bills}</div>
    </footer>`;
}

// ---- who paid ---------------------------------------------------------------------------------------
// The personal cards show what each person bears (shared buckets split half each); this shows the money
// that actually left each person's pocket, and what for.
function renderPaid() {
  const pd = status.paid, order = status.people_order;
  const sum = order.reduce((n, k) => n + pd.people[k].total, 0);
  const accent = (i) => (i === 0 ? "var(--du-hanz)" : "var(--du-vanisa)");
  const segs = order.map((k, i) => {
    const t = pd.people[k].total, w = sum ? (t / sum) * 100 : 100 / order.length;
    return `<span class="kk-paid-seg" style="--w:${w.toFixed(2)}%;--c:${accent(i)}" title="${esc(name(k))} ${esc(pd.people[k].total_fmt)}"></span>`;
  }).join("");
  const keys = order.map((k, i) => `<span class="kk-paid-key"><i style="--c:${accent(i)}" aria-hidden="true"></i>
    ${esc(name(k))} paid <b class="du-number">${esc(pd.people[k].total_fmt)}</b>${sum ? ` <span class="kk-muted">(${pct(pd.people[k].total, sum)}%)</span>` : ""}</span>`).join("");
  const label = (k) => (k === "unsorted" ? "Unsorted" : status.bucket_order.find((b) => b.key === k)?.label ?? k);
  const amt = (v) => (v.amount ? `<span class="du-number">${esc(v.amount_fmt)}</span>` : `<span class="kk-muted">–</span>`);
  const rows = pd.rows.map((r) => `<tr><th scope="row">${icon(BUCKET_ICON[r.bucket] || "receipt")}${esc(label(r.bucket))}</th>
    ${order.map((k) => `<td>${amt(r.people[k])}</td>`).join("")}</tr>`).join("");
  const totals = `<tr class="kk-paid-total"><th scope="row">Total</th>${order.map((k) =>
    `<td><span class="du-number">${esc(pd.people[k].total_fmt)}</span></td>`).join("")}</tr>`;
  const unknown = pd.unknown ? `<p class="kk-muted">Payer not known yet: <b class="du-number">${esc(pd.unknown_fmt)}</b></p>` : "";
  const transfers = pd.transfers.length ? `<div class="kk-transfers"><strong>Money handed over:</strong>${pd.transfers.map((t) =>
    `<span class="du-badge">${icon("swap")}${esc(name(t.from))} → ${esc(name(t.to))} <b class="du-number">${esc(t.amount_fmt)}</b>
      <span class="kk-muted">${esc(shortDate(t.on))}${t.note ? ` · ${esc(t.note)}` : ""}</span></span>`).join("")}</div>` : "";
  const owes = status.balance.owes;
  $("whopaid").innerHTML = `
    <header class="du-panel-title"><h2 id="paid-title">${icon("coin-stack")} WHO PAID</h2></header>
    <div class="kk-paid-body">
      <div class="kk-paid-bar" role="img" aria-label="${esc(order.map((k) => `${name(k)} paid ${pd.people[k].total_fmt}`).join(", "))}">${segs}</div>
      <div class="kk-paid-keys">${keys}</div>
      <table class="du-table kk-paid-table">
        <thead><tr><th scope="col">For</th>${order.map((k) => `<th scope="col">${esc(name(k))}</th>`).join("")}</tr></thead>
        <tbody>${rows || `<tr><td colspan="${order.length + 1}" class="kk-muted">Nothing paid yet this month.</td></tr>`}${totals}</tbody>
      </table>
      ${unknown}${transfers}
      <span class="du-badge du-settle">${icon("swap")}${owes
        ? `${esc(name(owes.from))} owes ${esc(name(owes.to))} <span class="du-number">${esc(owes.amount_fmt)}</span>`
        : "All square"}</span>
    </div>`;
}

// ---- personal cards ---------------------------------------------------------------------------------
function renderPerson(key, i) {
  const p = status.people[key], el = status.elapsed;
  const accent = i === 0 ? "var(--du-hanz)" : "var(--du-vanisa)";
  const weekly = goalBuckets().filter((b) => b.kind === "weekly");
  const monthly = goalBuckets().filter((b) => b.kind === "monthly");
  const current = status.today.startsWith(status.month);
  const week = weekly.map((b) => p.buckets[b.key].week).find(Boolean);
  const weekBars = !current ? `<p class="kk-muted">Not the current month.</p>` : weekly.map((b) => {
    const w = p.buckets[b.key].week;
    if (!w) return `<p class="kk-muted">${esc(b.label)}: no ${esc(b.label.toLowerCase())} days counted this week.</p>`;
    return budget(b.label, w, { cap: "allowance", person: key, bucket: b.key, note: carryNote(w),
      pace: w.days ? w.days_elapsed / w.days : null, iconName: BUCKET_ICON[b.key] });
  }).join("");
  // weekday/weekend over the whole month: spent against the sum of this month's week targets
  const mini = [...weekly, ...monthly].map((b) => budget(b.label, p.buckets[b.key],
    { person: key, bucket: b.key, pace: b.kind === "weekly" ? null : el, foot: false })).join("");
  const bills = fixedBuckets().map((b) => {
    const f = p.buckets[b.key];
    return bill(b.label, BUCKET_ICON[b.key] || "receipt", f.paid ? "paid" : "due", f.paid ? "PAID" : "DUE");
  }).join("");
  const unsorted = p.unsorted ? `<button type="button" class="du-badge du-unsorted kk-hit" data-person="${esc(key)}" data-bucket="unsorted">
    ${icon("receipt")}Unsorted <span class="du-number">${esc(p.unsorted_fmt)}</span></button>` : "";
  const g = p.goals;
  return `<section class="du-panel" style="--accent:${accent}" aria-labelledby="${esc(key)}-title">
    <header class="du-panel-title">
      <span class="du-player">P${i + 1}</span>${sprite(key)}
      <h2 id="${esc(key)}-title">${esc(p.name.toUpperCase())}</h2>${i === 1 ? sprite("chuchu") : ""}
      <span class="du-heart">${icon("heart")}</span>
    </header>
    <div class="du-partner-body">
      <div class="du-week">
        <h3 class="du-section-label">This week${week ? ` <span class="kk-muted kk-range">${esc(shortDate(week.start))} – ${esc(shortDate(week.end))}</span>` : ""}</h3>
        ${weekBars}
      </div>
      <div>
        <div class="du-month-total"><h3>This month</h3><span class="du-number">${esc(g.spent_fmt)} / ${esc(g.cap_fmt)}</span></div>
        <button type="button" class="kk-hit kk-hero" data-person="${esc(key)}" data-bucket="" title="Show ${esc(p.name)}'s spends">
          ${meter(g, { label: `${p.name} monthly goals`, pace: el })}</button>
        <div class="du-mini-buckets">${mini}</div>
      </div>
    </div>
    <footer class="du-partner-footer"><strong>Fixed bills:</strong>${bills}${unsorted}</footer>
  </section>`;
}

// ---- needs answer -----------------------------------------------------------------------------------
function renderNeeds() {
  const box = $("needs");
  const items = status.pending.map((q) => {
    const asks = q.needs.map((n) => n === "bucket"
      ? `${q.options.length ? q.options.map((o) => `<span class="du-tag">${esc(o)}</span>`).join(" or ") : "which bucket"}?`
      : `who paid?${q.split ? ` <span class="kk-muted">(${esc(q.split)})</span>` : ""}`);
    return `<li><b>${esc(q.place)}</b> <span class="du-number">${esc(q.total_fmt)}</span> · ${esc(q.who)} · ${esc(shortDate(q.spent_on))}:
      ${asks.join(" · ")}</li>`;
  });
  box.hidden = false;
  box.innerHTML = items.length
    ? `${icon("question")}<h2 id="needs-title">Needs answer:</h2>
       <ul class="du-question-text kk-questions">${items.join("")}</ul>
       <p class="kk-muted kk-telegram">Answer in the Telegram group.</p>`
    : `${sprite("chuchu", "sleep")}<h2 id="needs-title">Needs answer:</h2>
       <p class="du-question-text">Nothing to answer. All sorted.</p>`;
}

// ---- spending log -----------------------------------------------------------------------------------
function options(sel, first, items) {
  const cur = state[sel.name];
  sel.innerHTML = `<option value="">${esc(first)}</option>` +
    items.map(([v, l]) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(l)}</option>`).join("");
}

function fillFilterOptions() {
  const people = status.people_order.map((k) => [k, name(k)]);
  options($("f-person"), "Who", people);
  options($("f-bucket"), "Bucket", [...goalBuckets().map((b) => [b.key, b.label]), ["unsorted", "Unsorted"]]);
  options($("f-category"), "Category", status.categories.map((c) => [c, c]));
  options($("f-paid"), "Paid by", [...people, ["each", "Each paid own"]]);
  $("f-q").value = state.q;
}

function renderSpends(d) {
  const share = d.person ? `${name(d.person)} share` : null;
  const heads = ["Date", "Day", "Who", "Place / item", "Bucket", "Category", "Amount", ...(share ? [share] : []), "Split", "Paid by"];
  $("spends-head").innerHTML = `<tr>${heads.map((h) => `<th scope="col"${h === "Amount" || h === share ? ' class="du-amount"' : ""}>${esc(h)}</th>`).join("")}</tr>`;
  const bucketCell = (r) => (r.bucket ? esc(r.bucket_label) : `<span class="du-tag du-tag--due">Unsorted</span>`);
  const payerCell = (r) => (r.paid_by ? esc(r.paid_by_label) : `<span class="du-tag du-tag--due">ask</span>`);
  const place = (r) => esc(r.place) + (r.item ? ` <span class="kk-muted">(${esc(r.item)})</span>` : "");
  $("spends-rows").innerHTML = d.rows.map((r) => `<tr>
      <td>${esc(r.date)}</td><td>${esc(r.day)}</td><td>${esc(r.who)}</td><td>${place(r)}</td>
      <td>${bucketCell(r)}</td><td>${esc(r.category) || "—"}</td>
      <td class="du-amount">${esc(r.total_sen_fmt)}</td>${share ? `<td class="du-amount">${esc(r.share_fmt)}</td>` : ""}
      <td>${esc(r.split) || "—"}</td><td>${payerCell(r)}</td></tr>`).join("");
  $("spends-cards").innerHTML = d.rows.map((r) => `<article class="du-entry">
      <div class="du-entry-head"><span>${esc(r.date)} · ${esc(r.day)} · ${esc(r.who)}</span><span class="du-number">${esc(r.total_sen_fmt)}</span></div>
      <h3 class="du-entry-title">${place(r)}</h3>
      <p class="du-entry-meta">${bucketCell(r)} · ${esc(r.category) || "—"} · Paid by ${payerCell(r)}${share ? ` · ${esc(share)} ${esc(r.share_fmt)}` : ""}</p>
      <p class="du-entry-split">Split: ${esc(r.split) || "—"}</p></article>`).join("");
  $("spends-empty").hidden = d.rows.length > 0;
  $("spends-summary").innerHTML = `${d.count} spend${d.count === 1 ? "" : "s"} · <span class="du-number">${esc(d.total_fmt)}</span>` +
    (share ? ` <span class="kk-muted">(${esc(share)})</span>` : "");
  $("top-places").innerHTML = d.top_places.map((p, i) => `<div class="du-place">
      <span class="du-medal" aria-label="Rank ${i + 1}">${i + 1}</span>${icon(BUCKET_ICON[p.bucket] || "receipt")}
      <div>${esc(p.place)}<br><strong class="du-number">${p.count}x ${esc(p.total_fmt)}</strong></div></div>`).join("")
    || `<p class="du-empty">No places yet.</p>`;
  $("csv").href = `/api/spends.csv?${query()}`;
}

// ---- loading ----------------------------------------------------------------------------------------
let lastGood = null;
function markStale(err) {
  const el = $("stale");
  el.hidden = false;
  el.textContent = lastGood
    ? `Couldn't refresh (${err.message}). Showing figures from ${lastGood.toLocaleTimeString()}.`
    : `Couldn't load the ledger: ${err.message}`;
}

async function loadStatus() {
  status = await getJSON(`/api/status?${new URLSearchParams(state.month ? { month: state.month } : {})}`);
  state.month = status.month;
  renderHeader();
  renderCombined();
  $("partners").innerHTML = status.people_order.map(renderPerson).join("");
  renderPaid();
  renderNeeds();
  fillFilterOptions();
}

async function loadSpends() {
  renderSpends(await getJSON(`/api/spends?${query()}`));
  const q = query();
  history.replaceState(null, "", q ? `?${q}` : location.pathname);
}

let busy = null;
function refresh() {
  if (busy) return busy;
  busy = loadStatus().then(loadSpends)
    .then(() => { lastGood = new Date(); $("stale").hidden = true; })
    .catch(markStale)
    .finally(() => { busy = null; });
  return busy;
}

function filterTo(person, bucket) {
  Object.assign(state, { person, bucket, category: "", paid_by: "", q: "" });
  fillFilterOptions();
  loadSpends().catch(markStale);
  $("spends").scrollIntoView({ behavior: "smooth", block: "start" });
}

function goMonth(month) {
  if (!month || month === state.month) return;
  state.month = month;
  refresh();
}

// ---- live updates: SSE when the ledger file changes, polling every 3 s if SSE drops ---------------
let pollTimer = null;
function setLive(s, text) { $("live").dataset.s = s; $("live").querySelector("span").textContent = text; }
function startPolling() {
  if (pollTimer) return;
  setLive("poll", "polling");
  pollTimer = setInterval(refresh, 3000);
}
function connect() {
  if (!window.EventSource) return startPolling();
  const es = new EventSource("/api/events");
  es.addEventListener("hello", () => {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; refresh(); }
    setLive("live", "live");
  });
  es.addEventListener("change", refresh);
  es.onerror = () => startPolling();
}

// ---- wiring -----------------------------------------------------------------------------------------
document.addEventListener("click", (e) => {
  const t = e.target.closest(".kk-hit");
  if (t) filterTo(t.dataset.person || "", t.dataset.bucket || "");
});
document.addEventListener("animationend", (e) => {
  if (e.target.dataset?.animation === "wave") e.target.dataset.animation = "idle";
});

$("month").addEventListener("change", (e) => goMonth(e.target.value));
$("f-month").addEventListener("change", (e) => goMonth(e.target.value));
$("month-prev").addEventListener("click", () => goMonth(status.months[status.months.indexOf(state.month) + 1]));
$("month-next").addEventListener("click", () => goMonth(status.months[status.months.indexOf(state.month) - 1]));
for (const id of ["f-person", "f-bucket", "f-category", "f-paid"]) {
  $(id).addEventListener("change", (e) => { state[e.target.name] = e.target.value; loadSpends().catch(markStale); });
}
let typing = null;
$("f-q").addEventListener("input", (e) => {
  clearTimeout(typing);
  typing = setTimeout(() => { state.q = e.target.value.trim(); loadSpends().catch(markStale); }, 250);
});
$("f-clear").addEventListener("click", () => { for (const k of FILTERS) state[k] = ""; fillFilterOptions(); loadSpends().catch(markStale); });

const initial = new URLSearchParams(location.search);
for (const k of ["month", ...FILTERS]) state[k] = initial.get(k) || "";
refresh().then(connect);
