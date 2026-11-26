const { chromium } = require('playwright');
(async () => {
  const url = process.argv[2] || 'http://localhost:8765/';
  const out = process.argv[3] || 'shots/a.png';
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1400, height: 900 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.type() + ': ' + m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  await p.goto(url);
  await p.waitForTimeout(+(process.argv[4] || 4000));
  await p.screenshot({ path: out });
  console.log(errs.slice(0, 20).join('\n'));
  await b.close();
})();
