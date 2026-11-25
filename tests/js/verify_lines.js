// Verifies record lines from stdin with the UI's own CRC code (web/src/store-local.js). Used by REQ-VER-003.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'src', 'store-local.js'), 'utf8');
const ctx = { TextEncoder, console };
vm.createContext(ctx);
vm.runInContext(src + '\nthis.crcHex = crcHex;', ctx);
const lines = fs.readFileSync(0, 'utf8').split('\n').filter(Boolean);
let ok = 0;
for (const line of lines) {
  const a = JSON.parse(line);
  if (ctx.crcHex(JSON.stringify(a.slice(0, 4))) === a[4]) ok++;
  else console.error('mismatch:', line);
}
console.log(`${ok}/${lines.length} valid`);
process.exit(ok === lines.length ? 0 : 1);
