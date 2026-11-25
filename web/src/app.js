/*APP-START*/
const E = ENGINE;
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const r0 = v => Math.round(v);
const fmtDur = h => { const m = Math.round(h * 60); return m < 60 ? `${m} min` : (m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m / 60} h`); };
const bandOf = r => r >= 70 ? 'good' : r >= 50 ? 'warn' : 'crit';

const SAMPLE_CREW = [
  { id: 'cdr', name: 'R. Okafor', role: 'Commander', tau: 24.15, need: 7.5 },
  { id: 'plt', name: 'M. Lindqvist', role: 'Pilot', tau: 24.35, need: 8 },
  { id: 'ms1', name: 'A. Reyes', role: 'Mission Specialist 1', tau: 24.05, need: 8 },
  { id: 'ms2', name: 'K. Tanaka', role: 'Mission Specialist 2', tau: 24.25, need: 7.5 }
];
const SAMPLE_SLAM = { delta: -4, startDay: 2, crit: { label: 'Docking: logistics vehicle', day: 6, start: 6, dur: 3 } };

const App = { st: null, plans: {}, live: {}, t: 2 * 24 + 4 + 35 / 60, view: 'crew', crewSel: 'cdr', drafts: [], preview: null, status: 'NOMINAL', bootLog: [], lastBoot: null, val: null, mc: null, mcRunning: false };

// ---------- Triple-redundant RAM cell for the active-timeline map ----------
const TMR = { a: '', b: '', c: '' };
function tmrSet(v) { TMR.a = TMR.b = TMR.c = v; }
function tmrGet() { const { a, b, c } = TMR; return a === b || a === c ? a : b === c ? b : a; }
function tmrScrub() {
  const { a, b, c } = TMR; if (a === b && b === c) return;
  const v = tmrGet(); const bad = a !== v ? 'A' : b !== v ? 'B' : 'C';
  tmrSet(v);
  Store.append('fault', { kind: 'ram', msg: `RAM copy ${bad} of active-timeline map disagreed; rewritten from majority.` });
  App.st = reduce(Store.records);
  toast(`Memory scrub repaired RAM copy ${bad}. No recommendation used the bad value.`);
  if (App.view === 'systems') render();
}

// ---------- Reducer: everything on screen derives from the event log ----------
function reduce(recs) {
  const st = { crew: {}, order: [], timelines: {}, active: {}, recs: {}, sleeplog: {}, gapack: [], faults: [], boots: 0, version: 0 };
  for (const r of recs) {
    const p = r.payload;
    switch (r.type) {
      case 'crew': if (!st.crew[p.id]) st.order.push(p.id); st.crew[p.id] = p; break;
      case 'timeline': st.timelines[p.version] = p; p.crewIds.forEach(id => { st.active[id] = p.version; }); st.version = Math.max(st.version, p.version); break;
      case 'rec': st.recs[p.item + '@' + p.crew] = { status: p.status, until: p.until }; break;
      case 'sleeplog': st.sleeplog[p.crew + '@' + p.sleep] = p.lostH; break;
      case 'gapack': st.gapack.push(...p.seqs); break;
      case 'fault': st.faults.push({ seq: r.seq, ...p }); break;
      case 'boot': st.boots++; break;
    }
  }
  return st;
}
const stateHash = st => crcHex(JSON.stringify([st.crew, st.timelines, st.active, st.recs, st.sleeplog]));

function seed() {
  Store.append('genesis', { app: 'Lunar Sleep-Shift Scheduling Tool', schema: 1, note: 'Sample mission data' });
  SAMPLE_CREW.forEach(c => Store.append('crew', c));
  Store.append('timeline', { version: 1, spec: null, crewIds: SAMPLE_CREW.map(c => c.id), author: 'Mission planning (sample)', note: 'Nominal GMT day' });
  Store.append('timeline', { version: 2, spec: SAMPLE_SLAM, crewIds: ['cdr', 'plt'], author: 'Flight surgeon (sample)', note: 'Vehicle arrival moved 4 h earlier' });
}

// ---------- Plans ----------
const planCache = new Map();
function computePlans() {
  const st = App.st; const active = JSON.parse(tmrGet() || '{}');
  const t0 = performance.now();
  for (const id of st.order) {
    const crew = st.crew[id], v = active[id] ?? st.active[id], tl = st.timelines[v];
    const key = id + '@' + v;
    if (!planCache.has(key)) planCache.set(key, E.buildPlan(crew, tl ? tl.spec : null));
    const plan = planCache.get(key); App.plans[id] = { ...plan, version: v, timeline: tl };
    App.live[id] = E.applyLive(crew, plan, it => (st.recs[it.id + '@' + id] || {}).status === 'skipped', sl => st.sleeplog[id + '@' + sl.id] || 0);
  }
  return performance.now() - t0;
}

// ---------- Boot routine ----------
function boot(reason) {
  const L = []; const T = performance.now();
  const log = (tag, msg, lvl = 'ok') => L.push({ ms: performance.now() - T, tag, msg, lvl });
  log('BOOT', `Cold start (${reason}).`);
  const src = (document.getElementById('engine-src') || {}).textContent || '';
  log('SELF', `Engine image checksum ${crcHex(src)}. Planner and model constants loaded.`);
  if (Store.remote) { const h = Store.health(); log('STORE', `Data service ${h.version}: ${h.copies.length} log copies, each fsynced before a write is acknowledged.`); }
  else log('STORE', Store.persistent ? 'Browser demo store: 3 log copies in local storage (cannot fsync; demo only).' : 'Storage blocked in this view: running from memory only. Data will not survive a reload.', 'warn');
  if (!Store.isInit()) { seed(); Store.markInit(); log('INIT', 'First start: sample mission written (4 crew, 2 timelines).'); }
  const snap = Store.readSnapshot();
  if (snap.pick) log('SNAP', `Snapshot slot ${snap.ptr}${snap.ptrValid ? '' : ' invalid; fell back to other slot'}: state at record ${snap.pick.seq}.`, snap.ptrValid ? 'ok' : 'warn');
  else log('SNAP', 'No valid snapshot. Replaying the log from record 1.', 'warn');
  const rep = Store.recover();
  rep.copies.forEach(c => log('LOG', `Copy ${c.name}: ${c.ok} valid, ${c.bad} corrupt, ${c.torn} torn tail.`, c.bad || c.torn ? 'warn' : 'ok'));
  if (rep.uncommitted) log('LOG', 'Dropped 1 uncommitted record left by an interrupted write. Nothing earlier was touched.', 'warn');
  if (rep.clientRejected) log('LOG', `${rep.clientRejected} record(s) from the service failed the UI's own checksum and were ignored.`, 'crit');
  if (rep.repaired) log('REPAIR', `Rewrote ${rep.repaired} cop${rep.repaired === 1 ? 'y' : 'ies'} from the majority vote.`, 'warn');
  const st = reduce(Store.records);
  const unrec = rep.unrecoverable.filter(s => !st.gapack.includes(s));
  if (unrec.length) log('LOG', `Record${unrec.length > 1 ? 's' : ''} ${unrec.join(', ')} corrupt in every copy. Data from ${unrec.length > 1 ? 'them' : 'it'} is lost.`, 'crit');
  App.status = !Store.records.length ? 'SAFE' : unrec.length ? 'DEGRADED' : 'NOMINAL';
  App.unrec = unrec;
  if (snap.pick && App.status !== 'SAFE') {
    const upto = Store.records.filter(r => r.seq <= snap.pick.seq);
    const h = stateHash(reduce(upto));
    log('VERIFY', h === snap.pick.hash ? `Replay to record ${snap.pick.seq} reproduces snapshot hash ${h}.` : `Replay hash ${h} differs from snapshot ${snap.pick.hash}; using the log as truth.`, h === snap.pick.hash ? 'ok' : 'warn');
  }
  App.st = st; tmrSet(JSON.stringify(st.active));
  if (App.status !== 'SAFE') {
    const ms = computePlans();
    log('ENGINE', `Rebuilt ${st.order.length} crew states and plans in ${r0(ms)} ms.`);
    const last = Store.lastAlive();
    if (last) { const gap = (Date.now() - last) / 60000; log('GAP', gap < 1 ? 'Offline under 1 min. No tracking gap.' : `Offline ${gap < 120 ? r0(gap) + ' min' : (gap / 60).toFixed(1) + ' h'}. Scheduled timeline assumed for the gap; crew will be asked to confirm sleep.`, gap < 1 ? 'ok' : 'warn'); }
    Store.append('boot', { reason, status: App.status, repaired: rep.repaired, unrec: unrec.length });
    App.st = reduce(Store.records);
    const slot = Store.writeSnapshot(Store.records[Store.records.length - 1].seq, stateHash(App.st));
    log('SNAP', `New snapshot written to slot ${slot}; pointer flipped.`);
    if (!App.st.order.includes(App.crewSel)) App.crewSel = App.st.order[0];
  } else {
    log('SAFE', 'No consistent state could be rebuilt. Safe Mode: generic guidance only. Controller asked to resend profiles.', 'crit');
  }
  log('RESUME', App.status === 'NOMINAL' ? 'Nominal. Tracking resumed without crew input.' : App.status === 'DEGRADED' ? 'Degraded: running on remaining data. Flagged to Controller Mode.' : 'Safe Mode active.', App.status === 'NOMINAL' ? 'ok' : App.status === 'DEGRADED' ? 'warn' : 'crit');
  App.bootLog = L; App.lastBoot = { reason, at: new Date() };
  Store.alive();
}

