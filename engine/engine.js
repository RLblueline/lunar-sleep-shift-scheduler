/*ENGINE-START*/
const ENGINE = (() => {
  // Forger, Jewett & Kronauer (1999) "simpler" model constants
  const P = { mu: 0.23, q: 1 / 3, k: 0.55, a0: 0.05, p: 0.5, I0: 9500, beta: 0.0075, G: 33.75 };
  const DT = 0.1;              // hours per step (6 min)
  const HORIZON = 15 * 24;     // simulated hours (14 shown + margin)
  const CBT_OFF = 0.97;        // CBTmin = time of x minimum + offset (h)
  const LUX = { awake: 150, task: 300, alert: 1500, dim: 8 };
  const BASE_SLEEP = 21.5;     // nominal sleep start, GMT clock hours
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function deriv(x, xc, n, I, tau) {
    const a = I > 0 ? P.a0 * Math.pow(I / P.I0, P.p) : 0;
    const B = P.G * a * (1 - n) * (1 - 0.4 * x) * (1 - 0.4 * xc);
    const dx = Math.PI / 12 * (xc + P.mu * (x / 3 + 4 * x * x * x / 3 - 256 * Math.pow(x, 7) / 105) + B);
    const dxc = Math.PI / 12 * (P.q * B * xc - x * (Math.pow(24 / (0.99669 * tau), 2) + P.k * B));
    const dn = 60 * (a * (1 - n) - P.beta * n);
    return [dx, dxc, dn];
  }
  function step(s, I, tau) {
    const h = DT;
    const k1 = deriv(s[0], s[1], s[2], I, tau);
    const k2 = deriv(s[0] + h / 2 * k1[0], s[1] + h / 2 * k1[1], s[2] + h / 2 * k1[2], I, tau);
    const k3 = deriv(s[0] + h / 2 * k2[0], s[1] + h / 2 * k2[1], s[2] + h / 2 * k2[2], I, tau);
    const k4 = deriv(s[0] + h * k3[0], s[1] + h * k3[1], s[2] + h * k3[2], I, tau);
    return [0, 1, 2].map(j => s[j] + h / 6 * (k1[j] + 2 * k2[j] + 2 * k3[j] + k4[j]));
  }

  // Paint the schedule onto a time grid. Priority: sleep > critical task light > alert > dim > general.
  function raster(items, t0, n) {
    const lux = new Float32Array(n).fill(LUX.awake), asleep = new Uint8Array(n), crit = new Uint8Array(n);
    const idx = t => Math.round((t - t0) / DT);
    const paint = (it, fn) => { const a = Math.max(0, idx(it.start)), b = Math.min(n, idx(it.end)); for (let i = a; i < b; i++) fn(i); };
    const act = items.filter(i => !i.skipped);
    for (const it of act) if (it.type === 'light' && it.kind === 'dim') paint(it, i => { lux[i] = LUX.dim; });
    for (const it of act) if (it.type === 'light' && it.kind === 'alert') paint(it, i => { lux[i] = LUX.alert; });
    for (const it of act) if (it.type === 'critical') paint(it, i => { crit[i] = 1; lux[i] = it.alertLight ? LUX.alert : Math.max(lux[i], LUX.task); });
    for (const it of act) if (it.type === 'sleep' || it.type === 'nap') paint(it, i => { asleep[i] = 1; lux[i] = 0; });
    for (const it of act) if (it.type === 'pulse') paint(it, i => { lux[i] = it.lux; });
    return { lux, asleep, crit };
  }

  // Integrate Process C (oscillator), Process S, chronic debt, sleep inertia and readiness.
  function simulate(crew, items, init, t0, t1) {
    const n = Math.round((t1 - t0) / DT);
    const r = raster(items, t0, n);
    const x = new Float32Array(n), S = new Float32Array(n), R = new Float32Array(n), debt = new Float32Array(n);
    let st = [init.x, init.xc, init.n], s = init.S, d = init.debt, inert = 0;
    let prev = init.asleep ? 1 : 0, bout = init.bout || 0, sStart = init.sStart ?? s;
    for (let i = 0; i < n; i++) {
      const a = r.asleep[i];
      if (a && !prev) { bout = 0; sStart = s; }
      if (!a && prev) {
        d = Math.max(0, d + (bout >= 3 ? crew.need - bout : -bout));
        const sws = bout <= 0.36 ? 0.08 : bout <= 1.15 ? Math.min(0.9, 0.25 + 0.9 * sStart) : bout <= 1.75 ? 0.15 : 0.2;
        inert = 0.3 * sws;
      }
      x[i] = st[0]; S[i] = s; debt[i] = d;
      R[i] = a ? NaN : 100 * clamp(0.66 + 0.22 * st[0] - 0.40 * (s - 0.3) - 0.04 * d - inert, 0, 1);
      st = step(st, r.lux[i], crew.tau);
      if (a) { s -= DT * s / 4.2; bout += DT; }
      else { s += DT * (1 - s) / 18.2; inert *= Math.exp(-DT / 0.3); }
      d *= Math.exp(-DT / 96);
      prev = a;
    }
    return { t0, n, x, S, R, debt, lux: r.lux, asleep: r.asleep, crit: r.crit,
      end: { x: st[0], xc: st[1], n: st[2], S: s, debt: d, asleep: prev, bout, sStart } };
  }

  const baseStart = k => BASE_SLEEP + 24 * k;
  const sleepDur = crew => crew.need + 0.5;
  function baseItems(crew, kFrom, kTo) {
    const out = [], dur = sleepDur(crew);
    for (let k = kFrom; k <= kTo; k++) {
      out.push({ id: 'sl' + k, type: 'sleep', start: baseStart(k), end: baseStart(k) + dur, night: k });
      out.push({ id: 'wd' + k, type: 'light', kind: 'dim', role: 'wind', start: baseStart(k) - 2, end: baseStart(k) });
    }
    return out;
  }
  const leadCache = new Map();
  // Hours from predicted CBTmin to habitual wake on the baseline schedule (the alignment target).
  function baseLead(crew) {
    const key = crew.tau + '|' + crew.need;
    if (leadCache.has(key)) return leadCache.get(key);
    const sim = simulate(crew, baseItems(crew, -1, 4), entrain(crew), 0, 4 * 24);
    const c = cbtMins(sim).find(v => v > 24 && v < 48);
    const lead = (BASE_SLEEP + sleepDur(crew)) - c;
    leadCache.set(key, lead); return lead;
  }
  const entrainCache = new Map();
  function entrain(crew) {
    const key = crew.tau + '|' + crew.need;
    if (entrainCache.has(key)) return entrainCache.get(key);
    const items = baseItems(crew, -31, 0);
    const sim = simulate(crew, items, { x: -0.5, xc: -1, n: 0, S: 0.3, debt: 0, asleep: 0 }, -30 * 24, 0);
    entrainCache.set(key, sim.end);
    return sim.end;
  }

  function cbtMins(sim) {
    const out = [];
    for (let i = 1; i < sim.n - 1; i++) if (sim.x[i] < sim.x[i - 1] && sim.x[i] <= sim.x[i + 1] && sim.x[i] < -0.2) out.push(sim.t0 + i * DT + CBT_OFF);
    return out;
  }

  const wrap = d => { d = ((d % 24) + 24) % 24; if (d > 12) d -= 24; return d; };
  const sortByStart = a => a.sort((p, q) => p.start - q.start);

  // Awake intervals inside [a,b], given sleep/nap items.
  function awakeParts(a, b, rest) {
    let parts = [[a, b]];
    for (const s of rest) {
      const next = [];
      for (const [p, q] of parts) {
        if (s.end <= p || s.start >= q) { next.push([p, q]); continue; }
        if (s.start > p) next.push([p, s.start]);
        if (s.end < q) next.push([s.end, q]);
      }
      parts = next;
    }
    return parts.filter(([p, q]) => q - p >= 0.5);
  }

  function cutSleeps(sleeps, a, b) {
    let lost = 0; const out = [];
    for (const s of sleeps) {
      if (s.end <= a || s.start >= b) { out.push(s); continue; }
      let kept = 0;
      if (Math.min(s.end, a) - s.start >= 1) { out.push({ ...s, end: Math.min(s.end, a) }); kept += Math.min(s.end, a) - s.start; }
      if (s.end - Math.max(s.start, b) >= 1) { out.push({ ...s, id: s.id + 'b', start: Math.max(s.start, b) }); kept += s.end - Math.max(s.start, b); }
      lost += (s.end - s.start) - kept;
    }
    return { sleeps: out, lost };
  }

  // Place light windows from predicted CBTmin vs. the planned wake time of each night.
  function placeLights(cbts, sleeps, rest, tFrom, tTo, meta, lead) {
    const out = [];
    for (const c of cbts) {
      if (c < tFrom || c > tTo) continue;
      let s = null, best = 1e9;
      for (const sl of sleeps) { const dd = Math.abs((sl.start + sl.end) / 2 - c); if (dd < best && c > sl.start - 6 && c < sl.end + 6) { best = dd; s = sl; } }
      if (!s) continue;
      const e = c - (s.end - lead);   // positive = clock running late -> advance
      if (Math.abs(e) <= 0.5) continue;
      if (e > 0) {
        const st = Math.max(c + 0.5, s.end), len = e > 1.5 ? 2 : 1;
        for (const [p, q] of awakeParts(st, st + len, rest)) out.push({ id: 'la' + Math.round(p * 10), type: 'light', kind: 'alert', role: 'shift', dir: 'earlier', start: p, end: q, ...meta });
        for (const [p, q] of awakeParts(c - 6, c, rest)) out.push({ id: 'ld' + Math.round(p * 10), type: 'light', kind: 'dim', role: 'anti', dir: 'earlier', start: p, end: q, ...meta });
      } else {
        for (const [p, q] of awakeParts(c - 5.5, c - 2.5, rest)) out.push({ id: 'la' + Math.round(p * 10), type: 'light', kind: 'alert', role: 'shift', dir: 'later', start: p, end: q, ...meta });
        for (const [p, q] of awakeParts(c, c + 5, rest)) { const q2 = Math.min(q, p + 3); if (q2 - p >= 0.5) out.push({ id: 'ld' + Math.round(p * 10), type: 'light', kind: 'dim', role: 'anti', dir: 'later', start: p, end: q2, ...meta }); }
      }
    }
    return out;
  }

  function critStats(sim) {
    let mn = 101, sum = 0, cnt = 0;
    for (let i = 0; i < sim.n; i++) if (sim.crit[i] && !isNaN(sim.R[i])) { mn = Math.min(mn, sim.R[i]); sum += sim.R[i]; cnt++; }
    return cnt ? { min: mn, mean: sum / cnt } : null;
  }

  // Build sleep/nap/light items around a set of main sleeps and score them.
  function assemble(crew, init, sleeps0, crit, opt) {
    let sleeps = sortByStart(sleeps0.map(s => ({ ...s })));
    let lost = 0;
    if (crit) { const c = cutSleeps(sleeps, crit.start - 0.75, crit.end + 0.25); sleeps = sortByStart(c.sleeps); lost = c.lost;
      if (lost > 0.5 && opt.mitigate) {
        const rs = crit.end + 0.5, re = rs + Math.min(lost, 4);
        if (!sleeps.some(s => s.start < re + 2 && s.end > rs)) sleeps.push({ id: 'rec' + Math.round(rs * 10), type: 'sleep', start: rs, end: re, recovery: true });
        sleeps = sortByStart(sleeps);
      }
    }
    const naps = [];
    if (opt.mitigate) {
      for (let i = 0; i + 1 < sleeps.length; i++) {
        const a = sleeps[i].end, b = sleeps[i + 1].start, w = b - a;
        if (w <= 17.5) continue;
        let ns = a + w * 0.5, ne = ns + 1.5;
        if (crit && ne > crit.start - 1 && ns < crit.end + 0.25) {
          if (crit.start - 1.25 - 1.5 >= a + 3) { ne = crit.start - 1.25; ns = ne - 1.5; }
          else if (crit.end + 0.5 + 1.5 <= b - 3) { ns = crit.end + 0.5; ne = ns + 1.5; }
          else continue;
        }
        naps.push({ id: 'nb' + Math.round(ns * 10), type: 'nap', role: 'bridge', wake: w, start: ns, end: ne });
      }
    }
    const winds = opt.mitigate ? sleeps.filter(s => !s.recovery).map(s => ({ id: 'wd' + Math.round(s.start * 10), type: 'light', kind: 'dim', role: 'wind', start: s.start - 2, end: s.start })) : [];
    const critItems = crit ? [{ id: 'cr' + Math.round(crit.start * 10), type: 'critical', label: crit.label, start: crit.start, end: crit.end }] : [];
    const rest = () => sortByStart([...sleeps, ...naps]);
    let lights = [];
    const build = () => [...winds, ...lights, ...critItems, ...rest()];
    let sim = simulate(crew, build(), init, 0, HORIZON);
    if (opt.lights) {
      const tFrom = opt.lightFrom ?? 0, tTo = opt.lightTo ?? HORIZON;
      for (let it = 0; it < 2; it++) {
        lights = placeLights(cbtMins(sim), sleeps, rest(), tFrom, tTo, { goal: crit ? crit.label : null }, opt.lead ?? 2.5);
        sim = simulate(crew, build(), init, 0, HORIZON);
      }
    }
    if (crit && opt.mitigate) {
      let cs = critStats(sim);
      if (cs && cs.min < 75) {
        critItems[0].alertLight = true;
        lights.push({ id: 'lc' + Math.round(crit.start * 10), type: 'light', kind: 'alert', role: 'counter', start: crit.start - 0.5, end: crit.start, goal: crit.label });
        sim = simulate(crew, build(), init, 0, HORIZON);
        cs = critStats(sim);
        const score = c => c ? c.min + 0.3 * c.mean : 0;
        let bestScore = score(cs), bestNap = null, bestSim = sim;
        for (const [d, lead] of [[1 / 6, 0.5], [1 / 3, 0.5], [1.5, 1.0]]) {
          const ne = crit.start - lead, ns = ne - d;
          const all = rest();
          const prevEnd = Math.max(-1e9, ...all.filter(s => s.end <= ns).map(s => s.end));
          if (all.some(s => s.start < ne && s.end > ns) || ns < prevEnd + 1.5) continue;
          const nap = { id: 'nc' + Math.round(ns * 10), type: 'nap', role: 'crit', goal: crit.label, start: ns, end: ne };
          naps.push(nap);
          const s2 = simulate(crew, build(), init, 0, HORIZON);
          naps.pop();
          const sc = score(critStats(s2));
          if (sc > bestScore + 2) { bestScore = sc; bestNap = nap; bestSim = s2; }
        }
        if (bestNap) naps.push(bestNap);
        sim = bestSim;
        if (!bestNap) sim = simulate(crew, build(), init, 0, HORIZON);
      }
    }
    const items = sortByStart(build());
    const cs = crit ? critStats(sim) : null;
    let post = 0;
    if (crit) { for (let i = 0; i < sim.n; i++) { const t = i * DT; if (t >= crit.end && t <= crit.end + 48 && !isNaN(sim.R[i])) post += Math.pow(Math.max(0, 60 - sim.R[i]), 2) * DT / 100; } }
    let shortfall = 0;
    for (let i = 0; i < sim.n; i++) if (sim.crit[i] && !isNaN(sim.R[i])) shortfall += Math.pow(Math.max(0, 75 - sim.R[i]), 2) * DT / 10;
    const lightCount = lights.filter(l => l.kind === 'alert').length;
    const cost = shortfall + 4 * lost + 1.5 * lightCount + 0.5 * naps.length + post;
    return { items, sim, crit: cs, cost, sleepLost: lost, lightCount, napCount: naps.length };
  }

  // The Slam-Shift planner. spec = {delta, startDay, crit:{label, day, start, dur}} or null for baseline.
  function buildPlan(crew, spec) {
    const t0 = performance.now();
    const init = entrain(crew), dur = sleepDur(crew);
    const lead = baseLead(crew);
    const nights = []; for (let k = -1; k <= 14; k++) nights.push(k);
    const mk = (offs) => nights.map(k => ({ id: 'sl' + k, type: 'sleep', night: k, start: baseStart(k) + offs(k), end: baseStart(k) + offs(k) + dur }));
    if (!spec) {
      const a = assemble(crew, init, mk(() => 0), null, { lights: false, mitigate: true });
      return { ...a, strategy: 'Baseline', options: [], reasons: [`Nominal day: sleep 21:30, wake ${hm(BASE_SLEEP + dur)} GMT.`], ms: performance.now() - t0, spec: null };
    }
    const delta = wrap(spec.delta);
    const Tc = (spec.crit.day - 1) * 24 + spec.crit.start, Te = Tc + spec.crit.dur;
    const crit = { label: spec.crit.label, start: Tc, end: Te };
    const kStar = Math.floor((Tc - dur - BASE_SLEEP - delta) / 24);
    const startNight = spec.startDay - 1;
    const avail = Math.max(0, kStar - startNight);
    const dir = delta < 0 ? 'advance' : 'delay';
    const reasons = [];
    reasons.push(delta === 0 ? 'No clock shift requested; protecting the critical block only.' :
      `Required shift: ${delta > 0 ? '+' : '−'}${Math.abs(delta)} h (${dir}, ${delta < 0 ? 'earlier' : 'later'}).`);
    reasons.push(`${avail} night${avail === 1 ? '' : 's'} available before ${crit.label} (${clk(Tc)}).`);
    if (BASE_SLEEP + delta + 24 * (kStar + 1) < Te) reasons.push('The critical block runs into the new sleep window; that sleep is split around it.');
    const lockedOff = k => k >= kStar ? delta : 0;
    const options = [];
    const holdS = mk(lockedOff);
    const hold = assemble(crew, init, holdS, crit, { lights: true, mitigate: true, lead, lightFrom: (kStar) * 24, lightTo: HORIZON });
    options.push({ name: 'Hold-and-Mitigate', rate: 0, reached: delta === 0, plan: hold });
    const canShift = delta !== 0 && avail >= 2;
    if (delta !== 0 && !canShift) reasons.push('Fewer than 2 nights to prepare: holding the clock and mitigating instead of a partial shift.');
    if (canShift) {
      const rates = dir === 'advance' ? [0.5, 1, 1.5] : [1, 1.5, 2];
      for (const r of rates) {
        const sg = Math.sign(delta), A = Math.abs(delta);
        const off = k => k < startNight ? 0 : k >= kStar ? delta : sg * Math.min(r * (k - startNight + 1), A);
        const reached = r * avail >= A;
        const p = assemble(crew, init, mk(off), crit, { lights: true, mitigate: true, lead, lightFrom: startNight * 24, lightTo: HORIZON });
        options.push({ name: `${dir === 'advance' ? 'Advance' : 'Delay'} ${r} h/day`, rate: r, reached, remaining: Math.max(0, A - r * avail), plan: p });
      }
      const other = 24 - Math.abs(delta), orate = dir === 'advance' ? 1.5 : 1;
      reasons.push(`The opposite direction (${dir === 'advance' ? 'delay' : 'advance'} ${other} h) would need about ${Math.ceil(other / orate)} days; not feasible here.`);
    }
    options.sort((a, b) => a.plan.cost - b.plan.cost);
    const best = options[0];
    if (best.rate > 0) reasons.push(best.reached ? `Chosen: ${best.name}, reaching the new schedule before the critical block.` :
      `Chosen: ${best.name}; the last ${best.remaining.toFixed(1)} h is taken as a single jump the night before.`);
    else if (delta !== 0) reasons.push('Chosen: Hold-and-Mitigate. The clock stays put until the critical day, then naps and timed light cover the gap.');
    const cs = best.plan.crit;
    if (cs) {
      reasons.push(`Predicted readiness during ${crit.label}: ${Math.round(cs.min)} at worst, ${Math.round(cs.mean)} on average (${band(cs.min)}).`);
      if (cs.min < 70) reasons.push('Readiness gap remains. Flight surgeon review recommended (caffeine timing, task reassignment).');
    }
    const unmit = assemble(crew, init, holdS, crit, { lights: false, mitigate: false });
    return { ...best.plan, strategy: best.name, options: options.map(o => ({ name: o.name, cost: o.plan.cost, crit: o.plan.crit, sleepLost: o.plan.sleepLost, lights: o.plan.lightCount, naps: o.plan.napCount })),
      reasons, unmit: { crit: unmit.crit, sim: unmit.sim }, ms: performance.now() - t0, spec, critWin: crit };
  }

  // Re-simulate a plan with crew-reported skips and short sleeps.
  function applyLive(crew, plan, isSkipped, lostFor) {
    const items = plan.items.map(it => {
      const o = { ...it };
      if ((it.type === 'light' || it.type === 'nap') && isSkipped(it)) o.skipped = true;
      if (it.type === 'sleep') { const l = lostFor(it); if (l) o.end = Math.max(o.start + 1, o.end - l); }
      return o;
    });
    return { items, sim: simulate(crew, items, entrain(crew), 0, HORIZON) };
  }

  const band = r => r >= 70 ? 'Green' : r >= 50 ? 'Amber' : 'Red';
  function hm(t) { const m = Math.round((((t % 24) + 24) % 24) * 60) % 1440; return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'); }
  function clk(t) { const tt = t + 1e-6; return 'D' + (Math.floor(tt / 24) + 1) + ' ' + hm(t); }

  // Validation: phase response curve to a 3 h, 1500 lux pulse.
  function prc(tau = 24.2) {
    const crew = { tau, need: 8 };
    const init = entrain(crew);
    const items = baseItems(crew, -1, 6);
    const ctl = simulate(crew, items, init, 0, 6 * 24);
    const cb = cbtMins(ctl);
    const ref = cb.find(c => c > 24 && c < 48);
    const ctlLater = cb.find(c => c > 96 && c < 120);
    const pts = [];
    for (let h = 0; h < 24; h += 1) {
      const ps = 24 + h;
      const sim = simulate(crew, [...items, { type: 'pulse', lux: 1500, start: ps, end: ps + 3 }], init, 0, 6 * 24);
      const c2 = cbtMins(sim).find(c => Math.abs(c - ctlLater) < 8);
      if (c2 == null) continue;
      pts.push({ rel: wrap(ps + 1.5 - ref), shift: ctlLater - c2 });
    }
    pts.sort((a, b) => a.rel - b.rel);
    return { pts, ref, wake: BASE_SLEEP + 8.5 - 24 };
  }

  return { baseLead, buildPlan, applyLive, simulate, entrain, cbtMins, prc, critStats, band, hm, clk, wrap, DT, HORIZON, LUX, BASE_SLEEP, P };
})();
/*ENGINE-END*/
if (typeof module !== 'undefined') module.exports = ENGINE;
