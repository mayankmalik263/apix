/* APIx dashboard.
   Reads the open tier at /public. Every panel renders independently, so one
   failing chart cannot empty the page. */

const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const inr = v => v == null ? "—" : "₹" + Math.round(v).toLocaleString("en-IN");
const num = v => v == null ? "—" : Number(v).toLocaleString("en-IN");
const pct = v => v == null ? "—" : (v >= 0 ? "+" : "") + Number(v).toFixed(2) + "%";
// Bytes are not currency: lakh grouping on a payload size reads as a mistake.
const bytes = n => n == null ? "—"
  : n >= 1048576 ? (n / 1048576).toFixed(2) + " MB"
  : n >= 1024 ? (n / 1024).toFixed(1) + " KB" : n + " bytes";

const state = { freq: "daily", data: null, view: "index" };
const plots = {};

function plot(id) {
  const el = $(id);
  if (!el || typeof echarts === "undefined") return null;
  if (!plots[id]) plots[id] = echarts.init(el, null, { renderer: "canvas" });
  return plots[id];
}

/* ---------------------------------------------------------------- chrome -- */
const tipStyle = () => ({
  backgroundColor: css("--surface"), borderColor: css("--edge"), borderWidth: 1,
  textStyle: { color: css("--text"), fontSize: 12, fontFamily: '"Archivo", sans-serif' },
  extraCssText: "border-radius:8px;box-shadow:0 12px 32px -12px rgba(0,0,0,.7)",
});
const axisStyle = () => ({
  axisLine: { lineStyle: { color: css("--edge") } },
  axisTick: { show: false },
  axisLabel: { color: css("--text-3"), fontSize: 11, fontFamily: '"IBM Plex Mono", monospace' },
  splitLine: { lineStyle: { color: css("--edge-soft") } },
});
const axisName = () => ({ color: css("--text-3"), fontSize: 10,
  fontFamily: '"IBM Plex Mono", monospace' });
const shell = extra => Object.assign({
  animationDuration: 520, animationEasing: "cubicOut",
  textStyle: { fontFamily: '"Archivo", system-ui, sans-serif', color: css("--text-2") },
  grid: { left: 54, right: 22, top: 26, bottom: 46, containLabel: true },
}, extra);

function rebase(pairs) {
  if (!pairs.length) return [];
  const b = pairs[0][1];
  return b ? pairs.map(p => [p[0], 100 * p[1] / b]) : [];
}

/* ----------------------------------------------------------------- clock -- */
function istParts() {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit",
    second: "2-digit", hour12: false,
  }).formatToParts(new Date()).reduce((a, p) => (a[p.type] = +p.value, a), {});
}
function tick() {
  const p = istParts();
  const pad = n => String(n).padStart(2, "0");
  if ($("clock")) $("clock").textContent = `${pad(p.hour)}:${pad(p.minute)}:${pad(p.second)}`;
  const secs = p.hour * 3600 + p.minute * 60 + p.second, slot = 20 * 3600;
  const left = secs < slot ? slot - secs : 86400 - secs + slot;
  const h = Math.floor(left / 3600), m = Math.floor((left % 3600) / 60);
  if ($("countdown")) $("countdown").textContent =
    h > 0 ? `${h}h ${pad(m)}m` : `${m}m ${pad(left % 60)}s`;
}
setInterval(tick, 1000); tick();

/* ---------------------------------------------------------------- router -- */
const VIEWS = ["index", "leadtime", "basket", "quality", "api", "about"];
function show(v) {
  if (!VIEWS.includes(v)) v = "index";
  state.view = v;
  VIEWS.forEach(x => { const el = $("v-" + x); if (el) el.hidden = x !== v; });
  document.querySelectorAll("#tabs button").forEach(b =>
    b.setAttribute("aria-current", b.dataset.v === v ? "page" : "false"));
  history.replaceState(null, "", "#" + v);
  window.scrollTo(0, 0);
  requestAnimationFrame(resizeAll);
}
$("tabs").addEventListener("click", e => {
  const b = e.target.closest("button[data-v]");
  if (b) show(b.dataset.v);
});
window.addEventListener("hashchange", () => show(location.hash.slice(1)));

function resizeAll() { Object.keys(plots).forEach(k => plots[k] && plots[k].resize()); }
let rz; window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(resizeAll, 130); });

