/* playwright-cli run-code --filename tools/check_png_export.js
   Actual downloads and pixel checks in a separate context; user saves untouched. */
async caller => {
  const context = await caller.context().browser().newContext({
    viewport: {width: 1440, height: 1000}, locale: 'en-US', reducedMotion: 'reduce'
  });
  const checks = [], errors = [];
  const check = (name, ok) => {
    checks.push({name, ok: !!ok}); if(!ok)throw Error(name);
  };
  try {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(caller.url().split('#')[0]);
    await page.waitForFunction(() => workspaceReady);
    check('PNG enabled beside existing SVG export', await page.evaluate(() =>
      !$('dl-png').disabled && $('dl-png').parentElement.id === 'editor-actions'
      && $('dl-svg').parentElement.id === 'editor-actions'));
    check('English photo label explains transparent PNG on hover', await page.evaluate(() =>
      $('dl-png').textContent==='Take a photo' && $('dl-png').title.includes('transparent PNG')));
    await page.evaluate(() => {
      const create = URL.createObjectURL;
      URL.createObjectURL = function(blob){
        if(blob.type === 'image/png')window.pngTestBlob = blob;
        return create.call(this, blob);
      };
      window.pngPlain = value => JSON.stringify(value, (_, v) =>
        typeof v === 'bigint' ? String(v) : v instanceof Map ? [...v] : v);
      window.pngPixels = async blob => {
        const image = await createImageBitmap(blob), canvas = document.createElement('canvas');
        canvas.width = image.width; canvas.height = image.height;
        const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0);
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        let clear = 0, opaque = 0;
        const colors = new Set();
        for(let i=0; i<pixels.length; i+=4){
          if(pixels[i+3] === 0)clear++;
          if(pixels[i+3] === 255){opaque++;colors.add([...pixels.slice(i,i+3)].join(','));}
        }
        const result = {width: canvas.width, height: canvas.height, clear, opaque,
          corners: [0,canvas.width-1,(canvas.height-1)*canvas.width,canvas.width*canvas.height-1]
            .map(n => pixels[n*4+3]), colors: [...colors]};
        image.close(); return result;
      };
      window.pngBefore = captureWorkspace();
    });
    const downloadPng = async path => {
      const waiting = page.waitForEvent('download');
      await page.locator('#dl-png').click();
      const download = await waiting;
      await download.saveAs(path);
      await page.waitForFunction(() => !pngBusy);
      check('download has PNG filename', download.suggestedFilename().endsWith('.png'));
      return page.evaluate(() => pngPixels(pngTestBlob));
    };
    const first = await downloadPng('output/playwright/transparent-opening.png');
    check('opening PNG has real transparent background and visible ink',
      first.clear > first.width*first.height*.5 && first.opaque > 100
      && first.corners.every(a => a === 0));
    check('longest edge is 2048px', Math.max(first.width, first.height) === 2048);
    check('export leaves exact SVG, geometry, settings and composer unchanged', await page.evaluate(() =>
      pngPlain(captureWorkspace()) === pngPlain(pngBefore)));
    check('PNG warning distinguishes artwork from readable SVG', await page.evaluate(() =>
      !$('png-done').hidden && $('png-done').textContent.includes('Keep the SVG')));

    await page.evaluate(() => {
      state.me = 'A'; $('me').value = 'A';
      $('msg').value = 'Signal'; $('sig').value = 'A'; commit();
      setAim('reply', 0, false); $('msg').value = 'Reply'; $('sig').value = 'B'; commit();
      $('msg').value = 'Do not commit this draft';
      zoomWall(2);
      setTheme('dark');
      window.pngBefore = captureWorkspace();
      const style = getComputedStyle($('art'));
      window.pngExpectedInks = sigsOf().map(sig => style.getPropertyValue('--ink-' + inkFor(sig)).trim());
      window.pngExpectedRGB = pngExpectedInks.map(ink => {
        const canvas = document.createElement('canvas');canvas.width=canvas.height=1;
        const ctx = canvas.getContext('2d');ctx.fillStyle=ink;ctx.fillRect(0,0,1,1);
        return [...ctx.getImageData(0,0,1,1).data.slice(0,3)].join(',');
      });
    });
    const reply = await downloadPng('output/playwright/transparent-replies.png');
    const expectedColors = await page.evaluate(() => pngExpectedRGB);
    check('orange and purple spiral colors survive raster export',
      new Set(expectedColors).size === 2 && expectedColors.every(c => reply.colors.includes(c)));
    check('multi-spiral PNG stays transparent', reply.clear > reply.width*reply.height*.5 && reply.corners.every(a => a === 0));
    check('export preserves multi-spiral wall, unfinished draft and zoom', await page.evaluate(() =>
      pngPlain(captureWorkspace()) === pngPlain(pngBefore)));
    check('source includes all committed paths and strips only paper rectangle', await page.evaluate(() => {
      const original = new DOMParser().parseFromString(state.svg, 'image/svg+xml');
      const prepared = transparentPngSource(state.svg, pngExpectedInks);
      const clean = new DOMParser().parseFromString(prepared.text, 'image/svg+xml');
      return original.querySelectorAll('path').length === clean.querySelectorAll('path').length
        && clean.querySelectorAll('[data-spiral]').length === 2 && !clean.querySelector('rect')
        && !clean.querySelector('.beams,.socket-layer');
    }));
    await page.evaluate(async () => {
      window.pngBeforeZoom = [...new Uint8Array(await pngTestBlob.arrayBuffer())];
      zoomWall(1.4);$('plate').classList.add('growing');
    });
    await downloadPng('output/playwright/transparent-zoomed.png');
    check('zoom and growth animation cannot crop or hide PNG content', await page.evaluate(async () => {
      const bytes = new Uint8Array(await pngTestBlob.arrayBuffer());
      return bytes.length === pngBeforeZoom.length && bytes.every((b,i) => b === pngBeforeZoom[i]);
    }));
    await page.evaluate(() => $('plate').classList.remove('growing'));
    const svgDownload = page.waitForEvent('download');
    await page.locator('#dl-svg').click();
    const svg = await svgDownload;
    await svg.saveAs('output/playwright/png-regression-original.svg');
    check('existing SVG download remains available', svg.suggestedFilename().endsWith('.svg'));

    // Flush a slow slider's pending shape without committing the input text.
    const delayed = page.waitForEvent('download');
    const pending = await page.evaluate(async () => {
      lastBuildMs=300;state.tight=.34;$('tight').value=.34;reshape();
      const hadPending=!!reshapeTimer;
      await pngBtn.onclick();
      return hadPending && !reshapeTimer && state.placements.every(p=>p.L.b===.34)
        && $('msg').value==='Do not commit this draft' && state.scroll[1].text==='Reply';
    });
    await (await delayed).saveAs('output/playwright/transparent-delayed.png');
    check('pending slider is flushed without committing draft', pending);

    check('PNG failure recovers button and leaves wall untouched', await page.evaluate(async () => {
      const original=transparentPngBlob,before=state.svg;
      try { transparentPngBlob=async()=>{throw Error('Test encode failure');};await pngBtn.onclick(); }
      finally { transparentPngBlob=original; }
      return !pngBusy && !pngBtn.disabled && state.svg===before;
    }));
    page.once('dialog', d => d.accept());
    await page.locator('#clear-wall').click();
    check('empty wall disables PNG', !(await page.locator('#dl-png').isEnabled()));
    await page.locator('#editor-undo').click();
    check('undo re-enables PNG', await page.locator('#dl-png').isEnabled());
    await page.locator('#m-read').click();
    check('writer PNG control is hidden in read mode', !(await page.locator('#dl-png').isVisible()));
    await page.locator('#m-write').click();
    await page.locator('#lang-zh').click();
    check('PNG label and help switch to Chinese', await page.evaluate(() =>
      $('dl-png').textContent==='拍张照片' && $('dl-png').title.includes('透明 PNG')
      && $('dl-png').title.includes('2048 像素')));
    await context.setOffline(true);
    const keyboardDownload = page.waitForEvent('download');
    await page.locator('#dl-png').focus();
    await page.locator('#dl-png').press('Enter');
    await (await keyboardDownload).saveAs('output/playwright/transparent-keyboard-offline.png');
    await page.waitForFunction(() => !pngBusy);
    check('keyboard export also works offline', await page.evaluate(() =>
      pngTestBlob.type==='image/png' && !pngBtn.disabled));
    await context.setOffline(false);
    await page.setViewportSize({width:390,height:844});
    await page.locator('#dl-png').scrollIntoViewIfNeeded();
    check('mobile PNG control fits viewport', await page.locator('#dl-png').evaluate(el => {
      const box=el.getBoundingClientRect();return box.left>=0 && box.right<=innerWidth
        && document.documentElement.scrollWidth<=innerWidth;
    }));
    await page.locator('#editor-actions').screenshot({path:'output/playwright/png-toolbar-mobile.png'});
    const touchContext = await caller.context().browser().newContext({
      viewport:{width:390,height:844},hasTouch:true,isMobile:true,locale:'zh-CN'
    });
    try {
      const touchPage = await touchContext.newPage();
      await touchPage.goto(caller.url().split('#')[0]);
      await touchPage.waitForFunction(() => workspaceReady);
      const touchDownload = touchPage.waitForEvent('download');
      await touchPage.locator('#dl-png').tap();
      const downloaded = await touchDownload;
      await downloaded.saveAs('output/playwright/transparent-touch.png');
      check('touch tap downloads a PNG', downloaded.suggestedFilename().endsWith('.png'));
    } finally { await touchContext.close(); }
    check('no browser errors', errors.length===0);
    return {passed:checks.length,opening:{...first,colors:first.colors.slice(0,8)},reply:{...reply,colors:reply.colors.slice(0,8)},checks};
  } finally { await context.close(); }
}
