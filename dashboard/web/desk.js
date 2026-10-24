// Desktop layout of the dashboard (shown from 768px by desk.css; phones get phone.js). Same contract as
// phone.js: it reuses app.js's data and helpers (`status`, `state`, `esc`, `icon`, `name`, `loadSpends`,
// `goMonth` and friends), app.js calls kkDesk.status() / .spends(d) / .stale(text) after each load, and
// nothing here adds money up: every figure is one the server computed. Edit buttons open app.js's kkEdit.
"use strict";

window.kkDesk = (() => {
  const root = document.getElementById("desk");
  const ACCENTS = ["var(--du-coral)", "var(--du-teal)", "var(--du-yellow)", "var(--du-blue)"];
  const STATE_CLASS = { ok: "ok", ahead: "ahead", over: "over" };
  const STATE_TAG = { ok: "On track", ahead: "Ahead of pace", over: "Over budget" };
  const view = { who: "", stale: "" };
  let spends = null;
  let built = false;

  const accent = (key) => ACCENTS[Math.max(0, status.people_order.indexOf(key)) % ACCENTS.length];
  const dot = (key) => `<i class="pm-dot" style="--c:${accent(key)}" aria-hidden="true"></i>`;
  const current = () => status.today.startsWith(status.month);
  const scope = () => (view.who ? status.people[view.who] : status.combined);
  const people = () => (view.who ? [view.who] : status.people_order);
  const shared = () => status.people_order.length > 1;
  const fillPct = (n, d) => (d > 0 ? Math.max(0, Math.min(100, (n / d) * 100)) : n > 0 ? 100 : 0);
  const unsigned = (fmt) => String(fmt).replace(/^-/, "");
  const money = (n, fmt) => (n < 0 ? `<span class="pm-over">${esc(unsigned(fmt))} over</span>` : esc(fmt));
  const bucketLabel = (k) => (k === "unsorted" ? "No bucket yet" : status.bucket_order.find((b) => b.key === k)?.label ?? k);
  const $d = (sel) => root.querySelector(sel);

  function bar(spent, cap, st, pace, label) {
    const marker = pace == null ? "" : `<i class="pm-pace" style="--p:${(Math.min(1, pace) * 100).toFixed(1)}%" aria-hidden="true"></i>`;
    return `<span class="pm-bar pm-${STATE_CLASS[st] || "ok"}" role="progressbar" aria-label="${esc(label)}"
      aria-valuemin="0" aria-valuemax="${cap}" aria-valuenow="${Math.max(0, Math.min(spent, cap))}">
      <i style="--w:${fillPct(spent, cap).toFixed(1)}%"></i>${marker}</span>`;
  }

  // ---- header -----------------------------------------------------------------------------------------
  function header() {
    const months = status.months.map((m) => `<option value="${m}"${m === status.month ? " selected" : ""}>${esc(monthLabel(m))}</option>`).join("");
    const i = status.months.indexOf(status.month);  // newest first
    const live = document.getElementById("live");
    const who = shared() ? [["", status.people_order.length > 2 ? "Everyone" : "Both"], ...status.people_order.map((k) => [k, name(k)])] : [];
    return `<div class="dk-wrap dk-head-row">
      <div class="dk-brand"><img class="dk-logo" src="${ASSETS}/brand/duit-cream.svg" alt="DUIT" width="132" height="40">
        <div><h1>${esc(status.household?.name || status.people_order.map(name).join(" & "))}</h1>
          <p class="dk-sub"><span>Day ${status.day} of ${status.days}</span>
            <span class="kk-live" data-s="${esc(live?.dataset.s || "off")}"><i aria-hidden="true"></i><span>${esc(live?.textContent.trim() || "")}</span></span></p></div></div>
      <div class="dk-month">
        <button type="button" class="pm-icon-btn pm-coral" data-act="month" data-month="${esc(status.months[i + 1] || "")}"
          aria-label="Previous month"${i >= status.months.length - 1 ? " disabled" : ""}>${icon("arrow-left")}</button>
        <label><span class="du-sr-only">Budget month</span><select data-act="pick-month">${months}</select></label>
        <button type="button" class="pm-icon-btn pm-coral" data-act="month" data-month="${esc(status.months[i - 1] || "")}"
          aria-label="Next month"${i <= 0 ? " disabled" : ""}>${icon("arrow-right")}</button>
      </div>
      ${who.length ? `<div class="pm-switch" role="group" aria-label="Whose budget">${who.map(([k, label]) =>
        `<button type="button" data-act="who" data-who="${esc(k)}" aria-pressed="${view.who === k}">${k ? dot(k) : ""}${esc(label)}</button>`).join("")}</div>` : ""}
    </div>`;
  }

  // ---- answer cards -----------------------------------------------------------------------------------
  function pending() {
    if (!status.pending.length) return "";
    const items = status.pending.map((q) => `<li><b>${esc(q.place)}</b> ${esc(q.total_fmt)} · ${esc(q.who)} · ${esc(shortDate(q.spent_on))}:
      ${q.needs.map((n) => (n === "bucket" ? (q.options.length ? esc(q.options.join(" or ")) + "?" : "which bucket?") : "who paid?")).join(" · ")}</li>`).join("");
    return `<section class="pm-card pm-pending" aria-labelledby="dk-needs">${icon("question")}
      <div><h2 id="dk-needs" class="pm-pending-title">${status.pending.length} need${status.pending.length === 1 ? "s" : ""} an answer</h2>
      <ul>${items}</ul><p>Answer it in Telegram.</p></div></section>`;
  }

  function hero() {
    const g = scope().goals;
    const used = g.cap ? Math.round((g.spent / g.cap) * 100) : 0;
    return `<section class="pm-card pm-hero dk-card" aria-labelledby="dk-left">
      <div class="pm-row"><h2 id="dk-left" class="pm-label">${esc(view.who ? `${name(view.who)} · left this month` : "Left this month")}</h2>
        <span class="pm-tag pm-${STATE_CLASS[g.status] || "ok"}">${STATE_TAG[g.status] || "On track"}</span></div>
      <p class="pm-big">${money(g.left, g.left_fmt)}</p>
      <p class="pm-muted">of ${esc(g.cap_fmt)} · spent ${esc(g.spent_fmt)} (${used}%)</p>
      ${bar(g.spent, g.cap, g.status, current() ? g.pace ?? status.elapsed : null, "Month spent")}
      ${current() ? `<p class="pm-small pm-muted dk-right">▲ ${Math.round(status.elapsed * 100)}% of the month gone</p>` : ""}
    </section>`;
  }

  function week() {
    const weekly = goalBuckets().filter((b) => b.kind === "weekly");
    if (!weekly.length || !current()) return "";
    let range = "";
    const blocks = weekly.map((b) => {
      const rows = people().map((k) => {
        const w = status.people[k].buckets[b.key]?.week;
        if (!w) return "";
        range = `${shortDate(w.start)} – ${shortDate(w.end)}`;
        const carry = w.carry ? ` · ${w.carry < 0 ? "−" : "+"}${esc(unsigned(w.carry_fmt))} ${w.carry < 0 ? "overspent" : "saved"}` : "";
        return `<span class="dk-week-person">${view.who || !shared() ? "" : `<span class="pm-small">${dot(k)}${esc(name(k))}</span>`}
          <span class="pm-mid">${money(w.left, w.left_fmt)}</span>
          <span class="pm-small pm-muted">of ${esc(w.allowance_fmt)}${carry}</span>
          ${bar(w.spent, w.allowance, w.status, w.days ? w.days_elapsed / w.days : null, `${name(k)} ${b.label} this week`)}</span>`;
      }).join("");
      return rows ? `<button type="button" class="dk-week" data-act="filter" data-person="${esc(view.who)}" data-bucket="${esc(b.key)}"
          title="Show ${esc(b.label)} spends"><span class="pm-week-title">${icon(BUCKET_ICON[b.key] || "receipt")}${esc(b.label)}</span>
          <span class="dk-week-people">${rows}</span></button>` : "";
    }).join("");
    return blocks ? `<section class="pm-card dk-card" aria-labelledby="dk-week">
      <h2 id="dk-week" class="pm-label pm-row"><span>Can spend this week</span><span class="pm-plain pm-muted">${esc(range)}</span></h2>
      ${blocks}</section>` : "";
  }

  function settle() {
    const owes = status.balance.owes;
    return `<section class="pm-card pm-settle dk-card dk-settle" aria-labelledby="dk-settle">
      <h2 id="dk-settle" class="pm-label dk-icon-title">${icon("swap")}To settle up</h2>
      <p class="pm-big dk-settle-line">${owes ? `${esc(name(owes.from))} owes ${esc(name(owes.to))} ${esc(owes.amount_fmt)}` : "All square"}</p>
      <p class="pm-small">${owes ? "Already paid back? Tell Kura-Kira in Telegram." : "Nobody owes anybody for this month."}</p>
    </section>`;
  }

  // ---- budgets table ----------------------------------------------------------------------------------
  function budgets() {
    const s = scope();
    const pace = current() ? status.elapsed : null;
    const rows = goalBuckets().map((b) => {
      const v = s.buckets[b.key];
      if (!v) return "";
      const split = !view.who && shared()
        ? `<span class="pm-small pm-muted">${status.people_order.map((k) => `${esc(name(k))} ${esc(status.people[k].buckets[b.key]?.spent_fmt ?? "–")}`).join(" · ")}</span>` : "";
      return `<button type="button" class="dk-grid dk-row" data-act="filter" data-person="${esc(view.who)}" data-bucket="${esc(b.key)}"
          title="Show ${esc(b.label)} spends">${icon(BUCKET_ICON[b.key] || "receipt")}
        <span class="pm-name">${esc(b.label)}${split}</span>
        ${bar(v.spent, v.cap, v.status, b.kind === "weekly" ? null : pace, b.label)}
        <span class="dk-num">${esc(v.spent_fmt)} / ${esc(v.cap_fmt)}</span><b class="dk-num">${money(v.left, v.left_fmt)}</b></button>`;
    }).join("");
    const unsorted = s.unsorted ? `<button type="button" class="dk-grid dk-row" data-act="filter" data-person="${esc(view.who)}" data-bucket="unsorted">
        ${icon("receipt")}<span class="pm-name">No bucket yet<span class="pm-small pm-muted">Not in any budget until it's answered</span></span>
        <span></span><span class="dk-num">${esc(s.unsorted_fmt)}</span><span></span></button>` : "";
    // an installment (a fixed bill that runs for set months) gets a bar for the whole plan, not just this month
    const plans = fixedBuckets().filter((b) => s.buckets[b.key]?.installment).map((b) => {
      const i = s.buckets[b.key].installment;
      return `<div class="dk-grid dk-plan">${icon(BUCKET_ICON[b.key] || "receipt")}
        <span class="pm-name">${esc(b.label)}<span class="pm-small pm-muted">Installment · ${i.done} of ${i.count} paid</span></span>
        ${bar(i.spent, i.total, "ok", null, `${b.label} installment`)}
        <span class="dk-num">${esc(i.spent_fmt)} / ${esc(i.total_fmt)}</span><b class="dk-num">${esc(i.left_fmt)}</b></div>`;
    }).join("");
    const bills = fixedBuckets().filter((b) => s.buckets[b.key]).map((b) => {
      const f = s.buckets[b.key];
      const count = f.count ?? 1;
      const [cls, text] = f.paid === count || f.paid === true ? ["ok", "Paid"] : !f.paid ? ["over", "Due"] : ["ahead", `${f.paid} of ${count} paid`];
      const i = f.installment;
      const tip = [b.label, f.amount_fmt, i && `${i.spent_fmt} / ${i.total_fmt} paid, ${i.done} of ${i.count} installments`, text].filter(Boolean).join(" · ");
      const tag = status.editable ? "button" : "span";
      return `<${tag}${tag === "button" ? ` type="button" data-act="plan" data-bucket="${esc(b.key)}"` : ""} class="dk-bill"
        title="${esc(tip)}${status.editable ? " · click to change" : ""}">${icon(BUCKET_ICON[b.key] || "receipt")}<span>${esc(b.label)}</span>
        ${f.amount_fmt ? `<b class="dk-num">${esc(f.amount_fmt)}</b>` : ""}<span class="pm-tag pm-${cls}">${text}</span></${tag}>`;
    }).join("");
    return `<section class="pm-card dk-budgets" aria-labelledby="dk-budgets">
      <header class="dk-sec-head"><h2 id="dk-budgets" class="pm-label">Budgets this month</h2>
        ${current() ? `<span class="pm-small pm-muted dk-key"><i aria-hidden="true"></i>where you should be today (${Math.round(status.elapsed * 100)}%)</span>` : ""}
        ${status.editable ? `<button type="button" class="dk-btn dk-edit-btn" data-act="plan" data-bucket="">Change amounts</button>` : ""}</header>
      <div class="dk-scroll"><div class="dk-table-min">
        <div class="dk-grid dk-th" aria-hidden="true"><span></span><span>Bucket</span><span>Used</span><span class="dk-num">Spent / budget</span><span class="dk-num">Left</span></div>
        ${rows}${unsorted}${plans}
      </div></div>${bills ? `<div class="dk-bills"><b class="pm-small">Fixed bills</b>${bills}</div>` : ""}</section>`;
  }

  // ---- side column ------------------------------------------------------------------------------------
  function paid() {
    const pd = status.paid, order = status.people_order;
    const sum = order.reduce((n, k) => n + pd.people[k].total, 0);
    const segs = order.map((k) => `<i style="--w:${(sum ? (pd.people[k].total / sum) * 100 : 100 / order.length).toFixed(1)}%;--c:${accent(k)}"></i>`).join("");
    const keys = order.map((k) => `<span><span>${dot(k)}${esc(name(k))}</span><b class="pm-mid">${esc(pd.people[k].total_fmt)}</b>
      <span class="pm-small pm-muted">${sum ? pct(pd.people[k].total, sum) : 0}%</span></span>`).join("");
    const rows = pd.rows.map((r) => `<tr><th scope="row">${icon(BUCKET_ICON[r.bucket] || "receipt")}${esc(bucketLabel(r.bucket))}</th>${order.map((k) =>
      `<td>${r.people[k].amount ? esc(r.people[k].amount_fmt) : "–"}</td>`).join("")}</tr>`).join("");
    const transfers = pd.transfers.map((t) => `<li>${icon("swap")}<span class="pm-name">${esc(name(t.from))} → ${esc(name(t.to))}
      <span class="pm-small pm-muted">${esc(shortDate(t.on))}${t.note ? ` · ${esc(t.note)}` : ""}</span></span><b>${esc(t.amount_fmt)}</b></li>`).join("");
    return `<section class="pm-card dk-paid" aria-labelledby="dk-paid">
      <h2 id="dk-paid" class="pm-label">Paid this month</h2>
      <div class="pm-split" role="img" aria-label="${esc(order.map((k) => `${name(k)} paid ${pd.people[k].total_fmt}`).join(", "))}">${segs}</div>
      <div class="pm-keys">${keys}</div>
      ${pd.unknown ? `<p class="pm-small pm-muted">Payer not known yet: ${esc(pd.unknown_fmt)}</p>` : ""}
      <details class="dk-by"><summary>By bucket</summary><div class="pm-table-box"><table class="pm-table">
        <thead><tr><th scope="col">For</th>${order.map((k) => `<th scope="col">${esc(name(k))}</th>`).join("")}</tr></thead>
        <tbody>${rows || `<tr><td colspan="${order.length + 1}">Nothing paid yet this month.</td></tr>`}
        <tr class="pm-total"><th scope="row">Total</th>${order.map((k) => `<td>${esc(pd.people[k].total_fmt)}</td>`).join("")}</tr></tbody></table></div></details>
      ${transfers ? `<h3 class="pm-small">Money handed over</h3><ul class="pm-list pm-bills dk-transfers">${transfers}</ul>` : ""}
    </section>`;
  }

  function places() {
    if (!spends) return `<p class="pm-muted pm-empty">Loading…</p>`;
    if (!spends.top_places.length) return `<p class="pm-muted pm-empty">No places yet.</p>`;
    return `<ol class="dk-places">${spends.top_places.map((p, i) => `<li><span class="pm-muted">${i + 1}</span>
      ${icon(BUCKET_ICON[p.bucket] || "receipt")}<span class="pm-name">${esc(p.place)}<span class="pm-small pm-muted">${p.count}×</span></span>
      <b>${esc(p.total_fmt)}</b></li>`).join("")}</ol>`;
  }

  // ---- spending log -----------------------------------------------------------------------------------
  function tools() {
    const opt = (cur, first, items) => `<option value="">${esc(first)}</option>` +
      items.map(([v, l]) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(l)}</option>`).join("");
    const who = status.people_order.map((k) => [k, name(k)]);
    return `<h2 id="dk-log" class="pm-label">Spending log</h2>
      <label class="pm-search">${icon("search")}<span class="du-sr-only">Search spends</span>
        <input type="search" data-act="search" placeholder="Search place or item" value="${esc(state.q)}" autocomplete="off"></label>
      <label><span class="du-sr-only">Category</span><select class="dk-select" data-act="select" name="category">${opt(state.category, "Any category", status.categories.map((c) => [c, c]))}</select></label>
      <label><span class="du-sr-only">Paid by</span><select class="dk-select" data-act="select" name="paid_by">${opt(state.paid_by, "Anyone paid", [...who, ["each", "Each paid own"]])}</select></label>
      <button type="button" class="dk-btn" data-act="clear">Clear</button>
      <button type="button" class="dk-btn pm-coral" data-act="csv">${icon("download")}Export CSV</button>`;
  }

  function chips() {
    const list = [["", "", "All"], ...status.people_order.map((k) => [k, "", name(k)]),
      ...goalBuckets().map((b) => ["", b.key, b.label]), ["", "unsorted", "No bucket"]];
    const sel = (p, b) => state.person === p && state.bucket === b;
    // a bucket clicked in one person's view filters both ways: show that as the bucket's chip pressed
    const on = list.some(([p, b]) => sel(p, b)) ? sel : (p, b) => b === state.bucket && !p;
    return list.map(([p, b, label]) => `<button type="button" data-act="chip" data-person="${esc(p)}" data-bucket="${esc(b)}"
      aria-pressed="${on(p, b)}">${p ? dot(p) : ""}${esc(label)}</button>`).join("");
  }

  function log() {
    if (!spends) return `<p class="pm-muted pm-empty">Loading…</p>`;
    const share = spends.person ? `${name(spends.person)}'s share` : "";
    const summary = `<p class="dk-summary"><b>${spends.count} spend${spends.count === 1 ? "" : "s"}</b> · <b>${esc(spends.total_fmt)}</b>${share ? ` <span class="pm-muted">(${esc(share)})</span>` : ""}</p>`;
    if (!spends.rows.length) return summary + `<p class="pm-muted pm-empty">No spends match.</p>`;
    const tag = (text) => `<span class="pm-tag pm-ahead">${text}</span>`;
    return summary + `<div class="dk-scroll"><table class="dk-table">
      <thead><tr><th scope="col">Date</th><th scope="col">Place / item</th><th scope="col">Bucket</th><th scope="col">Category</th>
        <th scope="col">For</th><th scope="col">Paid by</th><th scope="col">Split</th>${share ? `<th scope="col" class="dk-num">${esc(share)}</th>` : ""}
        <th scope="col" class="dk-num">Amount</th><th scope="col"><span class="du-sr-only">Fix</span></th></tr></thead>
      <tbody>${spends.rows.map((r) => `<tr>
        <td class="pm-muted dk-nowrap">${esc(r.day)} ${esc(r.date)}</td>
        <td><b>${esc(r.place)}</b>${r.item ? ` <span class="pm-muted">(${esc(r.item)})</span>` : ""}</td>
        <td><span class="dk-cell-icon">${icon(BUCKET_ICON[r.bucket] || "receipt")}${r.bucket ? esc(r.bucket_label) : tag("No bucket")}</span></td>
        <td>${esc(r.category) || "—"}</td><td>${esc(r.who)}</td><td>${r.paid_by ? esc(r.paid_by_label) : tag("ask")}</td>
        <td class="pm-muted dk-split-cell">${esc(r.split) || "—"}</td>${share ? `<td class="dk-num">${esc(r.share_fmt)}</td>` : ""}
        <td class="dk-num"><b>${esc(r.total_sen_fmt)}</b></td>
        <td><button type="button" class="dk-fix" data-act="fix" data-id="${r.id}" aria-label="Fix the amount of ${esc(r.place)}">Edit</button></td></tr>`).join("")}</tbody></table></div>`;
  }

  // ---- render + events --------------------------------------------------------------------------------
  function build() {
    root.innerHTML = `<header class="dk-head"></header>
      <main class="dk-wrap dk-main">
        <p class="pm-stale" role="status" hidden></p>
        <div class="dk-top"></div>
        <section class="pm-card dk-log" aria-labelledby="dk-log">
          <div class="dk-tools"></div><div class="pm-chips dk-chips" role="group" aria-label="Filter spends"></div><div class="dk-log-body"></div>
        </section>
      </main>`;
    built = true;
  }

  function renderStatus() {
    if (!status || !root) return;
    if (!built) build();
    $d(".dk-head").innerHTML = header();
    $d(".dk-top").innerHTML = `${pending()}<div class="dk-cards">${hero()}${week()}${settle()}</div>
      <div class="dk-split">${budgets()}<aside class="dk-side">${paid()}
        <section class="pm-card" aria-labelledby="dk-places"><h2 id="dk-places" class="pm-label dk-sec-head">Top places</h2><div class="dk-places-box">${places()}</div></section>
      </aside></div>`;
    if (!$d(".dk-tools").contains(document.activeElement)) $d(".dk-tools").innerHTML = tools();
    renderStale();
    renderSpends();
  }

  function renderSpends() {
    if (!status || !built) return;
    $d(".dk-chips").innerHTML = chips();
    $d(".dk-log-body").innerHTML = log();
    $d(".dk-places-box").innerHTML = places();
  }

  function renderStale() {
    const el = $d(".pm-stale");
    if (!el) return;
    el.hidden = !view.stale;
    el.textContent = view.stale;
  }

  function filter(person, bucket, scroll = false) {
    Object.assign(state, { person, bucket });
    if (typeof fillFilterOptions === "function") fillFilterOptions();
    spends = null;
    renderSpends();
    loadSpends().catch(markStale);
    if (scroll) $d(".dk-log").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  root?.addEventListener("click", (e) => {
    const t = e.target.closest("[data-act]");
    if (!t) return;
    const act = t.dataset.act;
    if (act === "who") { view.who = t.dataset.who; renderStatus(); filter(view.who, ""); }
    else if (act === "filter") filter(t.dataset.person, t.dataset.bucket, true);
    else if (act === "chip") filter(t.dataset.person, t.dataset.bucket);
    else if (act === "month" && t.dataset.month) goMonth(t.dataset.month);
    else if (act === "csv") document.getElementById("csv")?.click();
    else if (act === "plan") kkEdit.plan(t.dataset.bucket);
    else if (act === "fix") { const r = spends?.rows.find((x) => x.id === Number(t.dataset.id)); if (r) kkEdit.spend(r); }
    else if (act === "clear") {
      Object.assign(state, { person: "", bucket: "", category: "", paid_by: "", q: "" });
      $d(".dk-tools").innerHTML = tools();
      filter("", "");
    }
  });
  root?.addEventListener("change", (e) => {
    const act = e.target.dataset.act;
    if (act === "pick-month") goMonth(e.target.value);
    else if (act === "select") { state[e.target.name] = e.target.value; filter(state.person, state.bucket); }
  });
  let typing = null;
  root?.addEventListener("input", (e) => {
    if (e.target.dataset.act !== "search") return;
    clearTimeout(typing);
    typing = setTimeout(() => { state.q = e.target.value.trim(); loadSpends().catch(markStale); }, 300);
  });
  // app.js updates its own live badge (inside the hidden #app); mirror it into this header
  const live = document.getElementById("live");
  if (live && root) new MutationObserver(() => {
    const el = root.querySelector(".dk-head .kk-live");
    if (!el) return;
    el.dataset.s = live.dataset.s;
    el.querySelector("span").textContent = live.textContent.trim();
  }).observe(live, { attributes: true, childList: true, subtree: true, characterData: true });

  return {
    status() { view.stale = ""; renderStatus(); },
    spends(d) { spends = d; renderSpends(); },
    stale(text) { view.stale = text; renderStale(); },
  };
})();