// ---------- Event logging helpers (every user action is an append) ----------
function act(type, payload, msg) {
  Store.append(type, payload); App.st = reduce(Store.records); tmrSet(JSON.stringify(App.st.active));
  computePlans(); if (msg) toast(msg); render();
}

// ---------- Crew Mode ----------
function crewNow(id, t) {
  const live = App.live[id], items = live.items.filter(x => !x.skipped), sim = live.sim;
  const i = Math.max(0, Math.min(sim.n - 1, Math.round(t / E.DT)));
  const inside = x => x.start <= t && t < x.end;
  const curSleep = items.find(x => (x.type === 'sleep' || x.type === 'nap') && inside(x));
  const nextSleep = items.filter(x => x.type === 'sleep' && x.start > t).sort((a, b) => a.start - b.start)[0];
  const curCrit = items.find(x => x.type === 'critical' && inside(x));
  const curAlert = items.find(x => x.type === 'light' && x.kind === 'alert' && inside(x));
  const curDim = items.find(x => x.type === 'light' && x.kind === 'dim' && inside(x));
  const state = curSleep ? 'sleep' : (curCrit || curAlert) ? 'alert' : (curDim || (nextSleep && nextSleep.start - t <= 2)) ? 'wind' : 'neutral';
  const R = sim.R[i];
  const nextCrit = items.filter(x => x.type === 'critical' && x.end > t).sort((a, b) => a.start - b.start)[0];
  let critR = null;
  if (nextCrit) { const a = Math.round(nextCrit.start / E.DT), b = Math.round(nextCrit.end / E.DT); let mn = 101; for (let k = a; k < b; k++) if (!isNaN(sim.R[k])) mn = Math.min(mn, sim.R[k]); critR = mn > 100 ? null : mn; }
  return { live, items, i, R, state, curSleep, nextSleep, curCrit, curAlert, curDim, nextCrit, critR };
}

function promptText(it, crewPlan) {
  const goal = it.goal ? it.goal.replace(/:.*/, '') : 'the new schedule';
  if (it.type === 'light' && it.kind === 'alert') return it.role === 'counter'
    ? { title: 'Blue-enriched light', detail: `${fmtDur(it.end - it.start)} at full brightness. Lifts alertness for ${goal}.` }
    : { title: 'Blue-enriched light', detail: `${fmtDur(it.end - it.start)}. Moves your clock ${it.dir} toward ${goal}.` };
  if (it.type === 'light' && it.role === 'wind') return { title: 'Wind-down: red light only', detail: `Sleep at ${E.hm(it.end)}. Screens stay in red mode.` };
  if (it.type === 'light') return { title: 'Red light only', detail: `${fmtDur(it.end - it.start)}. Use blue-blocking glasses if task light is needed. Keeps light from undoing the shift.` };
  if (it.type === 'nap') return it.role === 'crit'
    ? { title: `Nap ${fmtDur(it.end - it.start)}`, detail: `Ends ${E.hm(it.end)}, clear of sleep inertia before ${goal}.` }
    : { title: `Nap ${fmtDur(it.end - it.start)}`, detail: `Breaks up a ${r0(it.wake)} h day. Full cycle, so you wake from light sleep.` };
  if (it.type === 'sleep') return { title: 'Sleep window', detail: `Lights off, eye mask on. Wake ${E.hm(it.end)}.` };
  return { title: it.label || it.type, detail: '' };
}

function crewPrompts(id, t) {
  const st = App.st, live = App.live[id];
  const cands = live.items.filter(x => (x.type === 'light' || x.type === 'nap' || x.type === 'sleep') && !x.skipped && x.end > t && x.start <= t + 0.75)
    .filter(x => { const r = st.recs[x.id + '@' + id]; if (!r) return true; if (r.status === 'done' || r.status === 'skipped') return false; if (r.status === 'snoozed') return t >= r.until; return true; })
    .sort((a, b) => a.start - b.start);
  // batch prompts that start within 20 minutes of each other
  const groups = [];
  for (const c of cands) { const g = groups[groups.length - 1]; if (g && c.start - g[0].start <= 1 / 3) g.push(c); else groups.push([c]); }
  return groups.slice(0, 2);
}

function ribbon(id, t, now) {
  const W = 960, a = t - 4, X = u => (u - a) / 24 * W;
  const items = App.live[id].items.filter(x => x.end > a && x.start < a + 24 && !x.skipped);
  let s = '';
  for (const it of items) {
    const x1 = Math.max(0, X(it.start)), x2 = Math.min(W, X(it.end)); if (x2 - x1 < 1) continue;
    if (it.type === 'sleep') s += `<rect x="${x1}" y="30" width="${x2 - x1}" height="30" rx="4" fill="var(--c-fg2)" fill-opacity="0.55"/>`;
    else if (it.type === 'nap') s += `<rect x="${x1}" y="36" width="${x2 - x1}" height="18" rx="3" fill="var(--c-fg2)" fill-opacity="0.85"/>`;
    else if (it.type === 'critical') s += `<rect x="${x1}" y="24" width="${x2 - x1}" height="42" rx="4" fill="none" stroke="var(--c-fg)" stroke-width="2"/>`;
    else if (it.kind === 'alert') s += `<rect x="${x1}" y="72" width="${x2 - x1}" height="12" rx="2" fill="url(#hatch-${id})"/>`;
    else s += `<rect x="${x1}" y="76" width="${x2 - x1}" height="4" rx="2" fill="var(--c-fg2)"/>`;
  }
  let ticks = '';
  const first = Math.ceil(a / 3) * 3;
  for (let u = first; u <= a + 24; u += 3) ticks += `<line x1="${X(u)}" x2="${X(u)}" y1="18" y2="88" stroke="var(--c-line)"/><text x="${X(u)}" y="108" text-anchor="middle" class="rb-tick">${E.hm(u)}</text>`;
  return `<svg class="ribbon" viewBox="0 0 ${W} 116" role="img" aria-label="Next 20 hours: sleep, light windows and critical tasks">
    <defs><pattern id="hatch-${id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--c-fg2)" fill-opacity="0.4"/><line x1="0" y1="0" x2="0" y2="6" stroke="var(--c-fg)" stroke-width="3"/></pattern></defs>
    ${ticks}${s}<line x1="${X(now)}" x2="${X(now)}" y1="10" y2="92" stroke="var(--c-fg)" stroke-width="2"/><text x="${X(now) + 6}" y="14" class="rb-now">NOW</text></svg>`;
}