/* ------------------------------------------------------------------ data -- */
async function getJSON(path) {
  const r = await fetch(path, { cache: "no-store", credentials: "same-origin" });
  if (!r.ok) throw new Error(path + " → " + r.status);
  return r.json();
}
function warn(msg) {
  const el = $("alert");
  if (!msg) { el.hidden = true; return; }
  el.innerHTML = msg; el.hidden = false;
}

/* ------------------------------------------------------------------ hero -- */
function countUp(el, target, decimals) {
  const from = parseFloat(el.textContent.replace(/,/g, "")) || 0;
  if (!isFinite(target)) { el.textContent = "—"; return; }
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.textContent = target.toFixed(decimals); return;
  }
  const t0 = performance.now(), dur = 620;
  (function step(t) {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = (from + (target - from) * e).toFixed(decimals);
    if (k < 1) requestAnimationFrame(step);
  })(performance.now());
}

function renderHero(d) {
  const s = d.series, t = d.latest;
  $("hero-tag").textContent = "Airfare Price Index · " + d.frequency +
    (d.using_generated_history ? " · generated history" : " · measured");
  if (!t) return;

  countUp($("hero-val"), t.apix, 2);

  const dl = $("hero-delta");
  if (t.change_pct == null) { dl.textContent = "base period"; dl.className = "hero-delta flat"; }
  else { dl.textContent = pct(t.change_pct); dl.className = "hero-delta " + (t.change_pct >= 0 ? "up" : "down"); }

  const first = s[0] ? (s[0].period_start || s[0].observation_date) : "—";
  $("hero-sub").innerHTML = d.using_generated_history
    ? `Every figure on this page comes from the <b>labelled generated series</b>, not a measured
       fare. Base ${first} = 100.`
    : `Measured from <b>${num(d.spread.n || 0)} fares</b> priced on ${d.observation_date} across
       six routes and five booking windows. Base ${first} = 100.`;

  $("g-cov").textContent = Math.round(t.coverage * 100) + "%";
  $("g-cells").textContent = t.n_observed != null
    ? `${t.n_observed} of ${t.n_expected} cells` : `${t.n_days} days averaged`;
  $("g-grade").textContent = t.confidence;
  $("g-grade").className = "v g" + t.confidence;
  $("g-why").textContent = t.confidence === "A" ? "two portals corroborating"
    : t.confidence === "B" ? "complete, single source" : "below 0.70 — provisional";

  if (d.spread && d.spread.n) {
    $("g-fares").textContent = num(d.spread.n);
    $("g-car").textContent = d.carriers.length + " carriers";
    $("g-med").textContent = inr(d.spread.median);
    $("g-range").textContent = inr(d.spread.min) + " – " + inr(d.spread.max);
  }

  // ambient sparkline behind the readout
  const p = plot("spark");
  if (p) p.setOption({
    animation: false, grid: { left: 0, right: 0, top: 6, bottom: 0 },
    xAxis: { type: "category", show: true, boundaryGap: false,
      data: s.map(r => r.observation_date), axisLine: { show: false },
      axisTick: { show: false }, axisLabel: { show: false } },
    yAxis: { type: "value", show: false, scale: true },
    series: [{
      type: "line", data: s.map(r => r.apix), showSymbol: false, smooth: .18,
      lineStyle: { width: 1.4, color: css("--beam"), opacity: .55 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: css("--beam") + "44" }, { offset: 1, color: "transparent" }]) },
    }],
  }, true);
}

