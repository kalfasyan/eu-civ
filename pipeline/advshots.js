const { chromium } = require('playwright');
(async () => {
  const ids = (process.argv[2] || 'energy,economy,people,prosperity,knowledge,land,commerce,culture,explorer').split(',');
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1400, height: 900 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message + ' ' + (e.stack||'').split('\n')[1]));
  p.on('response', r => { if (r.status() >= 400) errs.push('HTTP ' + r.status() + ' ' + r.url()); });
  await p.goto('http://localhost:8765/');
  await p.waitForTimeout(3500);
  await p.click('#btn-advisors');
  await p.waitForTimeout(800);
  for (const id of ids) {
    errs.push('--- ' + id);
    await p.click(`button[data-adv="${id}"]`);
    await p.waitForTimeout(2500);
    await p.screenshot({ path: `shots/adv-${id}.png` });
  }
  console.log(errs.join('\n'));
  await b.close();
})();
