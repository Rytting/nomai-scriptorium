/* playwright-cli run-code --filename tools/check_empty_language.js
   Run on the built scriptorium; a separate context protects user work. */
async caller => {
  const context = await caller.context().browser().newContext({
    locale: 'zh-CN', viewport: {width: 1200, height: 900}, reducedMotion: 'reduce'
  });
  const checks = [];
  const check = (name, ok) => {
    checks.push({name, ok: !!ok});
    if (!ok) throw Error(name);
  };
  try {
    const page = await context.newPage();
    await page.goto(caller.url().split('#')[0]);
    await page.waitForFunction(() => workspaceReady);
    await page.locator('#m-read').click();
    check('Chinese reader starts with Chinese empty message',
      await page.locator('#plate-msg').innerText() === '等你给一张图');
    for (const lang of ['en', 'zh', 'en']) {
      await page.locator('#lang-' + lang).click();
      const result = await page.evaluate(() => ({
        actual: $('plate-msg').textContent, expected: t('waiting for a drawing'),
        visible: !$('plate-msg').hidden
      }));
      check('reader empty message follows ' + lang + ': ' + JSON.stringify(result),
        result.actual === result.expected && result.visible);
    }
    for (const key of ['reading it', 'waiting for words']) {
      await page.evaluate(key => {setLang('zh'); empty(key);}, key);
      await page.locator('#lang-en').click();
      check('dynamic message follows English: ' + key,
        await page.locator('#plate-msg').innerText() === key);
      await page.locator('#lang-zh').click();
      check('dynamic message returns to Chinese: ' + key,
        await page.evaluate(key => $('plate-msg').textContent === t(key), key));
    }
    await page.evaluate(() => {clearReader(); setTheme('dark');});
    await page.locator('#lang-en').click();
    await page.locator('#plate').screenshot({path: 'output/playwright/empty-language-en.png'});

    // Import an actual SVG and retain the exact rendered node and encoded content.
    await page.evaluate(() => {
      const grid = gridFor('Do not change this scroll.', 'Solanum', null, 'strict', 256);
      readDrawing(renderSVG(grid, 0, 47, 0, 1, .29), 'Test scroll');
      window.emptyTestDrawing = $('art').querySelector('svg');
      window.emptyTestSvg = state.svg;
      window.emptyTestPending = state.pending;
    });
    check('test SVG loads before language switching', await page.evaluate(() =>
      !!emptyTestDrawing && !!state.pending && $('plate-msg').hidden));
    for (const lang of ['zh', 'en']) {
      await page.locator('#lang-' + lang).click();
      check('imported scroll stays intact in ' + lang, await page.evaluate(() =>
        $('art').querySelector('svg') === emptyTestDrawing && state.svg === emptyTestSvg
        && state.pending === emptyTestPending && $('plate-msg').hidden));
    }
    await page.locator('#m-write').click();
    await page.evaluate(() => {
      $('msg').value = 'Keep my words'; $('sig').value = 'My signature'; commit();
      $('msg').value = 'Keep my unfinished draft';
      window.emptyTestWriterSvg = state.svg;
    });
    await page.locator('#lang-zh').click();
    await page.locator('#lang-en').click();
    check('writer content, signature and draft are preserved', await page.evaluate(() =>
      state.scroll[0].text === 'Keep my words' && $('msg').value === 'Keep my unfinished draft'
      && $('sig').value === 'My signature' && state.svg === emptyTestWriterSvg));
    await page.locator('#m-read').click();
    await page.locator('#lang-zh').click();
    await page.locator('#lang-en').click();
    await page.setViewportSize({width: 390, height: 844});
    await page.evaluate(() => setTheme('light'));
    check('mobile/light empty message is English and fits', await page.evaluate(() =>
      $('plate-msg').textContent === 'waiting for a drawing'
      && document.documentElement.scrollWidth <= innerWidth));
    await page.locator('#plate').screenshot({path: 'output/playwright/empty-language-mobile.png'});
    return {passed: checks.length, checks};
  } finally {
    await context.close();
  }
}