/* ------------------------------------------------------------ main chart -- */
function renderMain(d, mospi) {
  const p = plot("p-main"); if (!p) return;
  const mo = (mospi && mospi.available)
    ? mospi.observations.map(o => [o.period + "-15", o.index]) : [];

  // Both series are drawn, always. The generated history gives the measured
  // points something to sit against; it is dashed, amber and named as
  // generated so the two can never be read as the same thing.
  const measured  = d.source_class === "LIVE" ? d.series : [];
  const generated = d.source_class === "LIVE" ? d.context_series : d.series;

  const asPairs = rows => rows.filter(r => r.apix != null)
    .map(r => [r.period_start || r.observation_date, r.apix]);

  p.setOption(shell({
    tooltip: Object.assign({ trigger: "axis",
      valueFormatter: v => v == null ? "—" : Number(v).toFixed(2) }, tipStyle()),
    // Legend on top: at the bottom it sat underneath the zoom slider.
    legend: { top: 0, left: 0, itemGap: 18, icon: "roundRect", itemWidth: 16, itemHeight: 3,
      textStyle: { color: css("--text-2"), fontSize: 11 } },
    // The official series spans two and a half years; ours is daily over
    // months. Without a zoom the daily stretch is an unreadable smear at the
    // right-hand edge.
    dataZoom: [
      // Open on the recent months so the daily series is legible; the slider
      // pulls back to the full official history.
      { type: "inside", filterMode: "none", start: 68, end: 100 },
      { type: "slider", height: 16, bottom: 8, filterMode: "none",
        start: 68, end: 100,
        borderColor: css("--edge"), backgroundColor: "transparent",
        fillerColor: css("--beam") + "1F", handleStyle: { color: css("--beam") },
        moveHandleStyle: { color: css("--edge") },
        textStyle: { color: css("--text-3"), fontSize: 9.5,
          fontFamily: '"IBM Plex Mono", monospace' },
        dataBackground: { lineStyle: { color: css("--edge") },
          areaStyle: { color: css("--edge-soft") } } },
    ],
    grid: { left: 54, right: 22, top: 56, bottom: 62, containLabel: true },
    xAxis: Object.assign({ type: "time" }, axisStyle(), { splitLine: { show: false } }),
    yAxis: Object.assign({ type: "value", scale: true, name: "index · own base = 100",
      nameTextStyle: axisName(), nameGap: 14 }, axisStyle(), { axisLine: { show: false } }),
    series: [
      { name: "Official airfare item · monthly", type: "line", step: "end",
        data: rebase(mo), color: css("--slate"), lineStyle: { width: 2 },
        symbol: "circle", symbolSize: 5 },
      { name: "APIx · generated history", type: "line", showSymbol: false,
        data: rebase(asPairs(generated)), color: css("--amber"),
        lineStyle: { width: 1.4, type: "dashed" } },
      { name: "APIx · measured", type: "line", symbol: "circle", symbolSize: 8,
        data: rebase(asPairs(measured)), color: css("--beam"),
        lineStyle: { width: 2.8 },
        areaStyle: measured.length > 1 ? { opacity: .1, color: css("--beam") } : undefined },
    ],
  }), true);
}

function renderRoutes(d) {
  const p = plot("p-routes"); if (!p || !d.routes.length) return;
  const rows = d.routes.filter(r => r.route_index != null);
  // Plotted as deviation from the base, not as the raw index. A bar chart
  // anchored at the axis floor renders six identical full-width bars on the
  // base day, which says nothing; diverging from zero shows the actual move.
  const dev = rows.map(r => +(r.route_index - 100).toFixed(3));
  const flat = dev.every(v => Math.abs(v) < .01);
  const cap = document.querySelector("#p-routes")?.closest(".card")?.querySelector(".card-h p");
  if (cap) cap.textContent = flat
    ? "This is the base day, so every route reads exactly 100 by construction. "
      + "Movement appears from the second collection day."
    : "Deviation from each route's own base. Red is dearer, green is cheaper.";
  const span = Math.max(1, ...dev.map(Math.abs)) * 1.25;
  p.setOption(shell({
    grid: { left: 72, right: 30, top: 18, bottom: 34, containLabel: true },
    tooltip: Object.assign({ trigger: "axis", axisPointer: { type: "shadow" },
      formatter: a => {
        const r = rows[a[0].dataIndex];
        return `<b>${r.route_code}</b><br>index ${r.route_index.toFixed(2)}
                <br>${pct(r.route_index - 100)} vs base
                <br><span style="color:${css("--text-3")}">${r.n_windows_used} of 5 windows</span>`;
      } }, tipStyle()),
    xAxis: Object.assign({ type: "value", min: -span, max: span,
      name: "% from base", nameTextStyle: axisName(), nameGap: 16,
      axisLabel: { color: css("--text-3"), fontSize: 10,
        fontFamily: '"IBM Plex Mono", monospace',
        formatter: v => (v > 0 ? "+" : "") + v.toFixed(1) } }, axisStyle()),
    yAxis: Object.assign({ type: "category", data: rows.map(r => r.route_code) },
      axisStyle(), { splitLine: { show: false }, axisLine: { show: false } }),
    series: [{
      type: "bar", data: dev, barMaxWidth: 15,
      itemStyle: {
        borderRadius: 3,
        color: pm => Math.abs(pm.value) < .01 ? css("--text-3")
          : pm.value > 0 ? css("--alert") : css("--clear"),
      },
      label: { show: true, position: "right", fontSize: 10.5,
        fontFamily: '"IBM Plex Mono", monospace', color: css("--text-2"),
        formatter: pm => rows[pm.dataIndex].route_index.toFixed(2) },
      markLine: { silent: true, symbol: "none",
        lineStyle: { color: css("--edge"), width: 1 },
        label: { show: false }, data: [{ xAxis: 0 }] },
    }],
  }), true);
}

