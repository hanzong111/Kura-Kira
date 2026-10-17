// Kura-Kira dashboard. Read-only: renders /api/status and /api/spends, refreshes on /api/events.
// Every number and money string comes from the server (duit.ledger + duit.money.fmt); this file only lays them out.
"use strict";

const $ = (id) => document.getElementById(id);
const FILTERS = ["person", "bucket", "category", "paid_by", "q"];
const state = { month: "", person: "", bucket: "", category: "", paid_by: "", q: "" };
let status = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const pct = (n, d) => (d > 0 ? Math.max(0, Math.min(1, n / d)) : n > 0 ? 1 : 0) * 100;
const unsign = (s) => String(s).replace(/^-/, "");

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

function syncURL() {
  const q = query();
  history.replaceState(null, "", q ? `?${q}` : location.pathname);
}

// ---- pieces -----------------------------------------------------------------------------------------
/** A clickable progress bar. `b` has spent/cap(+_fmt), left_fmt, status; `marker` is 0..1 or null. */
function bar(label, b, { marker = null, cap = "cap", big = false, person = "", bucket = "", sub = null, note = "" } = {}) {
  const capVal = b[cap], capFmt = b[`${cap}_fmt`];
  const over = b.spent > capVal;
  const subText = sub ?? (over ? `over by ${unsign(b.left_fmt)}` : `${b.left_fmt} left`);
  return `<button type="button" class="bar s-${esc(b.status)}${big ? " big" : ""}" data-person="${esc(person)}" data-bucket="${esc(bucket)}"
      title="Show ${esc(label)} spends">
    <span class="bar-top"><span class="bar-label">${esc(label)}</span>
      <span class="bar-nums num">${esc(b.spent_fmt)} / ${esc(capFmt)}</span></span>${note}
    <span class="bar-track"><span class="bar-fill" style="--w:${pct(b.spent, capVal)}%"></span>${
      marker == null ? "" : `<span class="bar-pace" style="--x:${(marker * 100).toFixed(1)}%" title="pace"></span>`}</span>
    <span class="bar-sub">${esc(subText)}</span>
  </button>`;
}

function stamp(label, amountFmt, kind, text) {
  return `<span class="stamp ${kind}"><span>${esc(label)} ${esc(amountFmt)}</span><b>${esc(text)}</b></span>`;
}

const goalBuckets = () => status.bucket_order.filter((b) => b.kind !== "fixed");
const fixedBuckets = () => status.bucket_order.filter((b) => b.kind === "fixed");
const name = (key) => status.people[key]?.name ?? key;

// ---- cards ------------------------------------------------------------------------------------------
function renderHeader() {
  $("day").textContent = `day ${status.day}/${status.days}`;
  for (const sel of [$("month"), $("f-month")]) {
    sel.innerHTML = status.months.map((m) => {
      const d = new Date(`${m}-01T00:00:00`);
      const label = d.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
      return `<option value="${m}"${m === status.month ? " selected" : ""}>${esc(label)}</option>`;
    }).join("");
  }
}

function renderCombined() {
  const c = status.combined, el = status.elapsed;
  const [a, b] = status.people_order;
  const paid = status.paid.people;
  const bigSub = `${c.goals.left_fmt} left · ${Math.round(el * 100)}% of the month gone`;
  const buckets = goalBuckets().map((x) => bar(x.label, c.buckets[x.key], { marker: el, bucket: x.key })).join("");
  const stamps = fixedBuckets().map((x) => {
    const f = c.buckets[x.key];
    const kind = f.paid === f.count ? "paid" : f.paid === 0 ? "due" : "part";
    const text = f.paid === f.count ? "PAID" : f.paid === 0 ? "DUE" : `${f.paid} of ${f.count} PAID`;
    return stamp(x.label, f.amount_fmt, kind, text);
  }).join("");
  const totalPaid = paid[a].total + paid[b].total + status.paid.unknown;
  const owes = status.balance.owes;
  $("combined-sub").textContent = `${status.combined.outflow_plan_fmt} plan incl. bills`;
  $("combined-body").innerHTML = `
    ${bar("Goals", c.goals, { marker: el, big: true, sub: bigSub })}
    <div class="bar-grid">${buckets}</div>
    <div class="combined-foot">
      <div class="stamps">${stamps}</div>
      <div class="paidby">
        <div class="section-title"><span>Who paid this month</span></div>
        <div class="split" role="img" aria-label="Paid by">
          <span class="pa" style="width:${pct(paid[a].total, totalPaid)}%"></span>
          <span class="pb" style="width:${pct(paid[b].total, totalPaid)}%"></span>
          <span class="pu" style="width:${pct(status.paid.unknown, totalPaid)}%"></span>
        </div>
        <div class="legend">
          <span><i style="background:var(--person-a)"></i>${esc(name(a))} paid <b class="num">${esc(paid[a].total_fmt)}</b></span>
          <span><i style="background:var(--person-b)"></i>${esc(name(b))} paid <b class="num">${esc(paid[b].total_fmt)}</b></span>
          ${status.paid.unknown ? `<span><i style="background:var(--unknown)"></i>payer unknown <b class="num">${esc(status.paid.unknown_fmt)}</b></span>` : ""}
        </div>
        <div class="owes">${owes ? `${esc(name(owes.from))} owes ${esc(name(owes.to))} <span class="num">${esc(owes.amount_fmt)}</span>` : "All square"}</div>
      </div>
    </div>`;
}

