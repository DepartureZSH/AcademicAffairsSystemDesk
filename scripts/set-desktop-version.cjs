// Update only the desktop product's explicit version references, never historical docs.
const fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname, '..');
const version = process.argv[2];
if (!/^\d+\.\d+\.\d+$/.test(version || '')) throw new Error('Expected x.y.z version');
const previous = JSON.parse(fs.readFileSync(path.join(root,'apps/desktop/package.json'),'utf8')).version;
for (const file of ['apps/desktop/package.json','apps/desktop/package-lock.json','apps/desktop/src-tauri/Cargo.toml','apps/desktop/src-tauri/Cargo.lock','apps/desktop/src-tauri/tauri.conf.json','apps/desktop/src/components/AboutView.vue','apps/desktop/src/DevApp.vue','pyproject.toml','uv.lock','sidecar/stt_desktop/storage/project.py','tests/test_release_evidence.py']) {
  const target = path.join(root,file), text = fs.readFileSync(target,'utf8');
  if (!text.includes(previous)) throw new Error(`Previous version not present: ${file}`);
  let updated;
  if (file.endsWith('Cargo.lock') || file === 'uv.lock') {
    updated = text.replace(/(name = "karios-stt-desktop"\r?\nversion = ")[^"]+("\r?\n)/, `$1${version}$2`);
  } else if (file.endsWith('package-lock.json')) {
    const lock = JSON.parse(text); lock.version = version; lock.packages[''].version = version;
    updated = JSON.stringify(lock, null, 2) + '\n';
  } else {
    updated = text.replaceAll(previous,version);
  }
  fs.writeFileSync(target, updated);
}
console.log(`Desktop version: ${previous} -> ${version}`);
