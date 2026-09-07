/* Operator console. Everything here needs a session; a 401 returns to login. */
const $ = id => document.getElementById(id);
const num = v => v == null ? "—" : Number(v).toLocaleString("en-IN");
const when = s => !s ? "—" : s.replace("T", " ").slice(0, 19);

function tick() {
  const p = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit",
    minute: "2-digit", second: "2-digit", hour12: false })
    .formatToParts(new Date()).reduce((a, x) => (a[x.type] = +x.value, a), {});
  const pad = n => String(n).padStart(2, "0");
  $("clock").textContent = `${pad(p.hour)}:${pad(p.minute)}:${pad(p.second)}`;
  const secs = p.hour * 3600 + p.minute * 60 + p.second, slot = 20 * 3600;
  const left = secs < slot ? slot - secs : 86400 - secs + slot;
  const h = Math.floor(left / 3600), m = Math.floor((left % 3600) / 60);
  const txt = h > 0 ? `${h}h ${pad(m)}m` : `${m}m ${pad(left % 60)}s`;
  $("countdown").textContent = txt;
  if ($("o-next")) $("o-next").textContent = txt;
}
setInterval(tick, 1000); tick();

async function api(path, opts) {
  const r = await fetch(path, Object.assign({ credentials: "same-origin" }, opts));
  const body = await r.json().catch(() => ({}));
  if (r.status === 401) { location.href = "/login?next=/console"; throw new Error("signed out"); }
  if (!r.ok) throw new Error(body.detail || `${r.status} ${r.statusText}`);
  return body;
}
const post = (p, b) => api(p, { method: "POST",
  headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) });

function say(el, text, colour) {
  el.textContent = text;
  el.style.borderLeftColor = `var(--${colour || "beam"})`;
  el.hidden = false;
}

async function loadStatus() {
  const s = await api("/v1/system/status");
  $("o-sched").textContent = s.scheduler_running ? "ON" : "OFF";
  $("o-sched").className = "v " + (s.scheduler_running ? "gA" : "gC");
  $("o-slot").textContent = "daily at " + s.slot_ist + " IST";
  $("o-today").textContent = s.collected_today ? "today collected" : "today not yet collected";
  const c = s.counts;
  $("o-bronze").textContent = num(c.bronze_records);
  $("o-bdays").textContent = c.bronze_days + " days archived";
  $("o-silver").textContent = num(c.silver_rows);
  $("o-flag").textContent = num(c.outliers_flagged) + " flagged, none deleted";
  $("o-days").textContent = num(c.published_days);
  $("o-live").textContent = c.live_days + " measured";
  $("o-calls").textContent = num(c.api_calls_24h);
  $("o-keys").textContent = c.active_api_keys + " active keys";
}

async function loadRuns() {
  const d = await api("/console/api/runs?limit=20");
  const cls = s => s === "OK" ? "c-ok" : s === "FAILED" ? "c-no" : "c-wn";
  document.querySelector("#t-runs tbody").innerHTML = d.runs.length
    ? d.runs.map(r => `<tr><td class="mono" style="font-size:11.5px">${when(r.started_at)}</td>
        <td>${r.observation_date}</td><td>${r.trigger}</td>
        <td><span class="chip ${cls(r.status)}">${r.status}</span></td>
        <td class="num">${r.cells_ok} / ${r.cells_attempted}</td>
        <td>${r.sources_used || "—"}</td></tr>`).join("")
    : `<tr><td colspan="6" style="color:var(--text-3)">No runs recorded yet.</td></tr>`;
}

async function loadKeys() {
  const d = await api("/console/api/keys");
  const tb = document.querySelector("#t-keys tbody");
  tb.innerHTML = d.keys.length ? d.keys.map(k => `<tr>
      <td><strong>${k.label}</strong>${k.organisation
        ? `<br><span style="color:var(--text-3);font-size:11.5px">${k.organisation}</span>` : ""}</td>
      <td class="mono" style="font-size:11.5px">${k.prefix}…</td>
      <td class="mono" style="font-size:10.5px">${k.scopes}</td>
      <td class="num">${num(k.request_count)}</td>
      <td><span class="chip ${k.status === "active" ? "c-ok" : "c-mt"}">${k.status}</span></td>
      <td>${k.revoked_at ? "" :
        `<button class="chip c-no" style="cursor:pointer;background:none"
          data-revoke="${k.id}">Revoke</button>`}</td></tr>`).join("")
    : `<tr><td colspan="6" style="color:var(--text-3)">No keys issued yet.</td></tr>`;

  tb.querySelectorAll("[data-revoke]").forEach(b => b.onclick = async () => {
    const reason = prompt("Why is this key being revoked?", "rotated");
    if (reason === null) return;
    try { await post(`/console/api/keys/${b.dataset.revoke}/revoke`, { reason }); await loadKeys(); }
    catch (e) { alert(e.message); }
  });
}

async function loadLog() {
  const d = await api("/console/api/access-log?limit=80");
  document.querySelector("#t-log tbody").innerHTML = d.entries.length
    ? d.entries.map(e => `<tr>
        <td class="mono" style="font-size:11px">${when(e.at_utc)}</td>
        <td>${e.label || '<span style="color:var(--text-3)">unrecognised key</span>'}</td>
        <td class="mono" style="font-size:11px">${e.path}</td>
        <td><span class="chip ${e.status_code < 400 ? "c-ok" : "c-no"}">${e.status_code}</span></td>
      </tr>`).join("")
    : `<tr><td colspan="4" style="color:var(--text-3)">No API calls recorded yet.</td></tr>`;
}

$("run").onclick = async () => {
  const b = $("run"); b.disabled = true; b.textContent = "Starting…";
  try {
    const r = await post("/console/api/collect-now");
    say($("msg"), r.started ? r.message : r.reason, r.started ? "clear" : "amber");
    setTimeout(() => { loadRuns(); loadStatus(); }, 2000);
  } catch (e) { say($("msg"), e.message, "alert"); }
  finally { b.disabled = false; b.textContent = "Collect now"; }
};

$("mint").onclick = async () => {
  const label = $("k-label").value.trim();
  if (!label) { alert("Give the key a label so it can be recognised later."); return; }
  const b = $("mint"); b.disabled = true;
  try {
    const r = await post("/console/api/keys", { label, scopes: $("k-scopes").value });
    const box = $("newkey");
    box.innerHTML = `<strong>Copy this now — it cannot be shown again.</strong>
      <div style="font-family:var(--mono);font-size:12.5px;color:var(--clear);
        word-break:break-all;margin-top:8px">${r.key}</div>`;
    box.hidden = false;
    $("k-label").value = "";
    await loadKeys();
  } catch (e) { alert(e.message); }
  finally { b.disabled = false; }
};

async function boot() {
  try { await Promise.all([loadStatus(), loadRuns(), loadKeys(), loadLog()]); $("alert").hidden = true; }
  catch (e) { if (e.message !== "signed out") say($("alert"), e.message, "alert"); }
}
boot();
setInterval(boot, 20000);
