// Engine verification (node --test). Test names start with the requirement ID they verify.
const test = require('node:test');
const assert = require('node:assert');
const crypto = require('crypto');
const E = require('../../engine/engine.js');

const CREW = { tau: 24.15, need: 7.5 };
const SLAM = { delta: -4, startDay: 2, crit: { label: 'Docking', day: 6, start: 6, dur: 3 } };
const digest = p => crypto.createHash('sha256').update(JSON.stringify(p.items)).update(Buffer.from(p.sim.R.buffer)).digest('hex');
const mainSleeps = p => p.items.filter(i => i.type === 'sleep' && !i.recovery && i.start > 0 && i.start < 13 * 24);

test('REQ-MDL-001 model entrains stably to the nominal 24 h schedule', () => {
  const p = E.buildPlan(CREW, null);
  const c = E.cbtMins(p.sim).filter(t => t > 24 && t < 12 * 24).map(t => ((t % 24) + 24) % 24);
  assert.ok(c.length >= 10);
  assert.ok(Math.max(...c) - Math.min(...c) < 0.25, `CBTmin drifts ${(Math.max(...c) - Math.min(...c)).toFixed(2)} h`);
});

test('REQ-MDL-002 PRC has both a delay and an advance region', () => {
  const { pts } = E.prc(24.2);
  assert.ok(Math.min(...pts.map(p => p.shift)) < -0.2);
  assert.ok(Math.max(...pts.map(p => p.shift)) > 0.2);
});

test('REQ-MDL-003 PRC delay-to-advance crossover lies within 1 h of CBTmin', { todo: 'Open item OI-1: model crossover is about -1.5 h; refit phase offset (docs/05)' }, () => {
  const { pts } = E.prc(24.2);
  let cross = null;
  for (let i = 1; i < pts.length; i++) if (pts[i - 1].shift < 0 && pts[i].shift >= 0 && Math.abs(pts[i].rel) < 6) {
    const a = pts[i - 1], b = pts[i]; cross = a.rel - a.shift * (b.rel - a.rel) / (b.shift - a.shift);
  }
  assert.ok(cross !== null && Math.abs(cross) <= 1, `crossover ${cross}`);
});

test('REQ-PLN-001 every main sleep opportunity is at least 6.5 h', () => {
  for (const spec of [null, SLAM]) for (const s of mainSleeps(E.buildPlan(CREW, spec))) assert.ok(s.end - s.start >= 6.5, `${E.clk(s.start)} is ${(s.end - s.start).toFixed(1)} h`);
});

test('REQ-PLN-002 a 14-day plan builds in under 2 s', () => {
  const t0 = performance.now(); E.buildPlan({ tau: 24.3, need: 8 }, SLAM); const ms = performance.now() - t0;
  assert.ok(ms < 2000, `${ms.toFixed(0)} ms`);
});

test('REQ-PLN-003 the planner never schedules sleep during a critical block', () => {
  const p = E.buildPlan(CREW, { delta: 3, startDay: 2, crit: { label: 'EVA', day: 4, start: 1, dur: 6 } });
  const c = p.items.find(i => i.type === 'critical');
  for (const s of p.items.filter(i => i.type === 'sleep' || i.type === 'nap')) assert.ok(s.end <= c.start || s.start >= c.end, `${s.type} ${E.clk(s.start)}`);
});

test('REQ-PLN-004 the plan improves worst readiness over the unmitigated slam', () => {
  const p = E.buildPlan(CREW, SLAM);
  assert.ok(p.crit.min > p.unmit.crit.min + 5, `${p.crit.min.toFixed(0)} vs ${p.unmit.crit.min.toFixed(0)}`);
});

test('REQ-PLN-005 fewer than 2 preparation nights selects Hold-and-Mitigate', () => {
  const p = E.buildPlan(CREW, { delta: -4, startDay: 4, crit: { label: 'EVA', day: 5, start: 8, dur: 3 } });
  assert.strictEqual(p.strategy, 'Hold-and-Mitigate');
});

test('REQ-LGT-002 a red-light wind-down precedes every main sleep', () => {
  const p = E.buildPlan(CREW, SLAM);
  for (const s of mainSleeps(p)) assert.ok(p.items.some(i => i.type === 'light' && i.role === 'wind' && Math.abs(i.end - s.start) < 1e-6), E.clk(s.start));
});

test('REQ-LGT-005 alerting light is never scheduled while asleep', () => {
  const p = E.buildPlan(CREW, SLAM);
  const rest = p.items.filter(i => i.type === 'sleep' || i.type === 'nap');
  for (const l of p.items.filter(i => i.type === 'light' && i.kind === 'alert')) for (const s of rest) assert.ok(l.end <= s.start + 1e-6 || l.start >= s.end - 1e-6, `${E.clk(l.start)} overlaps ${E.clk(s.start)}`);
});

test('REQ-VER-001 the same inputs give bit-identical plans', () => {
  assert.strictEqual(digest(E.buildPlan(CREW, SLAM)), digest(E.buildPlan(CREW, SLAM)));
});

test('REQ-SAF-001 every slam plan explains its choice and flags gaps', () => {
  const p = E.buildPlan(CREW, { delta: -6, startDay: 5, crit: { label: 'EVA', day: 6, start: 3, dur: 6 } });
  assert.ok(p.reasons.length >= 3);
  if (p.crit.min < 70) assert.ok(p.reasons.some(r => /gap/i.test(r)));
});