function renderCoverage(d) {
  const p = plot("p-cov"); if (!p) return;
  // Show whichever history is longer, so a single measured day does not draw
  // a chart with one bar and no axis.
  const ctx = d.context_series || [];
  const s = ctx.length > d.daily_series.length
    ? ctx.concat(d.daily_series) : d.daily_series;
  p.setOption(shell({
    grid: { left: 46, right: 18, top: 18, bottom: 30, containLabel: true },
    tooltip: Object.assign({ trigger: "axis",
      valueFormatter: v => Number(v).toFixed(0) + "%" }, tipStyle()),
    xAxis: Object.assign({ type: "time" }, axisStyle(), { splitLine: { show: false } }),
    yAxis: Object.assign({ type: "value", max: 100, name: "%", nameTextStyle: axisName() },
      axisStyle(), { axisLine: { show: false } }),
    series: [{
      type: "bar", barMaxWidth: 6,
      data: s.map(r => [r.observation_date, 100 * r.coverage]),
      itemStyle: { color: pm => pm.value[1] >= 90 ? css("--clear")
        : pm.value[1] >= 70 ? css("--amber") : css("--alert") },
    }],
  }), true);
}

/* -------------------------------------------------------------- lead time -- */
function renderLeadTime(d) {
  const lt = d.lead_time;
  if (!lt || !lt.available) return;

  const cheapest = lt.curve.find(c => c.window_days === lt.cheapest_window);
  $("insight-big").textContent =
    `Booking earliest is not booking cheapest. The floor is T+${lt.cheapest_window}.`;
  $("insight-p1").innerHTML =
    `Across all six routes the median fare bottoms out at <b>T+${lt.cheapest_window}</b> —
     ${inr(lt.cheapest_median)} — and rises to ${inr(lt.dearest_median)} at
     T+${lt.dearest_window}. That is a spread of <b>${lt.spread_pct}%</b> for the same seat
     specification, driven only by when you look.`;
  $("insight-p2").innerHTML = lt.u_shaped
    ? `The curve turns back up at long lead times: T+${lt.curve[lt.curve.length - 1].window_days}
       is dearer than the floor, so the cheapest moment is a window in the middle rather than as
       early as possible. A monthly national average cannot carry this shape, which is why no
       official series reports it.`
    : `The curve falls monotonically with lead time on this day. Whether it turns back up is
       exactly the kind of question a daily route-level series can answer and a monthly national
       average cannot.`;

  const p = plot("p-lead");
  if (p) p.setOption(shell({
    grid: { left: 66, right: 26, top: 26, bottom: 40, containLabel: true },
    tooltip: Object.assign({ trigger: "axis", valueFormatter: inr }, tipStyle()),
    xAxis: Object.assign({ type: "category", data: lt.curve.map(c => "T+" + c.window_days),
      name: "booking window", nameLocation: "middle", nameGap: 28,
      nameTextStyle: axisName() }, axisStyle()),
    yAxis: Object.assign({ type: "value", scale: true, name: "median fare",
      nameTextStyle: axisName() }, axisStyle(), { axisLine: { show: false } }),
    series: [{
      type: "line", data: lt.curve.map(c => c.median), smooth: .28,
      color: css("--beam"), lineStyle: { width: 3 }, symbol: "circle", symbolSize: 9,
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: css("--beam") + "38" }, { offset: 1, color: "transparent" }]) },
      markPoint: {
        symbolSize: 46, data: [{ type: "min", name: "cheapest" }],
        itemStyle: { color: css("--clear") },
        label: { formatter: "min", color: css("--ink"), fontSize: 10, fontWeight: 600 },
      },
    }],
  }), true);

  const tb = document.querySelector("#t-lead tbody");
  tb.innerHTML = lt.curve.map(c => {
    const cls = c.change_pct == null ? "" : c.change_pct > 0 ? "up" : "down";
    return `<tr><td><strong>T+${c.window_days}</strong></td>
      <td class="num">${inr(c.median)}</td>
      <td class="num ${cls}">${c.change_pct == null ? "—" : pct(c.change_pct)}</td>
      <td class="num">${c.pct_per_day == null ? "—" : c.pct_per_day.toFixed(2) + "%"}</td></tr>`;
  }).join("");

  const pr = plot("p-leadroutes");
  if (pr && lt.by_route.length) {
    const wins = lt.curve.map(c => c.window_days);
    pr.setOption(shell({
      grid: { left: 66, right: 26, top: 22, bottom: 54, containLabel: true },
      tooltip: Object.assign({ trigger: "axis", valueFormatter: inr }, tipStyle()),
      legend: { bottom: 0, itemGap: 14, icon: "roundRect", itemWidth: 14, itemHeight: 3,
        textStyle: { color: css("--text-2"), fontSize: 11 } },
      xAxis: Object.assign({ type: "category", data: wins.map(w => "T+" + w) }, axisStyle()),
      yAxis: Object.assign({ type: "value", scale: true, name: "median fare",
        nameTextStyle: axisName() }, axisStyle(), { axisLine: { show: false } }),
      series: lt.by_route.map(r => ({
        name: r.route_code, type: "line", smooth: .2, symbolSize: 6,
        data: wins.map(w => { const pt = r.points.find(x => x.window_days === w);
                              return pt ? pt.median : null; }),
      })),
    }), true);
  }
}