function crewView() {
  if (App.status === 'SAFE') return safeView();
  const st = App.st, id = App.crewSel, crew = st.crew[id], t = App.t;
  const N = crewNow(id, t);
  const chips = st.order.map(cid => { const n = crewNow(cid, t); return `<button class="who${cid === id ? ' on' : ''}" data-act="crew" data-id="${cid}" aria-pressed="${cid === id}"><span class="who-n">${esc(st.crew[cid].name)}</span><span class="who-r">${esc(st.crew[cid].role)} · ${{ sleep: 'asleep', wind: 'wind-down', alert: 'active', neutral: 'awake' }[n.state]}</span></button>`; }).join('');
  let head, sub;
  if (N.curSleep) { head = N.curSleep.type === 'nap' ? 'Nap in progress' : 'Sleep window'; sub = `Wake ${E.hm(N.curSleep.end)}. Nothing to do.`; }
  else if (N.curCrit) { head = N.curCrit.label; sub = `Critical block until ${E.hm(N.curCrit.end)}. Prompts are held until it ends.`; }
  else if (N.curAlert) { head = 'Blue-enriched light on'; sub = `${fmtDur(N.curAlert.end - t)} left in this window.`; }
  else if (N.curDim) { head = N.curDim.role === 'wind' ? 'Wind-down' : 'Red light only'; sub = N.curDim.role === 'wind' ? `Sleep at ${E.hm(N.curDim.end)}.` : `Until ${E.hm(N.curDim.end)}. Protects the clock shift.`; }
  else { head = 'No action needed'; sub = N.nextSleep ? `Next sleep ${E.hm(N.nextSleep.start)}.` : ''; }

  const prompts = N.curCrit || N.curSleep ? [] : crewPrompts(id, t);
  const pc = prompts.map(g => {
    const first = g[0], live = first.start <= t, txt = g.map(it => promptText(it));
    const status = (st.recs[first.id + '@' + id] || {}).status;
    const when = live ? (status === 'started' ? `In progress · ${fmtDur(first.end - t)} left` : 'Now') : `In ${fmtDur(first.start - t)} · ${E.hm(first.start)}`;
    const ids = g.map(x => x.id).join(',');
    const verb = live && status !== 'started' ? 'Start' : live ? 'Done' : 'Start early';
    return `<article class="prompt${live ? ' live' : ''}">
      <div class="prompt-when">${when}</div>
      ${txt.map(x => `<h3>${esc(x.title)}</h3><p>${esc(x.detail)}</p>`).join('')}
      <div class="prompt-act"><button class="btn-primary" data-act="rec" data-ids="${ids}" data-status="${verb === 'Done' ? 'done' : 'started'}">${verb}</button><button data-act="rec" data-ids="${ids}" data-status="snoozed">Snooze 15 min</button><button data-act="rec" data-ids="${ids}" data-status="skipped">Skip</button></div>
    </article>`;
  }).join('');

  const lastSleep = N.items.filter(x => x.type === 'sleep' && x.end <= t && t - x.end < 4).sort((a, b) => b.end - a.end)[0];
  const logged = lastSleep && (id + '@' + lastSleep.id) in st.sleeplog;
  const sleepCard = lastSleep && !logged && N.state !== 'sleep' ? `<article class="prompt">
      <div class="prompt-when">Sleep ended ${E.hm(lastSleep.end)}</div><h3>How did you sleep?</h3>
      <div class="prompt-act"><button class="btn-primary" data-act="sleep" data-sleep="${lastSleep.id}" data-lost="0">As scheduled</button><button data-act="sleep" data-sleep="${lastSleep.id}" data-lost="1">About 1 h less</button><button data-act="sleep" data-sleep="${lastSleep.id}" data-lost="2">About 2 h less</button></div></article>` : '';

  const rNow = isNaN(N.R) ? null : N.R;
  const facts = `<div class="facts">
    <div><span class="lbl">Readiness now</span><span class="big">${rNow == null ? '—' : r0(rNow)}</span><span class="sm">${rNow == null ? 'asleep' : E.band(rNow)}</span></div>
    <div><span class="lbl">Next sleep</span><span class="big">${N.nextSleep ? E.hm(N.nextSleep.start) : '—'}</span><span class="sm">${N.nextSleep ? 'wake ' + E.hm(N.nextSleep.end) + ' · ' + E.clk(N.nextSleep.start).split(' ')[0] : ''}</span></div>
    <div><span class="lbl">${N.nextCrit ? esc(N.nextCrit.label.replace(/:.*/, '')) : 'Next critical task'}</span><span class="big">${N.critR == null ? '—' : r0(N.critR)}</span><span class="sm">${N.nextCrit ? E.clk(N.nextCrit.start) + ' · predicted ' + E.band(N.critR ?? 0) : 'none scheduled'}</span></div>
  </div>`;
  const stateNote = { alert: 'Display: alert mode. Full-spectrum light is wanted now.', neutral: 'Display: amber mode. No blue pixels.', wind: 'Display: deep red, ≤5 cd/m². Melatonin-safe.', sleep: 'Display: dim red, single glance.' }[N.state];
  return `<section class="crew" data-state="${N.state}">
    <div class="who-row" role="group" aria-label="Crew member">${chips}</div>
    <div class="crew-body">
      <div class="now"><div class="eyebrow">${esc(crew.name)} · ${E.clk(t)} GMT</div><h2>${esc(head)}</h2><p>${esc(sub)}</p></div>
      ${N.state === 'sleep' ? '' : facts}
      ${pc}${sleepCard}
      <div class="rb-wrap">${ribbon(id, t, t)}<div class="rb-key"><span><i class="k-sleep"></i>Sleep / nap</span><span><i class="k-light"></i>Blue-enriched light</span><span><i class="k-dim"></i>Red light only</span><span><i class="k-crit"></i>Critical task</span></div></div>
      <p class="state-note">${stateNote}</p>
    </div></section>`;
}

function safeView() {
  return `<section class="crew" data-state="neutral"><div class="crew-body">
    <div class="now"><div class="eyebrow">Safe Mode</div><h2>Follow the last approved timeline</h2>
    <p>Stored data could not be rebuilt. Until the controller resends profiles: sleep at your scheduled time, use red light for 2 h before sleep, keep the sleep area under 1 lux, and seek bright light in the first 2 h after waking.</p></div>
    <div class="prompt-act"><button class="btn-primary" data-act="reseed">Reload sample mission</button></div></div></section>`;
}

// ---------- Controller Mode ----------
function lanes(planFor, label) {
  const st = App.st, PX = 3, LW = 168, LH = 84, H = 14 * 24, top = 30;
  const W = LW + H * PX + 16, X = u => LW + u * PX;
  let g = '';
  for (let d = 0; d <= 14; d++) g += `<line x1="${X(d * 24)}" x2="${X(d * 24)}" y1="${top - 6}" y2="${top + st.order.length * LH}" stroke="var(--line)"/>${d < 14 ? `<text x="${X(d * 24 + 12)}" y="${top - 12}" text-anchor="middle" class="ln-day">D${d + 1}</text>` : ''}`;
  st.order.forEach((id, li) => {
    const y = top + li * LH, P = planFor(id), live = P.live, crew = st.crew[id];
    g += `<g><text x="12" y="${y + 24}" class="ln-name">${esc(crew.name)}</text><text x="12" y="${y + 40}" class="ln-role">${esc(crew.role)}</text><text x="12" y="${y + 58}" class="ln-tag">${esc(P.tag[0])}</text><text x="12" y="${y + 72}" class="ln-tag">${esc(P.tag[1])}</text>`;
    for (const it of live.items) {
      if (it.start > H || it.end < 0) continue;
      const x1 = X(Math.max(0, it.start)), w = Math.max(1, (Math.min(H, it.end) - Math.max(0, it.start)) * PX);
      const sk = it.skipped ? ' opacity="0.3"' : '';
      if (it.type === 'sleep') g += `<rect x="${x1}" y="${y + 10}" width="${w}" height="18" rx="3" fill="var(--sleep)"${sk}/>`;
      else if (it.type === 'nap') g += `<rect x="${x1}" y="${y + 13}" width="${w}" height="12" rx="2" fill="var(--nap)"${sk}/>`;
      else if (it.type === 'critical') g += `<rect x="${x1}" y="${y + 5}" width="${w}" height="28" rx="3" fill="var(--signal)" fill-opacity="0.18" stroke="var(--signal)" stroke-width="1.5"/>`;
      else if (it.kind === 'alert') g += `<rect x="${x1}" y="${y + 31}" width="${w}" height="5" rx="1.5" fill="var(--light)"${sk}/>`;
      else g += `<rect x="${x1}" y="${y + 31}" width="${w}" height="5" rx="1.5" fill="var(--dimred)"${sk}/>`;
    }
    // readiness trace, coloured by band
    const sim = live.sim, y0 = y + 40, hh = 34; let seg = [], cur = null, out = '';
    const flush = () => { if (seg.length > 1) out += `<polyline points="${seg.join(' ')}" fill="none" stroke="var(--${cur})" stroke-width="1.5"/>`; seg = []; };
    for (let i = 0; i < Math.min(sim.n, H / E.DT); i += 3) {
      const R = sim.R[i]; if (isNaN(R)) { flush(); cur = null; continue; }
      const b = bandOf(R), pt = `${X(i * E.DT).toFixed(1)},${(y0 + hh - R / 100 * hh).toFixed(1)}`;
      if (b !== cur) { if (seg.length) { seg.push(pt); flush(); } cur = b; }
      seg.push(pt);
    }
    flush();
    g += `<line x1="${LW}" x2="${X(H)}" y1="${y0 + hh - 0.7 * hh}" y2="${y0 + hh - 0.7 * hh}" stroke="var(--line)" stroke-dasharray="2 4"/>` + out;
    for (const c of E.cbtMins(sim)) if (c < H) g += `<path d="M${X(c) - 4} ${y + 38}h8l-4 5z" fill="var(--ink-2)"/>`;
    g += `<line x1="${LW}" x2="${X(H)}" y1="${y + LH - 2}" y2="${y + LH - 2}" stroke="var(--line)"/></g>`;
  });
  g += `<line x1="${X(App.t)}" x2="${X(App.t)}" y1="${top - 6}" y2="${top + st.order.length * LH}" stroke="var(--signal)" stroke-width="1.5"/>`;
  return `<div class="lane-scroll"><svg viewBox="0 0 ${W} ${top + st.order.length * LH + 6}" width="${W}" role="img" aria-label="${esc(label)}">${g}</svg></div>`;
}

