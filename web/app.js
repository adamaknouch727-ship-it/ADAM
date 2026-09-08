/* KDP Niche Finder — front end. No framework, no build step. */
(() => {
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  markets: [], symbol: "$", job: null, run: null,
  niches: [], keywords: [], saved: new Set(),
  sort: { key: "opportunity_score", dir: -1 },
};

/* ------------------------------------------------------------ helpers */
const fmt = (value, digits = 0) =>
  value === null || value === undefined || value === "" || Number.isNaN(value)
    ? "—"
    : Number(value).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
const money = (value, digits = 0) => state.symbol + fmt(value, digits);
const pct = (value) => value === null || value === undefined ? "—" : Math.round(value * 100) + "%";
const esc = (text) => String(text ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function scoreColor(score) {
  if (score >= 72) return "var(--good)";
  if (score >= 60) return "var(--accent-2)";
  if (score >= 48) return "var(--warn)";
  if (score >= 36) return "var(--accent)";
  return "var(--bad)";
}

/* --------------------------------------------------------------- boot */
async function boot() {
  const data = await api("/api/markets");
  state.markets = data.markets;
  const options = data.markets
    .map((m) => `<option value="${m.code}">${esc(m.name)} — ${esc(m.domain)}</option>`).join("");
  $("#market").innerHTML = options;
  $("#calcMarket").innerHTML = options;
  const saved = localStorage.getItem("kdpniche.prefs");
  if (saved) {
    const prefs = JSON.parse(saved);
    for (const [id, value] of Object.entries(prefs)) {
      const el = document.getElementById(id);
      if (!el) continue;
      if (el.type === "checkbox") el.checked = value; else el.value = value;
    }
  }
  syncSymbol();
  loadSaved();
  loadRuns();
  recalc();
}

function savePrefs() {
  const prefs = {};
  for (const id of ["market", "store", "breadth", "limit", "deep", "offline"]) {
    const el = document.getElementById(id);
    prefs[id] = el.type === "checkbox" ? el.checked : el.value;
  }
  localStorage.setItem("kdpniche.prefs", JSON.stringify(prefs));
}

function syncSymbol() {
  const market = state.markets.find((m) => m.code === $("#market").value);
  state.symbol = market ? market.symbol : "$";
}

/* ------------------------------------------------------------- search */
async function startSearch() {
  const seed = $("#seed").value.trim();
  if (!seed) { $("#seed").focus(); return; }
  savePrefs();
  syncSymbol();
  $("#searchBtn").disabled = true;
  $("#warnings").classList.add("hidden");
  showProgress(0, "Asking Amazon for keyword ideas…", "");
  try {
    const { job } = await api("/api/search", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        seed,
        marketplace: $("#market").value,
        store: $("#store").value,
        breadth: $("#breadth").value,
        limit: Number($("#limit").value) || 25,
        deep: $("#deep").checked,
        offline: $("#offline").checked,
      }),
    });
    state.job = job;
    poll();
  } catch (error) {
    fail(error.message);
  }
}

function poll() {
  const timer = setInterval(async () => {
    let job;
    try { job = await api("/api/job/" + state.job); }
    catch (error) { clearInterval(timer); fail(error.message); return; }

    const total = job.total || 0;
    const done = job.done || 0;
    const ratio = total ? done / total : 0.05;
    const stage = job.stage === "keywords" ? "Collecting keyword ideas" : "Analysing niches";
    showProgress(ratio, `${stage}: ${job.current || ""}`, total ? `${done} / ${total}` : "");

    if (job.status === "done") {
      clearInterval(timer);
      finish(job.run);
    } else if (job.status === "error") {
      clearInterval(timer);
      fail(job.error);
    }
  }, 600);
}

function showProgress(ratio, label, count) {
  $("#progress").classList.remove("hidden");
  $("#progressFill").style.width = Math.max(3, Math.min(100, ratio * 100)) + "%";
  $("#progressLabel").textContent = label;
  $("#progressCount").textContent = count;
}

function fail(message) {
  $("#searchBtn").disabled = false;
  $("#progress").classList.add("hidden");
  const box = $("#warnings");
  box.classList.remove("hidden");
  box.textContent = "Search failed: " + message;
}