/** "target RM100.00 + RM20.00 saved = RM120.00 can spend" (carry from earlier weeks of the month). */
function carryNote(w) {
  const target = `target <span class="num">${esc(w.target_fmt)}</span>`;
  if (!w.carry) return `<span class="carry">${target}</span>`;
  const neg = w.carry < 0;
  const carry = `${neg ? "−" : "+"} <span class="num">${esc(unsign(w.carry_fmt))}</span> ${neg ? "overspent" : "saved"}`;
  return `<span class="carry">${target} <span class="${neg ? "carry-neg" : "carry-pos"}">${carry}</span>
    = <b class="num">${esc(w.allowance_fmt)}</b> can spend</span>`;
}

function weekRange(w) {
  const f = (s) => new Date(`${s}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return `${f(w.start)} – ${f(w.end)}`;
}

function renderPerson(key, mirror) {
  const p = status.people[key], el = status.elapsed;
  const weekly = goalBuckets().filter((b) => b.kind === "weekly");
  const monthly = goalBuckets().filter((b) => b.kind === "monthly");
  const anyWeek = weekly.map((b) => p.buckets[b.key].week).find(Boolean);
  const weekBars = weekly.map((b) => {
    const w = p.buckets[b.key].week;
    if (!w) return `<p class="muted week-none">${esc(b.label)}: no ${esc(b.label.toLowerCase())} days counted this week.</p>`;
    const sub = w.spent > w.allowance ? `over by ${unsign(w.left_fmt)} this week` : `${w.left_fmt} left this week`;
    return bar(b.label, w, { cap: "allowance", marker: w.days ? w.days_elapsed / w.days : null,
      person: key, bucket: b.key, sub, note: carryNote(w) });
  }).join("");
  // weekday/weekend over the month: spent against the sum of this month's week targets
  const monthBars = [...weekly, ...monthly].map((b) => bar(b.label, p.buckets[b.key],
    { marker: b.kind === "weekly" ? null : el, person: key, bucket: b.key })).join("");
  const stamps = fixedBuckets().map((b) => {
    const f = p.buckets[b.key];
    return stamp(b.label, f.amount_fmt, f.paid ? "paid" : "due", f.paid ? "PAID" : "DUE");
  }).join("");
  const initial = esc(p.name.slice(0, 1));
  return `<section class="card person${mirror ? " mirror" : ""}" aria-label="${esc(p.name)}">
    <div class="card-head">
      <span class="avatar" data-person="${esc(key)}">${initial}</span>
      <span>${esc(p.name)}</span>
      <span class="total"><span class="dot s-${esc(p.goals.status)}"></span> ${esc(p.goals.spent_fmt)} / ${esc(p.goals.cap_fmt)}</span>
    </div>
    <div class="card-body">
      <div class="section-title"><span>This week</span><span>${anyWeek ? esc(weekRange(anyWeek)) : ""}</span></div>
      ${status.today.startsWith(status.month) ? `<div class="two">${weekBars}</div>` : `<p class="muted">Not the current month.</p>`}
      <div class="section-title"><span>This month</span></div>
      ${bar("Total goals", p.goals, { marker: el, person: key })}
      <div class="two">${monthBars}</div>
      <div class="person-foot">
        <div class="stamps">${stamps}</div>
        ${p.unsorted ? `<button type="button" class="chip" data-person="${esc(key)}" data-bucket="unsorted">? Unsorted ${esc(p.unsorted_fmt)}</button>` : ""}
      </div>
    </div>
  </section>`;
}

function renderNeeds() {
  const items = status.pending.map((q) => {
    const asks = q.needs.map((n) => n === "bucket"
      ? `which bucket?${q.options.length ? " " + q.options.map((o) => `<span class="opt">${esc(o)}</span>`).join("") : ""}`
      : `who paid?${q.split ? ` <span class="muted">(${esc(q.split)})</span>` : ""}`);
    const d = new Date(`${q.spent_on}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
    return `<li><b>#${q.id} ${esc(q.place)}</b><span class="num">${esc(q.total_fmt)}</span>
      <span class="muted">${esc(q.who)} · ${esc(d)}</span><span class="q">${asks.join(" · ")}</span></li>`;
  });
  $("needs-list").innerHTML = items.join("") || `<li class="muted">Nothing to answer. All sorted.</li>`;
}

function renderStatus() {
  renderHeader();
  renderCombined();
  const [a, b] = status.people_order;
  $("people").innerHTML = renderPerson(a, false) + renderPerson(b, true);
  renderNeeds();
  fillFilterOptions();
}