function ctlView() {
  if (App.status === 'SAFE') return `<section class="panel"><h2>Safe Mode</h2><p class="muted">No crew data. Reload the sample mission from the Crew or Systems tab.</p></section>`;
  const st = App.st, draft = App.drafts.find(d => d.id === App.preview);
  const planFor = id => {
    if (draft && draft.res[id]) return { live: draft.res[id].live, tag: [`Draft ${draft.name}`, draft.res[id].plan.strategy] };
    const P = App.plans[id]; return { live: App.live[id], tag: [`Timeline v${P.version}`, P.strategy] };
  };
  const rows = st.order.map(id => {
    const P = App.plans[id], N = crewNow(id, App.t), c = st.crew[id];
    const cr = P.crit ? P.crit.min : null;
    return `<tr><td><b>${esc(c.name)}</b><br><span class="muted">${esc(c.role)} · τ ${c.tau.toFixed(2)} h</span></td><td>v${P.version}<br><span class="muted">${esc(P.timeline ? P.timeline.note : '')}</span></td><td>${esc(P.strategy)}</td>
      <td>${P.critWin ? esc(P.critWin.label) + '<br><span class="muted">' + E.clk(P.critWin.start) + '</span>' : '<span class="muted">none</span>'}</td>
      <td class="num">${cr == null ? '—' : `<span class="pill ${bandOf(cr)}">${r0(cr)} ${E.band(cr)}</span>`}</td><td class="num">${isNaN(N.R) ? '<span class="muted">asleep</span>' : r0(N.R)}</td></tr>`;
  }).join('');
  const crewChecks = st.order.map(id => `<label class="chk"><input type="checkbox" id="wf-c-${id}" value="${id}" ${['cdr', 'plt', 'ms1', 'ms2'].includes(id) ? 'checked' : ''}> ${esc(st.crew[id].name)}</label>`).join('');
  const draftsHtml = App.drafts.map(d => draftCard(d)).join('');
  const compare = App.drafts.length > 1 ? `<div class="panel"><h3>Compare drafts</h3><div class="tbl"><table><thead><tr><th>Draft</th><th>Change</th><th class="num">Worst crew readiness</th><th class="num">Time below 70</th><th class="num">Sleep lost</th></tr></thead><tbody>${App.drafts.map(d => `<tr><td>${d.name}</td><td>${esc(d.summary)}</td><td class="num">${r0(d.worst)}</td><td class="num">${d.below.toFixed(1)} h</td><td class="num">${d.lost.toFixed(1)} h</td></tr>`).join('')}</tbody></table></div></div>` : '';
  return `<div class="ctl">
    <section class="panel"><div class="ph"><h2>Crew readiness</h2><span class="muted">at ${E.clk(App.t)} GMT · status ${App.status.toLowerCase()}</span></div>
      <div class="tbl"><table><thead><tr><th>Crew</th><th>Timeline</th><th>Strategy</th><th>Next critical block</th><th class="num">Predicted worst</th><th class="num">Now</th></tr></thead><tbody>${rows}</tbody></table></div></section>
    <section class="panel"><div class="ph"><h2>${draft ? `Previewing draft ${draft.name}` : 'Active timelines'}</h2>${draft ? '<button data-act="unpreview">Show active</button>' : ''}</div>
      <div class="legend"><span><i style="background:var(--sleep)"></i>Sleep</span><span><i style="background:var(--nap)"></i>Nap</span><span><i style="background:var(--light)"></i>Blue-enriched light</span><span><i style="background:var(--dimred)"></i>Red light only</span><span><i class="lg-crit"></i>Critical block</span><span><i class="lg-cbt"></i>Predicted CBTmin</span><span><i class="lg-line"></i>Readiness (dashed = 70)</span></div>
      ${lanes(planFor, 'Crew timelines over 14 days')}</section>
    <section class="panel whatif"><h2>What-if: schedule change</h2>
      <p class="muted">Drafts never reach crew devices until you approve them.</p>
      <form id="wf" class="wf">
        <fieldset><legend>Crew</legend><div class="chks">${crewChecks}</div></fieldset>
        <label>Shift (h, negative = earlier)<input id="wf-delta" type="number" step="0.5" min="-12" max="12" value="-4"></label>
        <label>Start shifting on night of<select id="wf-start">${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(d => `<option value="${d}"${d === 2 ? ' selected' : ''}>Day ${d}</option>`).join('')}</select></label>
        <label>Critical task<input id="wf-label" type="text" value="EVA: radiator inspection"></label>
        <label>Day<select id="wf-day">${[2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(d => `<option value="${d}"${d === 6 ? ' selected' : ''}>Day ${d}</option>`).join('')}</select></label>
        <label>Start (GMT)<input id="wf-time" type="time" value="06:30" step="900"></label>
        <label>Duration (h)<input id="wf-dur" type="number" step="0.5" min="0.5" max="10" value="6"></label>
        <button type="submit" class="btn-primary">Simulate draft</button>
      </form></section>
    ${draftsHtml}${compare}
  </div>`;
}

function draftCard(d) {
  const st = App.st;
  const rows = d.crewIds.map(id => { const R = d.res[id], p = R.plan, c = st.crew[id];
    const u = p.unmit && p.unmit.crit ? p.unmit.crit.min : null, q = p.crit ? p.crit.min : null;
    return `<tr><td>${esc(c.name)}</td><td>${esc(p.strategy)}</td><td class="num">${u == null ? '—' : `<span class="pill ${bandOf(u)}">${r0(u)}</span>`}</td><td class="num">${q == null ? '—' : `<span class="pill ${bandOf(q)}">${r0(q)}</span>`}</td><td class="num">${p.sleepLost.toFixed(1)} h</td><td class="num">${p.lightCount}</td><td class="num">${p.napCount}</td></tr>`; }).join('');
  const why = d.crewIds.map(id => `<details><summary>${esc(st.crew[id].name)}: why this plan</summary><ul>${d.res[id].plan.reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul>
    <div class="tbl"><table class="mini"><thead><tr><th>Option</th><th class="num">Worst</th><th class="num">Cost</th></tr></thead><tbody>${d.res[id].plan.options.map(o => `<tr><td>${esc(o.name)}</td><td class="num">${o.crit ? r0(o.crit.min) : '—'}</td><td class="num">${o.cost.toFixed(1)}</td></tr>`).join('')}</tbody></table></div></details>`).join('');
  return `<section class="panel draft${App.preview === d.id ? ' previewing' : ''}"><div class="ph"><h2>Draft ${d.name}</h2><span class="muted">${esc(d.summary)} · computed in ${r0(d.ms)} ms</span></div>
    <div class="tbl"><table><thead><tr><th>Crew</th><th>Chosen plan</th><th class="num">Unmitigated worst</th><th class="num">Planned worst</th><th class="num">Sleep lost</th><th class="num">Light windows</th><th class="num">Naps</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${why}
    <div class="prompt-act"><button data-act="preview" data-id="${d.id}">${App.preview === d.id ? 'Previewing on timeline' : 'Preview on timeline'}</button>
    ${d.confirm ? `<span class="confirm">Push to ${d.crewIds.length} crew device${d.crewIds.length > 1 ? 's' : ''}?</span><button class="btn-primary" data-act="approve" data-id="${d.id}">Confirm push</button><button data-act="cancel" data-id="${d.id}">Cancel</button>`
      : `<button class="btn-primary" data-act="ask" data-id="${d.id}">Approve and push</button>`}<button data-act="discard" data-id="${d.id}">Discard</button></div></section>`;
}