function finish(run) {
  state.run = run;
  state.niches = run.niches || [];
  state.keywords = run.keywords || [];
  $("#searchBtn").disabled = false;
  setTimeout(() => $("#progress").classList.add("hidden"), 400);

  const badge = $("#sourceBadge");
  if (run.source === "demo") {
    badge.textContent = "DEMO DATA";
    badge.classList.remove("hidden");
  } else { badge.classList.add("hidden"); }

  const box = $("#warnings");
  if (run.warnings && run.warnings.length) {
    box.classList.remove("hidden");
    box.innerHTML = run.warnings.map((w) => `<div>⚠︎ ${esc(w)}</div>`).join("");
  } else { box.classList.add("hidden"); }

  renderNiches();
  renderKeywords();
  loadRuns();
}

/* ------------------------------------------------------- niches table */
function visibleNiches() {
  const text = $("#filterText").value.trim().toLowerCase();
  const minScore = Number($("#filterScore").value);
  const maxComp = Number($("#filterComp").value);
  const maxRev = $("#filterRev").value === "" ? Infinity : Number($("#filterRev").value);
  const rows = state.niches.filter((n) =>
    (!text || n.keyword.includes(text)) &&
    n.opportunity_score >= minScore &&
    n.competition_score <= maxComp &&
    (n.median_reviews ?? 0) <= maxRev);
  const { key, dir } = state.sort;
  return rows.sort((a, b) => {
    const x = a[key] ?? 0, y = b[key] ?? 0;
    if (typeof x === "string") return x.localeCompare(y) * dir * -1;
    return (x - y) * dir;
  });
}

function renderNiches() {
  const rows = visibleNiches();
  $("#countNiches").textContent = state.niches.length;
  $("#nicheEmpty").classList.toggle("hidden", rows.length > 0);
  $("#nicheTable").tBodies[0].innerHTML = rows.map((niche) => {
    const key = niche.keyword + "|" + niche.marketplace + "|" + niche.store;
    const on = state.saved.has(key) ? "on" : "";
    const verdict = (niche.verdict || "No data").split(" ")[0];
    return `<tr data-kw="${esc(niche.keyword)}">
      <td><div class="score"><b>${fmt(niche.opportunity_score, 0)}</b>
        <div class="meter"><i style="width:${niche.opportunity_score}%;background:${scoreColor(niche.opportunity_score)}"></i></div></div></td>
      <td class="kw">${esc(niche.keyword)}</td>
      <td><span class="chip ${verdict}">${esc(niche.verdict)}</span></td>
      <td class="num">${fmt(niche.demand_score)}</td>
      <td class="num">${fmt(niche.competition_score)}</td>
      <td class="num">${money(niche.est_royalty_month)}</td>
      <td class="num">${fmt(niche.est_sales_month)}</td>
      <td class="num">${fmt(niche.median_reviews)}</td>
      <td class="num">${fmt(niche.results_count)}</td>
      <td class="num">${money(niche.median_price, 2)}</td>
      <td><button class="star ${on}" data-star="${esc(niche.keyword)}" title="Shortlist">★</button></td>
    </tr>`;
  }).join("");
}

function renderKeywords() {
  $("#countKeywords").textContent = state.keywords.length;
  $("#kwEmpty").classList.toggle("hidden", state.keywords.length > 0);
  $("#kwTable").tBodies[0].innerHTML = state.keywords.map((idea) => `<tr>
      <td class="kw">${esc(idea.keyword)}</td>
      <td><div class="score"><b>${fmt(idea.volume_score)}</b>
        <div class="meter"><i style="width:${idea.volume_score}%"></i></div></div></td>
      <td class="num">${fmt(idea.hits)}</td>
      <td class="num">${idea.rank === 99 ? "—" : idea.rank + 1}</td>
      <td><button class="ghost" data-reseed="${esc(idea.keyword)}">Use as seed</button></td>
    </tr>`).join("");
}

