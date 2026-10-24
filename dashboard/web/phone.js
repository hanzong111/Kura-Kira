// Phone layout of the dashboard (shown at max-width 767px by phone.css; PCs keep the app.js layout).
// It reuses app.js's data and helpers: `status`, `state`, `esc`, `icon`, `name`, `loadSpends`, `goMonth` and
// friends, and app.js calls kkPhone.status() / .spends(d) / .stale(text) after each load. Like app.js it lays
// out what the server computed: no money is added up here, and Edit buttons open app.js's kkEdit.
"use strict";

window.kkPhone = (() => {
  const root = document.getElementById("phone");
  const ACCENTS = ["var(--du-coral)", "var(--du-teal)", "var(--du-yellow)", "var(--du-blue)"];
  const STATE_CLASS = { ok: "ok", ahead: "ahead", over: "over" };
  const view = { tab: "overview", who: "", detail: null, sheet: null, stale: "" };
  let spends = null;

  const accent = (key) => ACCENTS[Math.max(0, status.people_order.indexOf(key)) % ACCENTS.length];
  const dot = (key) => `<i class="pm-dot" style="--c:${accent(key)}" aria-hidden="true"></i>`;
  const current = () => status.today.startsWith(status.month);
  const scope = () => (view.who ? status.people[view.who] : status.combined);
  const people = () => (view.who ? [view.who] : status.people_order);
  const fillPct = (n, d) => (d > 0 ? Math.max(0, Math.min(100, (n / d) * 100)) : n > 0 ? 100 : 0);

  function bar(spent, cap, st, pace, label) {
    const marker = pace == null ? "" : `<i class="pm-pace" style="--p:${(Math.min(1, pace) * 100).toFixed(1)}%" aria-hidden="true"></i>`;
    return `<span class="pm-bar pm-${STATE_CLASS[st] || "ok"}" role="progressbar" aria-label="${esc(label)}"
      aria-valuemin="0" aria-valuemax="${cap}" aria-valuenow="${Math.max(0, Math.min(spent, cap))}">
      <i style="--w:${fillPct(spent, cap).toFixed(1)}%"></i>${marker}</span>`;
  }

  const left = (b) => (b.left < 0
    ? `<b class="pm-over">${esc(String(b.left_fmt).replace(/^-/, ""))} over</b>`
    : `<b>${esc(b.left_fmt)}</b> <span class="pm-muted">left</span>`);

  // ---- header + tabs ----------------------------------------------------------------------------------
  function header() {
    const title = view.detail ? bucketLabel(view.detail) : status.household?.name || "Kura-Kira";
    const months = status.months.map((m) => `<option value="${m}"${m === status.month ? " selected" : ""}>${esc(monthLabel(m))}</option>`).join("");
    const i = status.months.indexOf(status.month);
    const back = view.detail
      ? `<button type="button" class="pm-icon-btn pm-coral" data-act="back" aria-label="Back">${icon("arrow-left")}</button>` : "";
    return `<header class="pm-head">
      <div class="pm-head-row">${back}<h1>${esc(title)}</h1><span class="pm-day">Day ${status.day} of ${status.days}</span></div>
      ${view.detail ? "" : `<div class="pm-head-row">
        <button type="button" class="pm-icon-btn pm-coral" data-act="month" data-month="${esc(status.months[i + 1] || "")}"
          aria-label="Previous month"${i >= status.months.length - 1 ? " disabled" : ""}>${icon("arrow-left")}</button>
        <label class="pm-month"><span class="du-sr-only">Budget month</span><select data-act="pick-month">${months}</select></label>
        <button type="button" class="pm-icon-btn pm-coral" data-act="month" data-month="${esc(status.months[i - 1] || "")}"
          aria-label="Next month"${i <= 0 ? " disabled" : ""}>${icon("arrow-right")}</button>
      </div>`}
      ${view.stale ? `<p class="pm-stale" role="status">${esc(view.stale)}</p>` : ""}
    </header>`;
  }

  function tabs() {
    const t = [["overview", "Overview", "chart"], ["spends", "Spends", "receipt"], ["paid", "Who paid", "swap"]];
    return `<nav class="pm-tabs" aria-label="Dashboard">${t.map(([key, label, ic]) =>
      `<button type="button" data-act="tab" data-tab="${key}"${view.tab === key && !view.detail ? ' aria-current="page"' : ""}>${icon(ic)}${label}</button>`).join("")}</nav>`;
  }

  function whoSwitch() {
    if (status.people_order.length < 2) return "";
    const opts = [["", "Both"], ...status.people_order.map((k) => [k, name(k)])];
    if (opts.length > 3) opts[0][1] = "Everyone";
    return `<div class="pm-switch" role="group" aria-label="Whose budget">${opts.map(([k, label]) =>
      `<button type="button" data-act="who" data-who="${esc(k)}" aria-pressed="${view.who === k}">${k ? dot(k) : ""}${esc(label)}</button>`).join("")}</div>`;
  }

  // ---- overview ---------------------------------------------------------------------------------------
  function pending() {
    if (!status.pending.length) return "";
    const items = status.pending.map((q) => `<li><b>${esc(q.place)}</b> ${esc(q.total_fmt)} · ${esc(q.who)} · ${esc(shortDate(q.spent_on))}:
      ${q.needs.map((n) => (n === "bucket" ? (q.options.length ? esc(q.options.join(" or ")) + "?" : "which bucket?") : "who paid?")).join(" · ")}</li>`).join("");
    return `<section class="pm-card pm-pending" aria-labelledby="pm-needs">${icon("question")}
      <div><h2 id="pm-needs" class="pm-pending-title">${status.pending.length} need${status.pending.length === 1 ? "s" : ""} an answer</h2>
      <ul>${items}</ul><p>Answer it in Telegram.</p></div></section>`;
  }

  function hero() {
    const g = scope().goals;
    const used = g.cap ? Math.round((g.spent / g.cap) * 100) : 0;
    const label = view.who ? `${name(view.who)} · left this month` : "Left this month";
    const tag = { ok: "On track", ahead: "Ahead of pace", over: "Over budget" }[g.status] || "On track";
    return `<section class="pm-card pm-hero" aria-labelledby="pm-left">
      <div class="pm-row"><h2 id="pm-left" class="pm-label">${esc(label)}</h2><span class="pm-tag pm-${STATE_CLASS[g.status] || "ok"}">${tag}</span></div>
      <p class="pm-big">${g.left < 0 ? `${esc(String(g.left_fmt).replace(/^-/, ""))} over` : esc(g.left_fmt)}</p>
      <p class="pm-muted">of ${esc(g.cap_fmt)} · ${used}% used</p>
      ${bar(g.spent, g.cap, g.status, current() ? g.pace ?? status.elapsed : null, "Month spent")}
      <p class="pm-row pm-small"><span>Spent ${esc(g.spent_fmt)}</span>${current() ? `<span>month ${Math.round(status.elapsed * 100)}% gone</span>` : ""}</p>
    </section>`;
  }

  function week() {
    const weekly = goalBuckets().filter((b) => b.kind === "weekly");
    if (!weekly.length || !current()) return "";
    let range = "";
    const cards = weekly.map((b) => {
      const rows = people().map((k) => {
        const w = status.people[k].buckets[b.key]?.week;
        if (!w) return "";
        range = `${shortDate(w.start)} – ${shortDate(w.end)}`;
        const carry = w.carry ? ` · ${w.carry < 0 ? "−" : "+"}${esc(String(w.carry_fmt).replace(/^-/, ""))} ${w.carry < 0 ? "overspent" : "saved"}` : "";
        return `<span class="pm-week-row">${view.who || status.people_order.length < 2 ? "" : `<span class="pm-small">${dot(k)}${esc(name(k))}</span>`}
          <span class="pm-mid">${w.left < 0 ? `<span class="pm-over">${esc(String(w.left_fmt).replace(/^-/, ""))} over</span>` : esc(w.left_fmt)}</span>
          <span class="pm-small pm-muted">can spend${carry}</span>
          ${bar(w.spent, w.allowance, w.status, w.days ? w.days_elapsed / w.days : null, `${name(k)} ${b.label} this week`)}</span>`;
      }).join("");
      return rows ? `<button type="button" class="pm-card pm-week" data-act="detail" data-bucket="${esc(b.key)}">
        <span class="pm-week-title">${icon(BUCKET_ICON[b.key] || "receipt")}${esc(b.label)}</span>${rows}</button>` : "";
    }).join("");
    return cards ? `<section aria-labelledby="pm-week"><h2 id="pm-week" class="pm-label pm-row"><span>This week</span>
      <span class="pm-plain pm-muted">${esc(range)}</span></h2><div class="pm-grid2">${cards}</div></section>` : "";
  }

  function budgets() {
    const s = scope();
    const rows = goalBuckets().map((b) => {
      const v = s.buckets[b.key];
      if (!v) return "";
      const pace = !current() ? null : b.kind === "weekly" ? null : status.elapsed;
      return `<button type="button" class="pm-bucket" data-act="detail" data-bucket="${esc(b.key)}">
        ${icon(BUCKET_ICON[b.key] || "receipt")}<span class="pm-name">${esc(b.label)}</span><span class="pm-right">${left(v)}</span>
        ${bar(v.spent, v.cap, v.status, pace, b.label)}<span class="pm-right pm-small pm-muted">${esc(v.spent_fmt)} / ${esc(v.cap_fmt)}</span></button>`;
    }).join("");
    const unsorted = s.unsorted ? `<button type="button" class="pm-bucket" data-act="detail" data-bucket="unsorted">
      ${icon("receipt")}<span class="pm-name">No bucket yet</span><span class="pm-right"><b>${esc(s.unsorted_fmt)}</b></span></button>` : "";
    return `<section aria-labelledby="pm-month"><div class="pm-row"><h2 id="pm-month" class="pm-label">Budgets this month</h2>${editBtn("", "Change amounts")}</div>
      <div class="pm-card pm-list">${rows}${unsorted}</div></section>`;
  }

  function bills() {
    const s = scope();
    const rows = fixedBuckets().filter((b) => s.buckets[b.key]).map((b) => {
      const f = s.buckets[b.key];
      const count = f.count ?? 1;
      const [cls, text] = f.paid === count || f.paid === true ? ["ok", "Paid"] : !f.paid ? ["over", "Due"] : ["ahead", `${f.paid} of ${count} paid`];
      return `<li>${icon(BUCKET_ICON[b.key] || "receipt")}<span class="pm-name">${esc(b.label)}
        ${f.amount_fmt ? `<span class="pm-muted pm-small">${esc(f.amount_fmt)}</span>` : ""}</span><span class="pm-tag pm-${cls}">${text}</span>${editBtn(b.key)}</li>`;
    }).join("");
    return rows ? `<section aria-labelledby="pm-bills"><h2 id="pm-bills" class="pm-label">Fixed bills</h2>
      <ul class="pm-card pm-list pm-bills">${rows}</ul></section>` : "";
  }

  const editBtn = (key, label = key ? "Edit" : "Change") => (status.editable
    ? `<button type="button" class="pm-edit" data-act="plan" data-bucket="${esc(key)}">${esc(label)}</button>` : "");

  const overview = () => whoSwitch() + pending() + hero() + week() + budgets() + bills();

  // ---- bucket detail ----------------------------------------------------------------------------------
  function bucketLabel(key) {
    return key === "unsorted" ? "No bucket yet" : status.bucket_order.find((b) => b.key === key)?.label ?? key;
  }

  function detail() {
    const key = view.detail;
    const b = status.bucket_order.find((x) => x.key === key);
    const cards = key === "unsorted" ? "" : people().map((k) => {
      const v = status.people[k].buckets[key];
      if (!v) return "";
      const w = current() && v.week;
      const who = view.who || status.people_order.length < 2 ? "" : `<h3 class="pm-small">${dot(k)}${esc(name(k))}</h3>`;
      const eq = w ? `<dl class="pm-eq"><dt>This week's target</dt><dd>${esc(w.target_fmt)}</dd>
          ${w.carry ? `<dt>${w.carry < 0 ? "Overspent earlier" : "Saved in earlier weeks"}</dt><dd class="${w.carry < 0 ? "pm-over" : "pm-saved"}">${w.carry < 0 ? "−" : "+"} ${esc(String(w.carry_fmt).replace(/^-/, ""))}</dd>` : ""}
          <dt class="pm-total">Can spend</dt><dd class="pm-total">${esc(w.allowance_fmt)}</dd>
          <dt>Spent this week</dt><dd>${esc(w.spent_fmt)}</dd></dl>` : "";
      return `<section class="pm-card pm-hero">${who}
        <h2 class="pm-label">${w ? "Can spend this week" : "Left this month"}</h2>
        <p class="pm-big">${w ? (w.left < 0 ? `${esc(String(w.left_fmt).replace(/^-/, ""))} over` : esc(w.left_fmt)) : v.left < 0 ? `${esc(String(v.left_fmt).replace(/^-/, ""))} over` : esc(v.left_fmt)}</p>
        ${w ? bar(w.spent, w.allowance, w.status, w.days ? w.days_elapsed / w.days : null, "This week")
            : bar(v.spent, v.cap, v.status, current() ? status.elapsed : null, "This month")}
        ${eq}<p class="pm-small pm-muted">This month: ${esc(v.spent_fmt)} of ${esc(v.cap_fmt)}${b?.kind === "weekly" ? " · unspent days carry into the next week" : ""}</p>
      </section>`;
    }).join("");
    return cards + (key === "unsorted" || !status.editable ? "" : `<p class="pm-row">${editBtn(key, "Change this budget")}</p>`) +
      `<section aria-labelledby="pm-dspends"><h2 id="pm-dspends" class="pm-label">Spends</h2>${spendList()}</section>`;
  }

  // ---- spends -----------------------------------------------------------------------------------------
  function chips() {
    const list = [["", "", "All"], ...status.people_order.map((k) => [k, "", name(k)]),
      ...goalBuckets().map((b) => ["", b.key, b.label]), ["", "unsorted", "No bucket"]];
    return `<div class="pm-chips" role="group" aria-label="Filter spends">${list.map(([p, b, label]) => {
      const on = state.person === p && state.bucket === b;
      return `<button type="button" data-act="chip" data-person="${esc(p)}" data-bucket="${esc(b)}" aria-pressed="${on}">${esc(label)}</button>`;
    }).join("")}</div>`;
  }

  function spendList() {
    if (!spends) return `<p class="pm-muted pm-empty">Loading…</p>`;
    if (!spends.rows.length) return `<p class="pm-muted pm-empty">No spends match.</p>`;
    const groups = [];
    for (const r of spends.rows) {
      const label = `${r.day} ${r.date}`;
      let g = groups.find((x) => x.label === label);
      if (!g) groups.push(g = { label, rows: [] });
      g.rows.push(r);
    }
    return `<p class="pm-small"><b>${spends.count} spend${spends.count === 1 ? "" : "s"}</b> · <b>${esc(spends.total_fmt)}</b>${spends.person_label ? ` <span class="pm-muted">(${esc(spends.person_label)}'s share)</span>` : ""}</p>` +
      groups.map((g) => `<section class="pm-day-group"><h3 class="pm-label pm-muted">${esc(g.label)}</h3><div class="pm-card pm-list">${g.rows.map((r) =>
        `<button type="button" class="pm-spend" data-act="sheet" data-id="${r.id}">${icon(BUCKET_ICON[r.bucket] || "receipt")}
          <span class="pm-name"><b>${esc(r.place)}</b><span class="pm-small pm-muted">${esc(r.bucket ? r.bucket_label : "No bucket yet")} · ${esc(r.who)}</span></span>
          <b>${esc(spends.person ? r.share_fmt : r.total_sen_fmt)}</b></button>`).join("")}</div></section>`).join("");
  }

  function spendsTab() {
    return `<div class="pm-tools"><label class="pm-search">${icon("search")}<span class="du-sr-only">Search spends</span>
        <input type="search" data-act="search" placeholder="Search place or item" value="${esc(state.q)}" autocomplete="off"></label>
        <button type="button" class="pm-icon-btn" data-act="csv" aria-label="Export CSV">${icon("download")}</button></div>
      ${chips()}${spendList()}`;
  }

  function sheet() {
    const r = spends?.rows.find((x) => x.id === view.sheet);
    if (!r) return "";
    const line = (k, v) => `<dt>${k}</dt><dd>${esc(v || "—")}</dd>`;
    return `<div class="pm-scrim" data-act="close"></div>
      <section class="pm-sheet" role="dialog" aria-modal="true" aria-labelledby="pm-sheet-title">
        <span class="pm-grip" aria-hidden="true"></span>
        <div class="pm-row">${icon(BUCKET_ICON[r.bucket] || "receipt")}<div class="pm-name"><h2 id="pm-sheet-title">${esc(r.place)}</h2>
          <span class="pm-small pm-muted">${esc(r.day)} ${esc(r.date)}${r.item ? ` · ${esc(r.item)}` : ""}</span></div><b class="pm-mid">${esc(r.total_sen_fmt)}</b></div>
        <dl class="pm-facts">${line("Bucket", r.bucket ? r.bucket_label : "No bucket yet")}${line("Category", r.category)}${line("For", r.who)}
          ${line("Paid by", r.paid_by ? r.paid_by_label : "Not known yet")}${line("Split", r.split)}</dl>
        <p class="pm-small pm-muted">Wrong amount? Fix it here. Anything else: reply to the bot in Telegram.</p>
        <div class="pm-sheet-actions"><button type="button" class="pm-done pm-fix" data-act="fix" data-id="${r.id}">Fix amount</button>
          <button type="button" class="pm-done" data-act="close">Done</button></div>
      </section>`;
  }

  // ---- who paid ---------------------------------------------------------------------------------------
  function paid() {
    const pd = status.paid, order = status.people_order, owes = status.balance.owes;
    const sum = order.reduce((n, k) => n + pd.people[k].total, 0);
    const label = (k) => (k === "unsorted" ? "No bucket yet" : status.bucket_order.find((b) => b.key === k)?.label ?? k);
    const settle = `<section class="pm-card pm-settle" aria-labelledby="pm-settle">${icon("swap")}<div>
      <h2 id="pm-settle" class="pm-label">To settle up</h2>
      <p class="pm-mid">${owes ? `${esc(name(owes.from))} owes ${esc(name(owes.to))} ${esc(owes.amount_fmt)}` : "All square"}</p></div></section>`;
    const segs = order.map((k) => `<i style="--w:${(sum ? (pd.people[k].total / sum) * 100 : 100 / order.length).toFixed(1)}%;--c:${accent(k)}"></i>`).join("");
    const keys = order.map((k) => `<span><span>${dot(k)}${esc(name(k))}</span><b class="pm-mid">${esc(pd.people[k].total_fmt)}</b>
      <span class="pm-small pm-muted">${sum ? pct(pd.people[k].total, sum) : 0}%</span></span>`).join("");
    const rows = pd.rows.map((r) => `<tr><th scope="row">${icon(BUCKET_ICON[r.bucket] || "receipt")}${esc(label(r.bucket))}</th>${order.map((k) =>
      `<td>${r.people[k].amount ? esc(r.people[k].amount_fmt) : "–"}</td>`).join("")}</tr>`).join("");
    const transfers = pd.transfers.length ? `<section><h2 class="pm-label">Money handed over</h2><ul class="pm-card pm-list pm-bills">${pd.transfers.map((t) =>
      `<li>${icon("swap")}<span class="pm-name">${esc(name(t.from))} → ${esc(name(t.to))}<span class="pm-small pm-muted">${esc(shortDate(t.on))}</span></span><b>${esc(t.amount_fmt)}</b></li>`).join("")}</ul></section>` : "";
    return settle + `<section aria-labelledby="pm-paidm"><h2 id="pm-paidm" class="pm-label">Paid this month</h2>
      <div class="pm-card pm-paid"><div class="pm-split" role="img" aria-label="${esc(order.map((k) => `${name(k)} paid ${pd.people[k].total_fmt}`).join(", "))}">${segs}</div>
      <div class="pm-keys">${keys}</div></div></section>
      <section aria-labelledby="pm-by"><h2 id="pm-by" class="pm-label">By bucket</h2><div class="pm-card pm-table-box"><table class="pm-table">
        <thead><tr><th scope="col">For</th>${order.map((k) => `<th scope="col">${esc(name(k))}</th>`).join("")}</tr></thead>
        <tbody>${rows || `<tr><td colspan="${order.length + 1}">Nothing paid yet this month.</td></tr>`}
        <tr class="pm-total"><th scope="row">Total</th>${order.map((k) => `<td>${esc(pd.people[k].total_fmt)}</td>`).join("")}</tr></tbody></table></div></section>
      ${pd.unknown ? `<p class="pm-small pm-muted">Payer not known yet: ${esc(pd.unknown_fmt)}</p>` : ""}${transfers}`;
  }

  // ---- render + events --------------------------------------------------------------------------------
  function render() {
    if (!status || !root) return;
    const scrollY = root.querySelector(".pm-body")?.scrollTop ?? 0;
    const body = view.detail ? detail() : view.tab === "spends" ? spendsTab() : view.tab === "paid" ? paid() : overview();
    root.innerHTML = header() + `<div class="pm-body">${body}</div>` + tabs() + sheet();
    const el = root.querySelector(".pm-body");
    if (el && !view.reset) el.scrollTop = scrollY;
    view.reset = false;
    const back = window.Telegram?.WebApp?.BackButton;
    if (back) (view.detail || view.sheet ? back.show() : back.hide());
  }

  function filter(person, bucket) {
    Object.assign(state, { person, bucket, category: "", paid_by: "", q: state.q });
    if (typeof fillFilterOptions === "function") fillFilterOptions();
    spends = null;
    render();
    loadSpends().catch(markStale);
  }

  function goBack() {
    if (view.sheet) { view.sheet = null; return render(); }
    if (view.detail) { view.detail = null; view.reset = true; filter("", ""); }
  }

  root?.addEventListener("click", (e) => {
    const t = e.target.closest("[data-act]");
    if (!t) return;
    const act = t.dataset.act;
    if (act === "tab") { Object.assign(view, { tab: t.dataset.tab, detail: null, sheet: null, reset: true }); if (state.bucket || state.person) filter("", ""); else render(); }
    else if (act === "who") { view.who = t.dataset.who; render(); }
    else if (act === "detail") { Object.assign(view, { detail: t.dataset.bucket, reset: true }); filter(view.who, t.dataset.bucket); }
    else if (act === "back") goBack();
    else if (act === "chip") filter(t.dataset.person, t.dataset.bucket);
    else if (act === "sheet") { view.sheet = Number(t.dataset.id); render(); }
    else if (act === "close") { view.sheet = null; render(); }
    else if (act === "month" && t.dataset.month) goMonth(t.dataset.month);
    else if (act === "csv") document.getElementById("csv")?.click();
    else if (act === "plan") kkEdit.plan(t.dataset.bucket);
    else if (act === "fix") {
      const r = spends?.rows.find((x) => x.id === Number(t.dataset.id));
      if (r) { view.sheet = null; render(); kkEdit.spend(r); }
    }
  });
  root?.addEventListener("change", (e) => { if (e.target.dataset.act === "pick-month") goMonth(e.target.value); });
  let typing = null;
  root?.addEventListener("input", (e) => {
    if (e.target.dataset.act !== "search") return;
    clearTimeout(typing);
    typing = setTimeout(() => {
      state.q = e.target.value.trim();
      loadSpends().then(() => { const s = root.querySelector('[data-act="search"]'); s?.focus(); s?.setSelectionRange(s.value.length, s.value.length); })
        .catch(markStale);
    }, 300);
  });
  window.Telegram?.WebApp?.BackButton?.onClick(goBack);

  return {
    status() { view.stale = ""; render(); },
    spends(d) { spends = d; render(); },
    stale(text) { view.stale = text; render(); },
  };
})();