function simulateDraft() {
  const ids = App.st.order.filter(id => $('#wf-c-' + id) && $('#wf-c-' + id).checked);
  if (!ids.length) { toast('Pick at least one crew member.'); return; }
  const [hh, mm] = ($('#wf-time').value || '06:00').split(':').map(Number);
  const spec = { delta: Number($('#wf-delta').value) || 0, startDay: Number($('#wf-start').value), crit: { label: $('#wf-label').value.trim() || 'Critical task', day: Number($('#wf-day').value), start: hh + mm / 60, dur: Math.max(0.5, Number($('#wf-dur').value) || 1) } };
  if (spec.startDay >= spec.crit.day) { toast('The shift has to start before the day of the critical task.'); return; }
  const t0 = performance.now(), res = {};
  let worst = 101, below = 0, lost = 0;
  for (const id of ids) {
    const crew = App.st.crew[id], plan = E.buildPlan(crew, spec), live = { items: plan.items, sim: plan.sim };
    res[id] = { plan, live };
    if (plan.crit) worst = Math.min(worst, plan.crit.min);
    for (let i = 0; i < plan.sim.n; i++) if (plan.sim.crit[i] && plan.sim.R[i] < 70) below += E.DT;
    lost += plan.sleepLost;
  }
  const name = 'ABCDEFGHIJ'[(App.draftN = (App.draftN || 0) + 1) - 1 % 10] || String(App.draftN);
  const d = { id: 'd' + Date.now(), name, spec, crewIds: ids, res, ms: performance.now() - t0, worst, below, lost,
    summary: `${spec.delta > 0 ? '+' : ''}${spec.delta} h from day ${spec.startDay} · ${spec.crit.label} ${E.clk((spec.crit.day - 1) * 24 + spec.crit.start)}` };
  App.drafts.push(d); if (App.drafts.length > 3) App.drafts.shift();
  App.preview = d.id; render();
}

// ---------- Systems ----------
function sysView() {
  const recs = Store.records.slice(-30).reverse();
  const counts = Store.lineCount();
  const summarize = r => { const p = r.payload;
    switch (r.type) { case 'crew': return `${p.name}, ${p.role}`; case 'timeline': return `v${p.version} for ${p.crewIds.join(', ')}: ${p.note || ''}`;
      case 'rec': return `${p.crew}: ${p.item} ${p.status}`; case 'sleeplog': return `${p.crew}: ${p.sleep} lost ${p.lostH} h`;
      case 'boot': return `${p.reason}: ${p.status}${p.repaired ? `, ${p.repaired} copies repaired` : ''}`; case 'light': return `${p.crew}: lights ${p.mode} (${p.lux} lux measured)`; case 'fault': return p.msg; case 'gapack': return `acknowledged loss of ${p.seqs.join(', ')}`; case 'power': return `${p.event} (battery ${p.pct}%)`; case 'lightlink': return `lights ${p.linked ? 'linked to plan' : 'manual'} (${p.source})`; case 'switch': return `${p.name} switch → ${String(p.pos).toUpperCase()}`; default: return p.note || p.app || ''; } };
  return `<div class="sys">
    <section class="panel"><div class="ph"><h2>Store integrity</h2><span class="pill ${App.status === 'NOMINAL' ? 'good' : App.status === 'DEGRADED' ? 'warn' : 'crit'}">${App.status}</span></div>
      <dl class="kv"><div><dt>Committed records</dt><dd>${Store.records.length}</dd></div><div><dt>Lines per copy A / B / C</dt><dd>${counts.join(' / ')}</dd></div><div><dt>Last boot</dt><dd>${App.lastBoot ? esc(App.lastBoot.reason) : '—'}</dd></div><div><dt>Backend</dt><dd>${Store.remote ? 'Data service (fsync)' : Store.persistent ? 'Browser demo' : 'Memory only'}</dd></div></dl>
      ${App.status === 'DEGRADED' ? `<div class="prompt-act"><button class="btn-primary" data-act="gapack">Acknowledge data loss</button></div>` : ''}
      ${App.status === 'SAFE' ? `<div class="prompt-act"><button class="btn-primary" data-act="reseed">Reload sample mission</button></div>` : ''}</section>
    ${hwPanel()}
    ${lightsPanel()}
    <section class="panel"><h2>Fault injection</h2><p class="muted">Each test damages storage or memory the way a radiation hit or power loss would, then cold-starts the app.${faultsLocked() ? ' <b>Locked: turn on the recessed TEST switch to use these.</b>' : ''}</p>
      <div class="faults"${faultsLocked() ? ' inert' : ''}>
        <button data-act="fault" data-f="F01"><b>F-01 Power cut mid-write</b><span>Copy A finishes the record, B is torn halfway, C never starts.</span></button>
        <button data-act="fault" data-f="F02"><b>F-02 Corrupt active snapshot</b><span>Damages the snapshot slot the pointer names.</span></button>
        <button data-act="fault" data-f="F03"><b>F-03 Bit flip, one copy</b><span>Flips a byte in a random record of copy B.</span></button>
        <button data-act="fault" data-f="F03b"><b>F-03b Bit flips, two copies</b><span>Same record damaged in A and C; B still good.</span></button>
        <button data-act="fault" data-f="F04"><b>F-04 Record lost everywhere</b><span>Same record corrupted in all three copies.</span></button>
        <button data-act="fault" data-f="F05"><b>F-05 RAM upset</b><span>Corrupts one of three in-memory copies; the scrubber should fix it.</span></button>
        <button data-act="fault" data-f="F11"><b>F-11 Wipe all storage</b><span>Erases every log copy and snapshot.</span></button>
        <button data-act="fault" data-f="BOOT"><b>Cold restart</b><span>Reboot with no damage.</span></button>
      </div></section>
    <section class="panel"><h2>Boot log</h2><div class="bootlog">${App.bootLog.map(l => `<div class="bl ${l.lvl}"><span class="bl-ms">${l.ms.toFixed(1).padStart(6, ' ')} ms</span><span class="bl-tag">${l.tag}</span><span>${esc(l.msg)}</span></div>`).join('')}</div></section>
    <section class="panel"><h2>Event log</h2><p class="muted">Newest first. Each record carries its own CRC and the CRC of the record before it.</p>
      <div class="tbl"><table class="mono"><thead><tr><th class="num">Seq</th><th>Type</th><th>Record</th><th>CRC</th><th>Prev</th></tr></thead><tbody>${recs.map(r => `<tr><td class="num">${r.seq}</td><td>${r.type}</td><td>${esc(summarize(r))}</td><td>${r.crc}</td><td>${r.prev}</td></tr>`).join('')}</tbody></table></div></section>
  </div>`;
}