/* ------------------------------------------------------------- drawer */
function openDrawer(keyword) {
  const niche = state.niches.find((n) => n.keyword === keyword)
             || (state.savedRows || []).find((n) => n.keyword === keyword);
  if (!niche) return;
  const market = state.markets.find((m) => m.code === niche.marketplace);
  $("#drawerTitle").textContent = niche.keyword;
  $("#drawerSub").textContent =
    `${market ? market.domain : niche.marketplace} · ${niche.store} · ` +
    `${niche.analysed || 0} books analysed · ${niche.source === "demo" ? "demo data" : "live Amazon data"}`;

  const bar = (label, value, invert) => `
    <div class="row"><span>${label}</span>
      <div class="track"><i style="width:${value}%;background:${scoreColor(invert ? 100 - value : value)}"></i></div>
      <span style="width:34px;text-align:right">${fmt(value)}</span></div>`;

  const books = (niche.books || []).map((book) => `<tr>
      <td class="cover">${book.image ? `<img src="${esc(book.image)}" alt="">` : ""}</td>
      <td>${book.url ? `<a href="${esc(book.url)}" target="_blank" rel="noopener">${esc(book.title)}</a>` : esc(book.title)}
        <div class="hint">${esc(book.author || "")} ${book.fmt ? "· " + esc(book.fmt) : ""}${book.sponsored ? " · sponsored" : ""}</div></td>
      <td class="num">${book.rating ? book.rating + "★" : "—"}<div class="hint">${fmt(book.reviews)} rev.</div></td>
      <td class="num">${book.price ? money(book.price, 2) : "—"}</td>
      <td class="num">${book.bsr ? "#" + fmt(book.bsr) : "—"}</td>
      <td class="num">${fmt(book.est_sales_month)}<div class="hint">${money(book.est_royalty_month)}</div></td>
    </tr>`).join("");

  $("#drawerBody").innerHTML = `
    <div class="statgrid">
      <div class="stat"><span>Niche score</span><b style="color:${scoreColor(niche.opportunity_score)}">${fmt(niche.opportunity_score, 1)}</b></div>
      <div class="stat"><span>Royalties / month</span><b>${money(niche.est_royalty_month)}</b></div>
      <div class="stat"><span>Revenue / month</span><b>${money(niche.est_revenue_month)}</b></div>
      <div class="stat"><span>Units / month</span><b>${fmt(niche.est_sales_month)}</b></div>
      <div class="stat"><span>Competing books</span><b>${fmt(niche.results_count)}</b></div>
      <div class="stat"><span>Median reviews</span><b>${fmt(niche.median_reviews)}</b></div>
      <div class="stat"><span>Median price</span><b>${money(niche.median_price, 2)}</b></div>
      <div class="stat"><span>Under 50 reviews</span><b>${pct(niche.low_review_share)}</b></div>
      <div class="stat"><span>Self-published</span><b>${pct(niche.indie_share)}</b></div>
      <div class="stat"><span>Avg rating</span><b>${niche.avg_rating || "—"}</b></div>
    </div>
    <div class="breakdown">
      ${bar("Demand", niche.demand_score)}
      ${bar("Competition", niche.competition_score, true)}
      ${bar("Profitability", niche.profit_score)}
      ${bar("Search volume", niche.volume_score)}
    </div>
    ${(niche.reasons || []).length ? `<ul class="reasons">${niche.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="primary" data-save-niche="${esc(niche.keyword)}">★ Add to shortlist</button>
      <button class="ghost" data-reseed="${esc(niche.keyword)}">Drill into this niche</button>
      <a class="ghost" style="padding:7px 12px;border:1px solid var(--line);border-radius:8px;text-decoration:none"
         href="https://${market ? market.domain : "www.amazon.com"}/s?k=${encodeURIComponent(niche.keyword)}&i=${niche.store === "kindle" ? "digital-text" : "stripbooks"}"
         target="_blank" rel="noopener">Open on Amazon ↗</a>
      ${state.run ? `<a class="ghost" style="padding:7px 12px;border:1px solid var(--line);border-radius:8px;text-decoration:none"
         href="/api/export?job=${state.job}&kind=books&keyword=${encodeURIComponent(niche.keyword)}">Export these books</a>` : ""}
    </div>
    <h3>Page one right now</h3>
    <table class="booklist"><thead><tr><th></th><th>Title</th><th>Rating</th><th>Price</th><th>BSR</th><th>Est. sales/mo</th></tr></thead>
      <tbody>${books || `<tr><td colspan="6" class="empty">No books captured.</td></tr>`}</tbody></table>`;

  $("#drawer").classList.add("open");
  $("#scrim").classList.add("open");
}

function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#scrim").classList.remove("open");
}

/* ------------------------------------------------------------ storage */
async function loadSaved() {
  const data = await api("/api/saved");
  state.savedRows = data.niches;
  state.saved = new Set(data.niches.map((n) => n.keyword + "|" + n.marketplace + "|" + n.store));
  $("#countSaved").textContent = data.niches.length;
  $("#savedEmpty").classList.toggle("hidden", data.niches.length > 0);
  $("#savedTable").tBodies[0].innerHTML = data.niches.map((niche) => `<tr data-kw="${esc(niche.keyword)}">
      <td><div class="score"><b>${fmt(niche.opportunity_score)}</b>
        <div class="meter"><i style="width:${niche.opportunity_score}%;background:${scoreColor(niche.opportunity_score)}"></i></div></div></td>
      <td class="kw">${esc(niche.keyword)}</td>
      <td>${esc(niche.marketplace.toUpperCase())}</td>
      <td>${esc(niche.store)}</td>
      <td class="num">${fmt(niche.est_royalty_month)}</td>
      <td class="num">${fmt(niche.median_reviews)}</td>
      <td><button class="ghost" data-unsave="${esc(niche.keyword)}|${niche.marketplace}|${niche.store}">Remove</button></td>
    </tr>`).join("");
  renderNiches();
}

async function toggleSave(keyword) {
  const niche = state.niches.find((n) => n.keyword === keyword);
  if (!niche) return;
  const key = keyword + "|" + niche.marketplace + "|" + niche.store;
  if (state.saved.has(key)) {
    await api("/api/saved/delete", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, marketplace: niche.marketplace, store: niche.store }) });
  } else {
    const copy = { ...niche };
    copy.books = (niche.books || []).slice(0, 10);
    await api("/api/saved", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ niche: copy }) });
  }
  loadSaved();
}

async function loadRuns() {
  const data = await api("/api/runs");
  $("#runEmpty").classList.toggle("hidden", data.runs.length > 0);
  $("#runTable").tBodies[0].innerHTML = data.runs.map((run) => `<tr>
      <td>${new Date(run.created * 1000).toLocaleString()}</td>
      <td class="kw">${esc(run.seed)}</td>
      <td>${esc(run.marketplace.toUpperCase())}</td>
      <td>${esc(run.store)}</td>
      <td class="num">${run.niches}</td>
      <td><button class="ghost" data-openrun="${run.id}">Open</button></td>
    </tr>`).join("");
}

async function openRun(runId) {
  const run = await api("/api/runs/" + runId);
  state.job = null;
  $("#seed").value = run.seed;
  $("#market").value = run.marketplace;
  $("#store").value = run.store;
  syncSymbol();
  finish(run);
  switchTab("niches");
}

/* --------------------------------------------------------- calculator */
const PRINT_CURVE = [[1,2500],[5,1100],[10,700],[50,260],[100,170],[500,60],[1000,38],[5000,11],
  [10000,6.2],[25000,2.9],[50000,1.6],[100000,.85],[250000,.34],[500000,.17],[1000000,.075],
  [2000000,.03],[5000000,.008]];
const KINDLE_CURVE = [[1,5200],[5,2400],[10,1500],[50,600],[100,400],[500,145],[1000,95],[5000,28],
  [10000,16],[25000,7.2],[50000,3.6],[100000,1.6],[250000,.55],[500000,.22],[1000000,.08],
  [2000000,.03],[5000000,.006]];
const FACTORS = { us:1, uk:.26, de:.22, fr:.11, es:.07, it:.07, ca:.09, au:.06, jp:.16, in:.04,
  nl:.03, mx:.03, br:.02, se:.02, pl:.02 };

function salesPerDay(bsr, store, market) {
  const curve = store === "kindle" ? KINDLE_CURVE : PRINT_CURVE;
  if (!bsr || bsr <= 0) return 0;
  const factor = FACTORS[market] ?? 1;
  if (bsr <= curve[0][0]) return curve[0][1] * factor;
  for (let i = 0; i < curve.length - 1; i++) {
    const [x1, y1] = curve[i], [x2, y2] = curve[i + 1];
    if (bsr >= x1 && bsr <= x2) {
      const slope = (Math.log(y2) - Math.log(y1)) / (Math.log(x2) - Math.log(x1));
      return Math.exp(Math.log(y1) + slope * (Math.log(bsr) - Math.log(x1))) * factor;
    }
  }
  const [x1, y1] = curve[curve.length - 2], [x2, y2] = curve[curve.length - 1];
  const slope = (Math.log(y2) - Math.log(y1)) / (Math.log(x2) - Math.log(x1));
  return Math.exp(Math.log(y2) + slope * (Math.log(bsr) - Math.log(x2))) * factor;
}

function printCost(pages, market) {
  const cost = pages <= 108 ? 2.30 : 0.85 + pages * 0.012;
  const factor = { us:1, uk:.85, de:.95, fr:.95, es:.95, it:.95, ca:1.15, au:1.25, jp:1.1 }[market] ?? 1;
  return cost * factor;
}

function royaltyPerSale(price, store, pages, market) {
  if (!price) return 0;
  if (store === "kindle") return (price >= 2.99 && price <= 9.99) ? price * .7 - .15 : price * .35;
  return Math.max(price * .6 - printCost(pages, market), 0);
}

function recalc() {
  const bsr = Number($("#calcBsr").value);
  const store = $("#calcStore").value;
  const market = $("#calcMarket").value || "us";
  const price = Number($("#calcPrice").value);
  const pages = Number($("#calcPages").value) || 120;
  const marketInfo = state.markets.find((m) => m.code === market);
  const symbol = marketInfo ? marketInfo.symbol : "$";
  const perDay = salesPerDay(bsr, store, market);
  const unit = royaltyPerSale(price, store, pages, market);
  $("#calcOut").innerHTML = `
    <div><span>Sales / day</span><b>${fmt(perDay, 1)}</b></div>
    <div><span>Sales / month</span><b>${fmt(perDay * 30)}</b></div>
    <div><span>Royalty / sale</span><b>${symbol}${fmt(unit, 2)}</b></div>
    <div><span>Royalties / month</span><b>${symbol}${fmt(perDay * 30 * unit)}</b></div>
    <div><span>Royalties / year</span><b>${symbol}${fmt(perDay * 365 * unit)}</b></div>`;

  const target = Number($("#calcTarget").value) || 0;
  if (unit > 0 && target > 0) {
    const neededUnits = target / unit;
    let low = 1, high = 5000000;
    for (let i = 0; i < 60; i++) {
      const mid = Math.sqrt(low * high);
      if (salesPerDay(mid, store, market) * 30 > neededUnits) low = mid; else high = mid;
    }
    $("#calcTargetOut").innerHTML = `
      <div><span>Units needed / month</span><b>${fmt(neededUnits)}</b></div>
      <div><span>Units / day</span><b>${fmt(neededUnits / 30, 1)}</b></div>
      <div><span>Required BSR</span><b>#${fmt(Math.sqrt(low * high))}</b></div>`;
  } else {
    $("#calcTargetOut").innerHTML = `<div><span>Required BSR</span><b>—</b></div>`;
  }
}

