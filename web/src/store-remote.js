/*STORE-REMOTE-START*/
// Store backed by the local data service (service/lsst_service). Same interface as LocalStore.
// Calls are synchronous on purpose: append() does not return until the service has fsynced
// every log copy, so the UI can never show a state that is not durable (REQ-DAT-002).
const RemoteStore = (() => {
  let records = [], health = null;
  function call(method, path, body) {
    const x = new XMLHttpRequest();
    x.open(method, path, false);
    if (body !== undefined) x.setRequestHeader('Content-Type', 'application/json');
    x.send(body === undefined ? null : JSON.stringify(body));
    if (x.status !== 200) throw new Error(`${method} ${path} failed (${x.status}): ${x.responseText}`);
    return JSON.parse(x.responseText);
  }
  function parse(line) {
    try {
      const a = JSON.parse(line);
      if (!Array.isArray(a) || a.length !== 5) return null;
      if (crcHex(JSON.stringify(a.slice(0, 4))) !== a[4]) return null;   // cross-checks the service's CRC
      return { seq: a[0], type: a[1], payload: a[2], prev: a[3], crc: a[4], line };
    } catch (e) { return null; }
  }
  function available() {
    if (location.protocol === 'file:') return false;
    try { health = call('GET', '/api/health'); return !!health.ok; } catch (e) { return false; }
  }
  return {
    available,
    append(type, payload) {
      const rec = parse(call('POST', '/api/append', { type, payload }).line);
      if (!rec) throw new Error('The data service returned a record that fails its checksum.');
      records.push(rec); return rec;
    },
    recover() {
      const r = call('GET', '/api/recover');
      records = r.lines.map(parse).filter(Boolean);
      return { ...r.report, clientRejected: r.lines.length - records.length };
    },
    readSnapshot: () => call('GET', '/api/snapshot'),
    writeSnapshot: (seq, hash) => call('POST', '/api/snapshot', { seq, hash }).slot,
    corrupt: (copy, line) => call('POST', '/api/fault', { kind: 'corrupt', copy, line }).line,
    corruptSnap: () => call('POST', '/api/fault', { kind: 'corrupt-snapshot' }).slot,
    tornAppend: (type, payload) => call('POST', '/api/fault', { kind: 'torn', type, payload }).seq,
    wipe() { call('POST', '/api/fault', { kind: 'wipe' }); records = []; },
    lineCount: () => call('GET', '/api/linecount').counts,
    get records() { return records; },
    isInit: () => call('GET', '/api/state').init,
    markInit: () => call('POST', '/api/init', {}),
    alive: () => { try { call('POST', '/api/alive', {}); } catch (e) { /* service restarting */ } },
    lastAlive: () => call('GET', '/api/state').alive,
    lights: { get: () => call('GET', '/api/lights'), set: mode => call('POST', '/api/lights', { mode }) },
    // tablet hardware (REQ-HW-011 to 016)
    controls: () => call('GET', '/api/controls'),
    indicator: pattern => call('POST', '/api/indicator', { pattern }),
    backlight: level => call('POST', '/api/backlight', { level }),
    sim: body => call('POST', '/api/sim', body),
    health: () => health,
    persistent: true, remote: true
  };
})();
const Store = RemoteStore.available() ? RemoteStore : LocalStore;
/*STORE-REMOTE-END*/