function injectFault(f) {
  let msg = '';
  const n = Store.records.length;
  if (f === 'F01') { Store.tornAppend('rec', { crew: App.crewSel, item: 'test', status: 'done' }); msg = 'Power cut during a write'; }
  if (f === 'F02') { const p = Store.corruptSnap(); msg = `Snapshot slot ${p} corrupted`; }
  if (f === 'F03') { const i = Store.corrupt(1); msg = `Bit flip in copy B, line ${i + 1}`; }
  if (f === 'F03b') { const i = Math.max(1, Math.floor(n / 2)); Store.corrupt(0, i); Store.corrupt(2, i); msg = `Bit flips in copies A and C, line ${i + 1}`; }
  if (f === 'F04') { const i = Math.max(1, Math.floor(n / 3)); [0, 1, 2].forEach(c => Store.corrupt(c, i)); msg = `Line ${i + 1} corrupted in all copies`; }
  if (f === 'F05') { TMR.b = '{"cdr":99'; toast('RAM copy B corrupted. Scrubber runs every 3 s.'); return; }
  if (f === 'F11') { Store.wipe(); msg = 'All storage wiped'; }
  if (f === 'BOOT') msg = 'Operator restart';
  planCache.clear();
  boot(msg);
  if (f !== 'BOOT' && App.status !== 'SAFE') Store.append('fault', { kind: f, msg: `${f}: ${msg}. Recovery: ${App.status}.` }), App.st = reduce(Store.records);
  toast(`${msg}. Rebooted: ${App.status === 'NOMINAL' ? 'nominal' : App.status === 'DEGRADED' ? 'degraded' : 'Safe Mode'}.`);
  render();
}

// ---------- Habitat lights (REQ-LGT-001, REQ-SAF-002: off unless an operator links them) ----------
function desiredLightMode(id, t) {
  const N = crewNow(id, t);
  if (N.curSleep) return 'off';
  if (N.curAlert || (N.curCrit && N.curCrit.alertLight)) return 'phase-shift';
  if (N.curCrit) return 'general';
  if (N.curDim) return N.curDim.role === 'wind' ? 'pre-sleep' : 'red';
  if (N.state === 'wind') return 'pre-sleep';
  return 'general';
}
function syncLights() {
  if (!Store.remote || !App.lightsFollow || App.status === 'SAFE') return;
  const mode = desiredLightMode(App.crewSel, App.t);
  if (mode === App.lightMode) return;
  try {
    const r = Store.lights.set(mode); App.lightMode = mode; App.lightState = r;
    Store.append('light', { crew: App.crewSel, mode, at: App.t, lux: r.reading ? r.reading.lux : null });
    App.st = reduce(Store.records);
  } catch (e) { toast('Lights did not respond: ' + e.message); }
}
function lightsPanel() {
  if (!Store.remote) return `<section class="panel"><h2>Habitat lights</h2><p class="muted">Not connected. Run the data service on the Pi to drive the LED panel and read the light sensor.</p></section>`;
  let s = App.lightState; if (!s) { try { s = App.lightState = Store.lights.get(); } catch (e) { s = null; } }
  const modes = ['phase-shift', 'general', 'pre-sleep', 'red', 'off'];
  return `<section class="panel"><div class="ph"><h2>Habitat lights</h2><span class="muted">${s ? `${esc(s.driver)} driver · sensor ${esc(s.reading.sensor)} · ${s.reading.lux} lux` : 'no response'}</span></div>
    <p class="muted">Linking makes the panel follow ${esc(App.st.crew[App.crewSel] ? App.st.crew[App.crewSel].name : 'the selected crew member')}'s plan. Every change is written to the light log.</p>
    <div class="prompt-act"><button class="${App.lightsFollow ? 'btn-primary' : ''}" data-act="lightsfollow">${App.lightsFollow ? 'Linked to crew plan' : 'Link to crew plan'}</button>
    ${modes.map(m => `<button data-act="lightmode" data-mode="${m}"${s && s.mode === m ? ' aria-pressed="true" class="on"' : ''}>${m}${s && s.mode === m ? ' ✓' : ''}</button>`).join('')}</div></section>`;
}


// ---------- Tablet hardware (REQ-HW-011 to REQ-HW-016) ----------
// The service owns the GPIO. The UI polls the switch state, acts once per new key press,
// and tells the service what the backlight and the ACK light should show.
const BACKLIGHT = { alert: 1.0, neutral: 0.6, wind: 0.2, sleep: 0.04 };
const HW = { c: null, out: { backlight: null, indicator: null } };
function livePrompt() {
  if (App.status === 'SAFE') return null;
  const id = App.crewSel, t = App.t, N = crewNow(id, t);
  if (N.curCrit || N.curSleep) return null;
  return crewPrompts(id, t).find(g => g[0].start <= t) || null;
}
function hardwareAck() {
  const g = livePrompt(); if (!g) { toast('ACK: no prompt to confirm right now.'); return; }
  const started = (App.st.recs[g[0].id + '@' + App.crewSel] || {}).status === 'started';
  const status = started ? 'done' : 'started';
  g.forEach(it => Store.append('rec', { crew: App.crewSel, item: it.id, status, at: App.t, source: 'ACK' }));
  act('noop', {}, started ? 'ACK: logged as done.' : 'ACK: started. Logged.');
}
function hardwareSnooze() {
  const g = livePrompt(); if (!g) { toast('SNOOZE: no prompt to snooze right now.'); return; }
  g.forEach(it => Store.append('rec', { crew: App.crewSel, item: it.id, status: 'snoozed', at: App.t, until: App.t + 0.25, source: 'SNOOZE' }));
  act('noop', {}, 'SNOOZE: snoozed for 15 minutes.');
}
const faultsLocked = () => Store.remote && !(HW.c && HW.c.faults_allowed);
function pollHw() {
  if (!Store.remote) return;
  let c; try { c = Store.controls(); } catch (e) { return; }
  const prev = HW.c; HW.c = c;
  let changed = !prev;
  if (prev) {
    for (let i = prev.presses.ACK; i < c.presses.ACK; i++) hardwareAck();
    for (let i = prev.presses.SNOOZE; i < c.presses.SNOOZE; i++) hardwareSnooze();
    if (c.lights_link !== prev.lights_link) toast(c.lights_link ? 'LIGHTS switch: linked to the crew plan.' : 'LIGHTS switch: manual. Lights stay as they are.');
    if (c.mode !== prev.mode && (App.view === 'crew' || App.view === 'controller')) App.view = c.mode === 'ctrl' ? 'controller' : 'crew';
    changed = ['mode', 'test_mode', 'ext_power', 'shutting_down', 'faults_allowed'].some(k => c[k] !== prev[k]);
  } else if (c.mode === 'ctrl') App.view = 'controller';
  if (App.lightsFollow !== c.lights_link) { App.lightsFollow = c.lights_link; App.lightMode = null; changed = true; }   // the switch always wins
  renderBattery();
  $('#shutdown').hidden = !c.shutting_down;
  if (changed) render();
}
function renderBattery() {
  const el = $('#batt'), c = HW.c; if (!c) { el.hidden = true; return; }
  const pct = Math.round(c.battery.pct);
  el.hidden = false;
  el.textContent = `BATT ${pct}%${c.ext_power ? ' CHG' : ''}${c.test_mode ? ' · TEST' : ''}`;
  el.className = 'status batt' + (pct <= 15 && !c.ext_power ? ' low' : '');
}
function syncOutputs() {
  if (!Store.remote || !HW.c) return;
  const state = App.status === 'SAFE' ? 'neutral' : crewNow(App.crewSel, App.t).state;
  const level = App.view === 'crew' ? BACKLIGHT[state] : BACKLIGHT.neutral;
  const indicator = livePrompt() && state !== 'sleep' ? (state === 'wind' ? 'night' : 'prompt') : 'off';
  try {
    if (level !== HW.out.backlight) { Store.backlight(level); HW.out.backlight = level; }
    if (indicator !== HW.out.indicator) { Store.indicator(indicator); HW.out.indicator = indicator; }
  } catch (e) { /* service restarting; retried on the next render */ }
}
function hwPanel() {
  if (!Store.remote) return `<section class="panel"><h2>Tablet hardware</h2><p class="muted">Browser demo: no keys, switches or battery. Run the data service to use them.</p></section>`;
  const c = HW.c; if (!c) return '';
  const sim = c.driver === 'simulated';
  const row = (k, v) => `<div><dt>${k}</dt><dd>${v}</dd></div>`;
  return `<section class="panel"><div class="ph"><h2>Tablet hardware</h2><span class="muted">${esc(c.driver)} controls · ${esc(c.battery.driver)} battery</span></div>
    <dl class="kv">${row('ACK / SNOOZE presses', `${c.presses.ACK} / ${c.presses.SNOOZE}`)}${row('LIGHTS switch', c.lights_link ? 'LINK' : 'MAN')}${row('MODE switch', c.mode.toUpperCase())}${row('TEST switch', c.test_mode ? 'ON' : 'off')}
      ${row('Battery', `${c.battery.pct}% · ${c.battery.volts} V${c.ext_power ? ' · charging' : ''}`)}${row('Backlight', Math.round(c.backlight * 100) + '%')}${row('ACK light', esc(c.indicator))}</dl>
    ${sim ? `<p class="muted">Simulated hardware. These buttons stand in for the physical keys and switches.</p>
    <div class="prompt-act"><button data-act="sim" data-press="ACK">Press ACK</button><button data-act="sim" data-press="SNOOZE">Press SNOOZE</button>
      <button data-act="sim" data-k="lights_link" data-v="${!c.lights_link}">LIGHTS → ${c.lights_link ? 'MAN' : 'LINK'}</button><button data-act="sim" data-k="mode" data-v="${c.mode === 'crew' ? 'ctrl' : 'crew'}">MODE → ${c.mode === 'crew' ? 'CTRL' : 'CREW'}</button>
      <button data-act="sim" data-k="test_mode" data-v="${!c.test_mode}">TEST → ${c.test_mode ? 'off' : 'ON'}</button><button data-act="sim" data-k="ext_power" data-v="${!c.ext_power}">${c.ext_power ? 'Unplug charger' : 'Plug in charger'}</button>
      <button data-act="sim" data-k="battery_pct" data-v="80">Battery 80%</button><button data-act="sim" data-k="battery_pct" data-v="4">Battery 4%</button></div>` : ''}</section>`;
}