/* ---------------------------------------------------------------- basket -- */
let heatMeta = null;

function renderBasket(d) {
  const cells = d.cells;
  if (!cells.length) return;
  const routes = [...new Set(cells.map(c => c.route_code))];
  const wins = [...new Set(cells.map(c => c.window_days))].sort((a, b) => a - b);
  heatMeta = { routes, wins, date: d.observation_date, sc: d.source_class };

  const pts = [], vals = [];
  cells.forEach(c => {
    if (c.median_fare == null) return;
    pts.push([wins.indexOf(c.window_days), routes.indexOf(c.route_code), c.median_fare]);
    vals.push(c.median_fare);
  });

  const p = plot("p-heat");
  if (p && pts.length) {
    p.setOption({
      animationDuration: 480,
      textStyle: { fontFamily: '"Archivo", sans-serif' },
      grid: { left: 88, right: 28, top: 16, bottom: 78, containLabel: true },
      tooltip: Object.assign({ formatter: pm =>
        `<b>${routes[pm.data[1]]}</b> · T+${wins[pm.data[0]]}<br>${inr(pm.data[2])}
         <br><span style="color:${css("--text-3")};font-size:11px">click for provenance</span>`
      }, tipStyle()),
      xAxis: Object.assign({ type: "category", data: wins.map(w => "T+" + w) },
        axisStyle(), { splitLine: { show: false } }),
      yAxis: Object.assign({ type: "category", data: routes }, axisStyle(),
        { splitLine: { show: false } }),
      visualMap: {
        min: Math.min.apply(null, vals), max: Math.max.apply(null, vals), calculable: true,
        orient: "horizontal", left: "center", bottom: 8, itemWidth: 12, itemHeight: 130,
        textStyle: { color: css("--text-3"), fontSize: 10,
          fontFamily: '"IBM Plex Mono", monospace' },
        formatter: v => "₹" + Math.round(v / 1000) + "k",
        inRange: { color: ["#0E2B3B", "#175A78", "#2E90B8", "#5CC8F5", "#F2A649", "#FF5C5C"] },
      },
      series: [{
        type: "heatmap", data: pts,
        label: { show: true, fontSize: 10.5, color: "#040709",
          fontFamily: '"IBM Plex Mono", monospace', fontWeight: 500,
          formatter: pm => Math.round(pm.data[2] / 1000) + "k" },
        itemStyle: { borderColor: css("--surface"), borderWidth: 3, borderRadius: 3 },
        emphasis: { itemStyle: { borderColor: css("--text"), borderWidth: 2 } },
      }],
    }, true);
    p.off("click");
    p.on("click", e => {
      if (!e.data) return;
      openLineage(heatMeta.routes[e.data[1]], heatMeta.wins[e.data[0]]);
    });
  }

  const st = s => s === "OK" ? "c-ok" : (s === "SOLD_OUT" || s === "NO_SERVICE") ? "c-wn" : "c-no";
  document.querySelector("#t-cells tbody").innerHTML = cells.map(c =>
    `<tr class="tap" tabindex="0" data-r="${c.route_code}" data-w="${c.window_days}">
      <td><strong>${c.route_code}</strong></td><td>T+${c.window_days}</td>
      <td class="num">${inr(c.median_fare)}</td><td class="num">${c.n_used}</td>
      <td class="num">${c.n_outliers_flagged}</td>
      <td><span class="chip ${st(c.status)}">${c.status}</span></td></tr>`).join("");

  document.querySelectorAll("#t-cells tr.tap").forEach(tr => {
    const go = () => openLineage(tr.dataset.r, +tr.dataset.w);
    tr.addEventListener("click", go);
    tr.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });

  renderComposition(d.composition);
}