/* -------------------------------------------------------------- wiring */
function switchTab(name) {
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  $$(".tabpane").forEach((pane) => pane.classList.toggle("active", pane.id === "tab-" + name));
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (target.closest(".tab")) switchTab(target.closest(".tab").dataset.tab);

  if (target.dataset.star) { event.stopPropagation(); toggleSave(target.dataset.star); return; }
  if (target.dataset.saveNiche) { toggleSave(target.dataset.saveNiche); return; }
  if (target.dataset.unsave) {
    const [keyword, marketplace, store] = target.dataset.unsave.split("|");
    api("/api/saved/delete", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, marketplace, store }) }).then(loadSaved);
    return;
  }
  if (target.dataset.reseed) {
    $("#seed").value = target.dataset.reseed;
    closeDrawer(); switchTab("niches"); startSearch(); return;
  }
  if (target.dataset.openrun) { openRun(target.dataset.openrun); return; }
  if (target.dataset.export) {
    if (!state.job) { alert("Run a search first."); return; }
    window.location = `/api/export?job=${state.job}&format=${target.dataset.export}`;
    return;
  }

  const row = target.closest("#nicheTable tbody tr, #savedTable tbody tr");
  if (row && !target.closest("button")) openDrawer(row.dataset.kw);
});

$("#searchBtn").addEventListener("click", startSearch);
$("#seed").addEventListener("keydown", (e) => { if (e.key === "Enter") startSearch(); });
$("#drawerClose").addEventListener("click", closeDrawer);
$("#scrim").addEventListener("click", closeDrawer);
$("#helpBtn").addEventListener("click", () => $("#helpDialog").showModal());
$("#exportSaved").addEventListener("click", () => { window.location = "/api/export?job=saved&format=csv"; });
$("#market").addEventListener("change", () => { syncSymbol(); savePrefs(); });
["#filterText", "#filterRev"].forEach((sel) => $(sel).addEventListener("input", renderNiches));
["#filterScore", "#filterComp"].forEach((sel) => $(sel).addEventListener("input", (e) => {
  $(sel === "#filterScore" ? "#filterScoreVal" : "#filterCompVal").textContent = e.target.value;
  renderNiches();
}));
$$("#nicheTable th[data-sort]").forEach((th) => th.addEventListener("click", () => {
  const key = th.dataset.sort;
  state.sort = { key, dir: state.sort.key === key ? -state.sort.dir : -1 };
  $$("#nicheTable th").forEach((h) => h.classList.remove("sorted"));
  th.classList.add("sorted");
  renderNiches();
}));
["#calcBsr", "#calcStore", "#calcMarket", "#calcPrice", "#calcPages", "#calcTarget"]
  .forEach((sel) => $(sel).addEventListener("input", recalc));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

boot().catch((error) => fail(error.message));
})();