// ---------- Validation ----------
function valView() {
  if (!App.val) { const t0 = performance.now(); const prc = E.prc(24.2); App.val = { prc, ms: performance.now() - t0 }; }
  const { prc } = App.val, pts = prc.pts;
  const W = 720, H = 300, L = 56, Rr = 20, T = 20, B = 44, xs = u => L + (u + 12) / 24 * (W - L - Rr), ymax = 0.8, ys = v => T + (ymax - v) / (2 * ymax) * (H - T - B);
  let grid = '';
  for (let v = -0.8; v <= 0.81; v += 0.4) grid += `<line x1="${L}" x2="${W - Rr}" y1="${ys(v)}" y2="${ys(v)}" stroke="var(--line)"${Math.abs(v) < 1e-6 ? ' stroke-width="1.5" stroke="var(--ink-3)"' : ''}/><text x="${L - 8}" y="${ys(v) + 4}" text-anchor="end" class="ax">${v > 0 ? '+' : ''}${v.toFixed(1)}</text>`;
  for (let u = -12; u <= 12; u += 4) grid += `<text x="${xs(u)}" y="${H - B + 18}" text-anchor="middle" class="ax">${u > 0 ? '+' : ''}${u}</text>`;
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${xs(p.rel).toFixed(1)} ${ys(p.shift).toFixed(1)}`).join('');
  const dots = pts.map(p => `<circle cx="${xs(p.rel).toFixed(1)}" cy="${ys(p.shift).toFixed(1)}" r="3" fill="var(--signal)"/>`).join('');
  // crossover from delay to advance nearest CBTmin
  let cross = null; for (let i = 1; i < pts.length; i++) if (pts[i - 1].shift < 0 && pts[i].shift >= 0 && Math.abs(pts[i].rel) < 6) { const a = pts[i - 1], b = pts[i]; cross = a.rel + (0 - a.shift) / (b.shift - a.shift) * (b.rel - a.rel); }
  const maxAdv = Math.max(...pts.map(p => p.shift)), maxDel = Math.min(...pts.map(p => p.shift));
  const leads = App.status === 'SAFE' ? [] : App.st.order.map(id => ({ c: App.st.crew[id], lead: E.baseLead(App.st.crew[id]) }));
  const planMs = App.status === 'SAFE' ? 0 : Math.max(...App.st.order.map(id => App.plans[id].ms));
  const minSleep = App.status === 'SAFE' ? null : Math.min(...App.st.order.flatMap(id => { const it = App.plans[id].items.filter(x => x.type === 'sleep' && x.start > 0 && x.start < 13 * 24); return it.map(x => x.end - x.start); }));
  const mc = App.mc;
  const mcHtml = mc ? `<div class="mc">
      <div class="mc-row"><span>Unmitigated slam</span><div class="mcbar"><i class="crit" style="width:${mc.unGreen}%"></i></div><b>${r0(mc.unGreen)}% Green</b><span class="muted">mean worst ${r0(mc.unMean)}</span></div>
      <div class="mc-row"><span>With the tool</span><div class="mcbar"><i class="good" style="width:${mc.plGreen}%"></i></div><b>${r0(mc.plGreen)}% Green</b><span class="muted">mean worst ${r0(mc.plMean)}</span></div>
      <p class="muted">${mc.n} virtual crew, τ ${mc.tauMin.toFixed(2)}–${mc.tauMax.toFixed(2)} h, scenario: −4 h shift from day 2, docking day 6 06:00–09:00. ${r0(mc.ms)} ms.</p></div>` :
    `<p class="muted">${App.mcRunning ? `Running… ${App.mcDone || 0} of 80 virtual crew` : 'Samples 80 virtual crew with different body clocks and plans the same slam for each.'}</p>`;
  return `<div class="val">
    <section class="panel"><div class="ph"><h2>Phase response to a 3 h light pulse</h2><span class="muted">1500 lux, τ 24.2 h, model output</span></div>
      <p class="muted">Light before CBTmin delays the clock; light after it advances. This curve must match the published human PRC before the planner can be trusted.</p>
      <div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Phase shift versus pulse timing relative to CBTmin">${grid}
        <line x1="${xs(0)}" x2="${xs(0)}" y1="${T}" y2="${H - B}" stroke="var(--ink-3)" stroke-dasharray="3 3"/><text x="${xs(0) + 6}" y="${T + 12}" class="ax">CBTmin</text>
        <text x="${L + 6}" y="${T + 12}" class="ax">Advance (earlier)</text><text x="${L + 6}" y="${H - B - 8}" class="ax">Delay (later)</text>
        <path d="${path}" fill="none" stroke="var(--signal)" stroke-width="2"/>${dots}
        <text x="${(L + W - Rr) / 2}" y="${H - 6}" text-anchor="middle" class="ax">Pulse midpoint, hours from CBTmin</text>
        <text x="14" y="${(T + H - B) / 2}" text-anchor="middle" class="ax" transform="rotate(-90 14 ${(T + H - B) / 2})">Phase shift (h)</text></svg></div></section>
    <section class="panel"><div class="ph"><h2>Monte Carlo: slam-shift outcomes</h2><button class="btn-primary" data-act="mc"${App.mcRunning ? ' disabled' : ''}>${mc ? 'Run again' : 'Run 80 virtual crew'}</button></div>${mcHtml}</section>
    <section class="panel"><h2>Acceptance checks</h2><div class="tbl"><table><thead><tr><th>Check</th><th>Target</th><th>Measured</th><th></th></tr></thead><tbody>
      <tr><td>Delay → advance crossover</td><td>Within ±1 h of CBTmin</td><td class="num">${cross == null ? '—' : (cross > 0 ? '+' : '') + cross.toFixed(1) + ' h'}</td><td>${pill(cross != null && Math.abs(cross) <= 1)}</td></tr>
      <tr><td>PRC shape</td><td>Delays and advances both present</td><td class="num">${maxDel.toFixed(2)} / +${maxAdv.toFixed(2)} h</td><td>${pill(maxDel < -0.2 && maxAdv > 0.2)}</td></tr>
      ${leads.map(l => `<tr><td>CBTmin before wake, ${esc(l.c.name)}</td><td>1.5–3.5 h</td><td class="num">${l.lead.toFixed(1)} h</td><td>${pill(l.lead >= 1.5 && l.lead <= 3.5)}</td></tr>`).join('')}
      <tr><td>Plan generation, slowest crew</td><td>≤ 2000 ms</td><td class="num">${r0(planMs)} ms</td><td>${pill(planMs <= 2000)}</td></tr>
      <tr><td>Shortest main sleep in active plans</td><td>≥ 6.5 h</td><td class="num">${minSleep == null ? '—' : minSleep.toFixed(1) + ' h'}</td><td>${pill(minSleep != null && minSleep >= 6.5)}</td></tr>
      ${mc ? `<tr><td>Crew Green during critical block</td><td>≥ 80%</td><td class="num">${r0(mc.plGreen)}%</td><td>${pill(mc.plGreen >= 80)}</td></tr>` : ''}
    </tbody></table></div><p class="muted">Model constants follow Forger, Jewett &amp; Kronauer (1999). Readiness weights are placeholders until fit to PVT data.</p></section>
  </div>`;
}
const pill = ok => `<span class="pill ${ok ? 'good' : 'warn'}">${ok ? 'Pass' : 'Review'}</span>`;

function runMC() {
  if (App.mcRunning) return;
  App.mcRunning = true; App.mcDone = 0; App.mc = null; render();
  let seed = 20261006; const rnd = () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const gauss = () => Math.sqrt(-2 * Math.log(1 - rnd())) * Math.cos(2 * Math.PI * rnd());
  const N = 80, out = [], t0 = performance.now();
  const crews = Array.from({ length: N }, (_, i) => ({ tau: Math.round(Math.max(23.7, Math.min(24.7, 24.2 + 0.2 * gauss())) * 100) / 100, need: i % 2 ? 8 : 7.5 }));
  const chunk = () => {
    for (let k = 0; k < 4 && out.length < N; k++) { const c = crews[out.length]; const p = E.buildPlan(c, SAMPLE_SLAM); out.push({ pl: p.crit.min, un: p.unmit.crit.min }); }
    App.mcDone = out.length;
    if (out.length < N) { if (App.view === 'validation') render(); setTimeout(chunk, 0); return; }
    App.mc = { n: N, plGreen: 100 * out.filter(o => o.pl >= 70).length / N, unGreen: 100 * out.filter(o => o.un >= 70).length / N,
      plMean: out.reduce((s, o) => s + o.pl, 0) / N, unMean: out.reduce((s, o) => s + o.un, 0) / N,
      tauMin: Math.min(...crews.map(c => c.tau)), tauMax: Math.max(...crews.map(c => c.tau)), ms: performance.now() - t0 };
    App.mcRunning = false; render();
  };
  setTimeout(chunk, 30);
}

// ---------- Shell ----------
let toastTimer;
function toast(msg) { const el = $('#toast'); el.textContent = msg; el.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 4200); }

function render() {
  syncLights();
  syncOutputs();
  $('#clock').textContent = `${E.clk(App.t)} GMT`;
  $('#scrub').value = App.t;
  const chip = $('#status'); chip.textContent = App.status; chip.className = 'status ' + App.status.toLowerCase();
  document.querySelectorAll('.tab').forEach(b => { const on = b.dataset.view === App.view; b.classList.toggle('on', on); b.setAttribute('aria-selected', on); });
  const main = $('#main');
  const keep = App.view === 'controller' ? captureForm() : null;
  main.innerHTML = App.view === 'crew' ? crewView() : App.view === 'controller' ? ctlView() : App.view === 'systems' ? sysView() : valView();
  if (keep) restoreForm(keep);
  document.body.dataset.mode = App.view;
}
function captureForm() { const f = $('#wf'); if (!f) return null; const o = {}; f.querySelectorAll('input,select').forEach(el => { o[el.id] = el.type === 'checkbox' ? el.checked : el.value; }); return o; }
function restoreForm(o) { for (const k in o) { const el = document.getElementById(k); if (!el) continue; if (el.type === 'checkbox') el.checked = o[k]; else el.value = o[k]; } }

document.addEventListener('click', e => {
  const b = e.target.closest('[data-act],[data-view],[data-step]'); if (!b) return;
  if (b.dataset.view) { App.view = b.dataset.view; render(); return; }
  if (b.dataset.step) { App.t = Math.max(0, Math.min(14 * 24 - 0.25, App.t + Number(b.dataset.step))); render(); return; }
  const a = b.dataset.act, id = App.crewSel;
  if (a === 'crew') { App.crewSel = b.dataset.id; render(); }
  if (a === 'rec') {
    const st = b.dataset.status, ids = b.dataset.ids.split(',');
    ids.forEach(item => Store.append('rec', { crew: id, item, status: st, at: App.t, until: st === 'snoozed' ? App.t + 0.25 : undefined }));
    act('noop', {}, st === 'skipped' ? 'Skipped. Predictions re-run without that window.' : st === 'snoozed' ? 'Snoozed for 15 minutes.' : st === 'done' ? 'Logged as done.' : 'Started. Logged.');
  }
  if (a === 'sleep') act('sleeplog', { crew: id, sleep: b.dataset.sleep, lostH: Number(b.dataset.lost) }, Number(b.dataset.lost) ? 'Logged. Readiness updated for the shorter night.' : 'Logged.');
  if (a === 'preview') { App.preview = b.dataset.id; render(); }
  if (a === 'unpreview') { App.preview = null; render(); }
  if (a === 'ask' || a === 'cancel') { const d = App.drafts.find(x => x.id === b.dataset.id); if (d) d.confirm = a === 'ask'; render(); }
  if (a === 'discard') { App.drafts = App.drafts.filter(x => x.id !== b.dataset.id); if (App.preview === b.dataset.id) App.preview = null; render(); }
  if (a === 'approve') {
    const d = App.drafts.find(x => x.id === b.dataset.id); if (!d) return;
    const v = App.st.version + 1;
    d.crewIds.forEach(cid => planCache.set(cid + '@' + v, d.res[cid].plan));
    App.drafts = App.drafts.filter(x => x !== d); App.preview = null;
    act('timeline', { version: v, spec: d.spec, crewIds: d.crewIds, author: 'Flight surgeon console', note: d.summary }, `Timeline v${v} approved and pushed to ${d.crewIds.length} crew device${d.crewIds.length > 1 ? 's' : ''}.`);
  }
  if (a === 'fault') injectFault(b.dataset.f);
  if (a === 'gapack') act('gapack', { seqs: App.unrec }, 'Data loss acknowledged. Next boot will report nominal.');
  if (a === 'reseed') { Store.wipe(); seed(); planCache.clear(); boot('Sample mission reloaded'); render(); }
  if (a === 'mc') runMC();
  if (a === 'sim') { try { const body = b.dataset.press ? { press: b.dataset.press } : { [b.dataset.k]: b.dataset.k === 'mode' ? b.dataset.v : b.dataset.k === 'battery_pct' ? Number(b.dataset.v) : b.dataset.v === 'true' }; Store.sim(body); } catch (e) { toast(e.message); } pollHw(); render(); return; }
  if (a === 'lightsfollow' && Store.remote) { if (HW.c && HW.c.driver === 'simulated') { Store.sim({ lights_link: !App.lightsFollow }); pollHw(); render(); } else toast('Use the LIGHTS switch on the tablet.'); return; }
  if (a === 'lightmode' && Store.remote && App.lightsFollow) { toast('LIGHTS switch is on LINK. Set it to MAN to choose a mode by hand.'); return; }
  if (a === 'lightsfollow') { App.lightsFollow = !App.lightsFollow; App.lightMode = null; toast(App.lightsFollow ? 'Lights now follow the crew plan.' : 'Lights unlinked. They stay in their current mode.'); render(); }
  if (a === 'lightmode') { App.lightsFollow = false; try { App.lightState = Store.lights.set(b.dataset.mode); App.lightMode = b.dataset.mode; Store.append('light', { crew: 'operator', mode: b.dataset.mode, at: App.t, lux: App.lightState.reading.lux }); App.st = reduce(Store.records); } catch (e) { toast('Lights did not respond: ' + e.message); } render(); }
});
document.addEventListener('submit', e => { if (e.target.id === 'wf') { e.preventDefault(); simulateDraft(); } });
document.addEventListener('input', e => { if (e.target.id === 'scrub') { App.t = Number(e.target.value); render(); } });

// ignore 'noop' records in the log view; they only exist to trigger a rebuild
const _append = Store.append;
Store.append = (type, payload) => type === 'noop' ? null : _append(type, payload);

boot('Power on');
pollHw();
render();
setInterval(pollHw, 400);
setInterval(tmrScrub, 3000);
setInterval(() => Store.alive(), 15000);
/*APP-END*/