function renderComposition(c) {
  const p = plot("p-comp");
  if (!p) return;
  if (!c || !c.available) {
    $("comp-note").textContent = c && c.reason ? c.reason
      : "This source does not break the fare down.";
    return;
  }
  $("comp-note").innerHTML =
    `Taxes and fees are <b>${c.tax_share_pct}%</b> of the total fare. The brief requires base fare
     to be separated from taxes, user development fee and convenience charges — this is that split,
     averaged per route.`;
  const rows = c.by_route;
  p.setOption(shell({
    grid: { left: 72, right: 22, top: 20, bottom: 42, containLabel: true },
    tooltip: Object.assign({ trigger: "axis", axisPointer: { type: "shadow" },
      valueFormatter: inr }, tipStyle()),
    legend: { bottom: 0, itemGap: 16, icon: "roundRect", itemWidth: 11, itemHeight: 11,
      textStyle: { color: css("--text-2"), fontSize: 11 } },
    xAxis: Object.assign({ type: "value", name: "₹", nameTextStyle: axisName() }, axisStyle()),
    yAxis: Object.assign({ type: "category", data: rows.map(r => r.route_code) },
      axisStyle(), { splitLine: { show: false } }),
    series: [
      { name: "Base fare", type: "bar", stack: "f", data: rows.map(r => r.base_fare),
        color: css("--beam"), barMaxWidth: 18, itemStyle: { borderRadius: [4, 0, 0, 4] } },
      { name: "Taxes", type: "bar", stack: "f", data: rows.map(r => r.taxes),
        color: css("--amber"), barMaxWidth: 18 },
      { name: "Fees", type: "bar", stack: "f", data: rows.map(r => r.fees),
        color: css("--slate"), barMaxWidth: 18, itemStyle: { borderRadius: [0, 4, 4, 0] } },
    ],
  }), true);
}

