/*STORE-LOCAL-START*/
// Browser-only fallback store (demo without the data service). localStorage cannot fsync,
// so this backend does NOT satisfy REQ-DAT-002; the Pi build uses RemoteStore.
// ---------- CRC-32C-style checksum (IEEE polynomial) over UTF-8 ----------
const CRC_T = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
const ENC = new TextEncoder();
function crcHex(str) { const b = ENC.encode(str); let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = CRC_T[(c ^ b[i]) & 0xFF] ^ (c >>> 8); return ((c ^ 0xFFFFFFFF) >>> 0).toString(16).padStart(8, '0'); }

// ---------- Append-only event log: 3 copies, CRC + hash chain, A/B snapshots ----------
const LocalStore = (() => {
  const COPIES = ['lsst.log.A', 'lsst.log.B', 'lsst.log.C'];
  const SNAPS = { A: 'lsst.snap.A', B: 'lsst.snap.B' }, PTR = 'lsst.snap.ptr', INIT = 'lsst.init', ALIVE = 'lsst.alive';
  const mem = {};
  let ls = null;
  try { localStorage.setItem('lsst.probe', '1'); localStorage.removeItem('lsst.probe'); ls = localStorage; } catch (e) { ls = null; }
  const get = k => { if (ls) { try { return ls.getItem(k); } catch (e) { /* fall through */ } } return k in mem ? mem[k] : null; };
  const set = (k, v) => { if (ls) { try { ls.setItem(k, v); return; } catch (e) { /* fall through */ } } mem[k] = v; };
  let records = [], lastCrc = '00000000';

  const makeLine = (seq, type, payload, prev) => { const body = JSON.stringify([seq, type, payload, prev]); return JSON.stringify([seq, type, payload, prev, crcHex(body)]); };
  function parseLine(line) {
    try {
      const a = JSON.parse(line);
      if (!Array.isArray(a) || a.length !== 5) return null;
      if (crcHex(JSON.stringify(a.slice(0, 4))) !== a[4]) return null;
      return { seq: a[0], type: a[1], payload: a[2], prev: a[3], crc: a[4], line };
    } catch (e) { return null; }
  }
  // Write protocol: serialize, checksum, append to every copy, and only then expose to the app.
  function append(type, payload) {
    const seq = (records.length ? records[records.length - 1].seq : 0) + 1;
    const line = makeLine(seq, type, payload, lastCrc);
    for (const k of COPIES) { const cur = get(k); set(k, cur ? cur + '\n' + line : line); }
    const rec = parseLine(line); records.push(rec); lastCrc = rec.crc;
    return rec;
  }
  function recover() {
    const copies = COPIES.map(k => { const raw = get(k) || ''; const lines = raw ? raw.split('\n') : []; return { k, raw, lines, parsed: lines.map(parseLine) }; });
    const rep = { copies: [], repaired: 0, unrecoverable: [], torn: 0, corrupt: 0, chainBreaks: 0, total: 0, votes: 0 };
    copies.forEach((c, ci) => {
      let ok = 0, bad = 0, torn = 0;
      c.parsed.forEach((p, i) => { if (p) ok++; else if (i === c.lines.length - 1) torn++; else bad++; });
      rep.copies.push({ name: 'ABC'[ci], ok, bad, torn }); rep.torn += torn; rep.corrupt += bad;
    });
    const bySeq = new Map(); let maxSeq = 0;
    copies.forEach(c => c.parsed.forEach(p => { if (!p) return; if (!bySeq.has(p.seq)) bySeq.set(p.seq, []); bySeq.get(p.seq).push(p); maxSeq = Math.max(maxSeq, p.seq); }));
    // A tail record found in only one copy is an interrupted append that was never committed: drop it.
    const accepted = []; let prev = '00000000';
    for (let s = 1; s <= maxSeq; s++) {
      const cands = bySeq.get(s) || [];
      if (s === maxSeq && cands.length === 1 && s > 1) { rep.uncommitted = 1; break; }
      if (!cands.length) { rep.unrecoverable.push(s); prev = null; continue; }
      const votes = {}; cands.forEach(p => { votes[p.line] = (votes[p.line] || 0) + 1; });
      const keys = Object.keys(votes); if (keys.length > 1 || cands.length < 3) rep.votes++;
      const best = keys.sort((a, b) => votes[b] - votes[a])[0];
      const rec = cands.find(p => p.line === best);
      if (prev !== null && rec.prev !== prev) rep.chainBreaks++;
      accepted.push(rec); prev = rec.crc;
    }
    const canon = accepted.map(r => r.line).join('\n');
    copies.forEach(c => { if (c.raw !== canon) { rep.repaired++; set(c.k, canon); } });
    records = accepted; lastCrc = accepted.length ? accepted[accepted.length - 1].crc : '00000000';
    rep.total = accepted.length;
    return rep;
  }
  function readSnapshot() {
    const out = {};
    for (const slot of ['A', 'B']) {
      try { const o = JSON.parse(get(SNAPS[slot]) || 'null'); if (o && crcHex(JSON.stringify([o.seq, o.hash, o.at])) === o.crc) out[slot] = o; } catch (e) { /* invalid slot */ }
    }
    const ptr = get(PTR);
    const pick = [out.A, out.B].filter(Boolean).sort((a, b) => b.seq - a.seq)[0] || null;
    return { pick, ptr, valid: Object.keys(out), ptrValid: !!out[ptr] };
  }
  function writeSnapshot(seq, hash) {
    const ptr = get(PTR) === 'A' ? 'B' : 'A';
    const at = Date.now();
    set(SNAPS[ptr], JSON.stringify({ seq, hash, at, crc: crcHex(JSON.stringify([seq, hash, at])) }));
    set(PTR, ptr);   // single small write flips the active slot
    return ptr;
  }
  // ----- fault injection (verification harness) -----
  function flip(line) {
    if (line.length < 12) return line + '#';
    const j = 6 + Math.floor(Math.random() * (line.length - 12));
    const ch = line[j]; const rep = ch === '7' ? '3' : /[0-9]/.test(ch) ? '7' : ch === 'e' ? 'a' : 'e';
    return line.slice(0, j) + rep + line.slice(j + 1);
  }
  function corrupt(copyIdx, lineIdx) {
    const k = COPIES[copyIdx]; const lines = (get(k) || '').split('\n'); if (!lines[0]) return null;
    const i = lineIdx ?? Math.floor(Math.random() * Math.max(1, lines.length - 1));
    lines[i] = flip(lines[i]); set(k, lines.join('\n')); return i;
  }
  function tornAppend(type, payload) {
    const seq = (records.length ? records[records.length - 1].seq : 0) + 1;
    const line = makeLine(seq, type, payload, lastCrc);
    const a = get(COPIES[0]); set(COPIES[0], a ? a + '\n' + line : line);              // copy A: complete
    const b = get(COPIES[1]); set(COPIES[1], (b ? b + '\n' : '') + line.slice(0, Math.floor(line.length / 2))); // copy B: torn
    // copy C: power lost before the write began
    return seq;
  }
  function wipe() { COPIES.forEach(k => set(k, '')); set(SNAPS.A, ''); set(SNAPS.B, ''); records = []; lastCrc = '00000000'; }
  function corruptSnap() { const p = get(PTR); if (p) set(SNAPS[p], '{"seq":1,'); return p; }
  function lineCount() { return COPIES.map(k => { const r = get(k) || ''; return r ? r.split('\n').length : 0; }); }
  return {
    append, recover, readSnapshot, writeSnapshot, corrupt, corruptSnap, tornAppend, wipe, lineCount,
    get records() { return records; }, isInit: () => get(INIT) === '1', markInit: () => set(INIT, '1'),
    alive: () => set(ALIVE, String(Date.now())), lastAlive: () => Number(get(ALIVE) || 0), persistent: !!ls, remote: false
  };
})();
/*STORE-LOCAL-END*/