// ---- table ------------------------------------------------------------------------------------------
function options(sel, first, items) {
  const cur = state[sel.name];
  sel.innerHTML = `<option value="">${esc(first)}</option>` +
    items.map(([v, l]) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(l)}</option>`).join("");
}

function fillFilterOptions() {
  const people = status.people_order.map((k) => [k, name(k)]);
  options($("f-person"), "Everyone", people);
  options($("f-bucket"), "All buckets", [...goalBuckets().map((b) => [b.key, b.label]), ["unsorted", "Unsorted"]]);
  options($("f-category"), "All categories", status.categories.map((c) => [c, c]));
  options($("f-paid"), "Anyone", [...people, ["each", "Each paid own"]]);
  $("f-q").value = state.q;
}

function renderSpends(d) {
  const share = d.person ? `${name(d.person)} share` : null;
  $("spends-head").innerHTML = `<tr><th>Date</th><th>Day</th><th>Who</th><th>Place / item</th><th>Bucket</th>
    <th>Category</th><th class="amt">Amount</th>${share ? `<th class="amt">${esc(share)}</th>` : ""}<th>Split</th><th>Paid by</th></tr>`;
  $("spends-rows").innerHTML = d.rows.map((r) => {
    const bucket = r.bucket ? esc(r.bucket_label) : `<span class="flag">? Unsorted</span>`;
    const payer = r.paid_by ? esc(r.paid_by_label) : `<span class="flag">? ask</span>`;
    const meta = [r.who, r.bucket_label, r.category, r.split, `paid ${r.paid_by_label}`]
      .concat(share ? [`${share} ${r.share_fmt}`] : []).filter(Boolean).map(esc).join(" · ");
    return `<tr>
      <td class="c-date num">${esc(r.date)}</td><td class="c-day">${esc(r.day)}</td>
      <td class="c-hide-sm">${esc(r.who)}</td>
      <td class="c-place"><b>${esc(r.place)}</b>${r.item ? `<span class="item">${esc(r.item)}</span>` : ""}</td>
      <td class="c-hide-sm">${bucket}</td><td class="c-hide-sm">${esc(r.category)}</td>
      <td class="c-amt amt num">${esc(r.total_sen_fmt)}</td>
      ${share ? `<td class="c-hide-sm amt num">${esc(r.share_fmt)}</td>` : ""}
      <td class="c-hide-sm split">${esc(r.split) || "—"}</td><td class="c-hide-sm">${payer}</td>
      <td class="c-meta">${meta}${r.needs.length ? ` <span class="flag">· needs ${esc(r.needs.join(" + "))}</span>` : ""}</td>
    </tr>`;
  }).join("");
  $("spends-empty").hidden = d.rows.length > 0;
  $("spends-count").textContent = `${d.count} spend${d.count === 1 ? "" : "s"}`;
  $("spends-summary").innerHTML = `${d.count} spend${d.count === 1 ? "" : "s"} · <span class="num">${esc(d.total_fmt)}</span>` +
    (share ? ` <span class="muted">(${esc(share)})</span>` : "");
  $("top-places").innerHTML = d.top_places.map((p) =>
    `<li><span>${esc(p.place)}<small>${p.count}×</small></span><span class="num">${esc(p.total_fmt)}</span></li>`).join("")
    || `<li class="muted">—</li>`;
  $("csv").href = `/api/spends.csv?${query()}`;
}

// ---- loading ----------------------------------------------------------------------------------------
async function loadStatus() {
  status = await getJSON(`/api/status?${new URLSearchParams(state.month ? { month: state.month } : {})}`);
  state.month = status.month;
  renderStatus();
}

async function loadSpends() {
  renderSpends(await getJSON(`/api/spends?${query()}`));
  syncURL();
}

let busy = null;
async function refresh() {
  if (busy) return busy;
  busy = Promise.all([loadStatus(), loadSpends()]).catch((e) => console.error(e)).finally(() => { busy = null; });
  return busy;
}

function filterTo(person, bucket) {
  Object.assign(state, { person, bucket, category: "", paid_by: "", q: "" });
  fillFilterOptions();
  loadSpends();
  $("spends").scrollIntoView({ behavior: "smooth", block: "start" });
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
  const t = e.target.closest("[data-bucket], [data-person].chip");
  if (t && (t.classList.contains("bar") || t.classList.contains("chip"))) filterTo(t.dataset.person || "", t.dataset.bucket || "");
});

for (const sel of [$("month"), $("f-month")]) {
  sel.addEventListener("change", () => { state.month = sel.value; refresh(); });
}
for (const id of ["f-person", "f-bucket", "f-category", "f-paid"]) {
  $(id).addEventListener("change", (e) => { state[e.target.name] = e.target.value; loadSpends(); });
}
let typing = null;
$("f-q").addEventListener("input", (e) => {
  clearTimeout(typing);
  typing = setTimeout(() => { state.q = e.target.value.trim(); loadSpends(); }, 250);
});
$("f-clear").addEventListener("click", () => { for (const k of FILTERS) state[k] = ""; fillFilterOptions(); loadSpends(); });

const initial = new URLSearchParams(location.search);
for (const k of ["month", ...FILTERS]) state[k] = initial.get(k) || "";
refresh().then(connect);