/* --------------------------------------------------------------- quality -- */
function renderQuality(d) {
  const s = d.spread;
  if (s && s.n) {
    $("dist-note").innerHTML =
      `${num(s.n)} fares priced. Cheapest ${inr(s.min)}, median <b>${inr(s.median)}</b>,
       dearest ${inr(s.max)}. The mean is ${inr(s.mean)} — a price almost nobody paid,
       which is why the index takes the median.`;
  }

  const p = plot("p-hist");
  if (p && d.histogram.length) {
    const mi = s && s.median != null
      ? d.histogram.findIndex(h => s.median >= h.from && s.median < h.to) : -1;
    p.setOption(shell({
      grid: { left: 48, right: 18, top: 20, bottom: 38, containLabel: true },
      tooltip: Object.assign({ trigger: "axis", formatter: a =>
        `${inr(a[0].data[2])} – ${inr(a[0].data[3])}<br><b>${a[0].data[1]}</b> fares` }, tipStyle()),
      xAxis: Object.assign({ type: "category",
        data: d.histogram.map(h => "₹" + Math.round(h.from / 1000) + "k") },
        axisStyle(), { axisLabel: { color: css("--text-3"), fontSize: 10, interval: 3,
          fontFamily: '"IBM Plex Mono", monospace' } }),
      yAxis: Object.assign({ type: "value", name: "fares", nameTextStyle: axisName() },
        axisStyle(), { axisLine: { show: false } }),
      series: [{
        type: "bar", data: d.histogram.map((h, i) => [i, h.count, h.from, h.to]),
        itemStyle: { color: css("--beam"), borderRadius: [2, 2, 0, 0] },
        markLine: mi >= 0 ? { silent: true, symbol: "none",
          lineStyle: { color: css("--clear"), type: "dashed", width: 1.4 },
          label: { formatter: "median", color: css("--clear"), fontSize: 10 },
          data: [{ xAxis: mi }] } : undefined,
      }],
    }), true);
  }

  const colour = { MARKET: "--clear", POLICY: "--amber", SYSTEM: "--alert" };
  const ps = plot("p-status");
  if (ps && d.status_mix.length) {
    ps.setOption({
      animationDuration: 520,
      textStyle: { fontFamily: '"Archivo", sans-serif' },
      tooltip: Object.assign({ formatter: pm =>
        `<b>${pm.name}</b><br>${num(pm.value)} rows (${pm.percent}%)
         <br><span style="color:${css("--text-3")}">${d.status_mix[pm.dataIndex].status_class}</span>`
      }, tipStyle()),
      legend: { bottom: 0, itemGap: 12, icon: "circle",
        textStyle: { color: css("--text-2"), fontSize: 10.5 } },
      series: [{
        type: "pie", radius: ["52%", "74%"], center: ["50%", "44%"],
        itemStyle: { borderColor: css("--surface"), borderWidth: 3 },
        label: { show: false }, labelLine: { show: false },
        data: d.status_mix.map(r => ({ name: r.status, value: r.n,
          itemStyle: { color: css(colour[r.status_class] || "--text-3") } })),
      }],
    }, true);
  }
}

function renderOutliers(rows) {
  document.querySelector("#t-out tbody").innerHTML = rows.length
    ? rows.slice(0, 14).map(r =>
      `<tr><td><strong>${r.route_code}</strong></td><td>T+${r.window_days}</td>
        <td>${r.carrier || "—"}</td><td class="num">${inr(r.total_fare)}</td>
        <td class="num">${r.outlier_score == null ? "—" : r.outlier_score.toFixed(2)}</td></tr>`).join("")
    : `<tr><td colspan="5" style="color:var(--text-3)">No fares flagged.</td></tr>`;
}

function renderCompliance(c) {
  if (!c) return;
  $("g-src").textContent = c.permitted + " / " + c.total;
  $("rail").innerHTML = c.sources.map(s => `
    <div class="src ${s.verdict === "PERMITTED" ? "on" : ""}">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
        <span class="nm">${s.name}</span>
        <span class="chip ${s.verdict === "PERMITTED" ? "c-ok" : "c-no"}">${s.verdict}</span>
      </div>
      <div class="hs">${s.sha256 && s.sha256 !== "-" ? s.sha256 : s.reason.slice(0, 58)}</div>
    </div>`).join("");
}

/* ---------------------------------------------------------------- drawer -- */
function closeDrawer() {
  $("drawer").classList.remove("on");
  $("drawer").setAttribute("aria-hidden", "true");
  $("scrim").classList.remove("on");
}
$("dr-close").addEventListener("click", closeDrawer);
$("scrim").addEventListener("click", closeDrawer);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });

