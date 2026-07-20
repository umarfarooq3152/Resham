import { build, context } from 'esbuild';
import { cp, mkdir, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(root, 'dist');
const watch = process.argv.includes('--watch');

async function copyStaticFiles() {
  await mkdir(dist, { recursive: true });
  await Promise.all([
    cp(path.join(root, 'manifest.json'), path.join(dist, 'manifest.json')),
    cp(path.join(root, 'popup.html'), path.join(dist, 'popup.html')),
    cp(path.join(root, 'microphone.html'), path.join(dist, 'microphone.html')),
    cp(path.join(root, 'src/styles.css'), path.join(dist, 'popup.css')),
    cp(path.join(root, 'src/microphone.css'), path.join(dist, 'microphone.css')),
    cp(path.join(root, '../web/src/assets/images/dhaaga-logo.png'), path.join(dist, 'dhaaga-logo.png')),
  ]);
}

await rm(dist, { recursive: true, force: true });
await copyStaticFiles();

const options = {
  entryPoints: {
    background: path.join(root, 'src/background.ts'),
    popup: path.join(root, 'src/popup.ts'),
    microphone: path.join(root, 'src/microphone.ts'),
  },
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: 'chrome116',
  outdir: dist,
  entryNames: '[name]',
  sourcemap: false,
  logLevel: 'info',
};

if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  console.log('Watching Resham extension sources...');
} else {
  await build(options);
}
