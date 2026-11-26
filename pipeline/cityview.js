const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1400, height: 900 } });
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error' && !m.text().includes('404')) errs.push(m.text()); });
  await p.goto('http://localhost:8765/#city=DE007M');
  await p.waitForTimeout(4000);
  await p.click('text=Open City View');
  await p.waitForTimeout(3500);
  
  await p.click('text=Districts').catch(()=>{}); await p.waitForTimeout(1500); await p.screenshot({ path: 'shots/cv2.png' });
  const el = await p.$('.cv-panel, .cv-scroll, [class*=cv-side]');
  await p.screenshot({ path: 'shots/cv1.png' });
  await p.goto('http://localhost:8765/#at=2900,2350,1.6');
  await p.waitForTimeout(4000);
  await p.screenshot({ path: 'shots/zoom.png' });
  console.log(errs.join('\n'));
  await b.close();
})();