async function openLineage(route, window_days) {
  if (!heatMeta) return;
  const d = $("drawer");
  d.classList.add("on"); d.setAttribute("aria-hidden", "false");
  $("scrim").classList.add("on");
  $("dr-title").textContent = `${route} · T+${window_days}`;
  $("dr-sub").textContent = heatMeta.date + " · " + heatMeta.sc;
  $("dr-body").innerHTML = `<p style="color:var(--text-3)">Walking the chain…</p>`;

  try {
    const L = await getJSON(`/public/lineage/${heatMeta.date}/${route}/${window_days}`
      + `?source_class=${heatMeta.sc}`);
    const g = L.gold || {};
    const used = L.silver.filter(f => f.status === "OK" && !f.is_outlier);
    const sample = L.silver.slice(0, 6);
    const raw = L.bronze[0];

    $("dr-body").innerHTML = `
      <div class="step">
        <span class="lbl">Published — gold_cell_median</span>
        <div class="val">${inr(g.median_fare)}</div>
        <div class="det">Median of ${L.used_in_median} fares, ${L.flagged} flagged and excluded.
          Price relative ${g.price_relative == null ? "—" : g.price_relative.toFixed(4)}.</div>
      </div>

      <div class="step">
        <span class="lbl">Parsed — silver_fare_observation</span>
        <div class="val">${num(L.silver_count)} fare rows</div>
        <div class="det">Every quote the search returned, each with a status and an outlier score.
          Flagged rows stay in the table; they are excluded from the median, never deleted.</div>
        <div class="scroll" style="margin-top:10px">
          <table style="min-width:0;font-size:12px">
            <thead><tr><th>Carrier</th><th style="text-align:right">Base</th>
              <th style="text-align:right">Tax</th><th style="text-align:right">Total</th>
              <th style="text-align:right">Z</th></tr></thead>
            <tbody>${sample.map(f => `<tr>
              <td>${f.carrier || "—"}</td>
              <td class="num">${inr(f.base_fare)}</td>
              <td class="num">${inr(f.taxes)}</td>
              <td class="num">${inr(f.total_fare)}</td>
              <td class="num" style="color:${f.is_outlier ? css("--alert") : "inherit"}">
                ${f.outlier_score == null ? "—" : f.outlier_score.toFixed(2)}</td></tr>`).join("")}
            </tbody></table>
        </div>
        <div class="det" style="margin-top:6px">Showing 6 of ${num(L.silver_count)}.</div>
      </div>

      <div class="step">
        <span class="lbl">Stored — bronze archive</span>
        <div class="val">${raw ? bytes(raw.payload_bytes) : "no payload"}</div>
        <div class="det">${raw ? `Captured from <code>${raw.source_id}</code> at
          ${(raw.fetched_at_utc || "").slice(0, 19)} UTC, status ${raw.fetch_status}.
          The response was written before anything parsed it, so this cell can be re-derived if the
          parser ever changes.` : "No stored payload for this cell."}</div>
        ${raw && raw.payload_sha256
          ? `<div class="hashbox">sha256 ${raw.payload_sha256}</div>` : ""}
      </div>`;
  } catch (err) {
    $("dr-body").innerHTML = `<p style="color:var(--alert)">Could not load provenance: ${err.message}</p>`;
  }
}

/* ------------------------------------------------------------------ load -- */
function guarded(name, fn) {
  try { fn(); } catch (e) { console.error("APIx: " + name, e); }
}

async function load() {
  let d, mospi, comp;
  try {
    [d, mospi, comp] = await Promise.all([
      getJSON(`/public/overview?freq=${state.freq}`),
      getJSON("/public/mospi").catch(() => null),
      getJSON("/public/compliance/report").catch(() => null),
    ]);
  } catch (err) {
    warn(`<strong>The API is not answering.</strong> Start it with
      <code>python -m webapp.run</code> and reload.`);
    return;
  }

  state.data = d;
  warn(d.using_generated_history
    ? `<strong>Showing the labelled generated series.</strong> No measured collection day has been
       indexed yet, so every figure comes from the documented model rather than an observed fare.`
    : null);

  guarded("hero", () => renderHero(d));
  guarded("main", () => renderMain(d, mospi));
  guarded("routes", () => renderRoutes(d));
  guarded("coverage", () => renderCoverage(d));
  guarded("leadtime", () => renderLeadTime(d));
  guarded("basket", () => renderBasket(d));
  guarded("quality", () => renderQuality(d));
  guarded("outliers", () => renderOutliers(d.outliers || []));
  guarded("compliance", () => renderCompliance(comp));
  guarded("api", () => {
    const t = d.latest || {};
    $("api-sample").textContent = "GET /v1/apix/latest\n\n" +
      JSON.stringify({ available: true, source_class: d.source_class, ...t }, null, 2);
  });
}

$("freq").addEventListener("click", async e => {
  const b = e.target.closest("button[data-f]"); if (!b) return;
  state.freq = b.dataset.f;
  document.querySelectorAll("#freq button").forEach(x =>
    x.setAttribute("aria-pressed", String(x === b)));
  await load();
});

show(location.hash.slice(1) || "index");
load();
setInterval(load, 60000);
