/* Run with playwright-cli run-code --filename tools/check_reset_opening.js
   against the built scriptorium. All edits stay in an isolated browser context. */
async caller => {
  const context = await caller.context().browser().newContext({
    viewport: { width: 1440, height: 1000 }, locale: 'en-US', reducedMotion: 'reduce'
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
    check('reset is enabled after workspace initialization', await page.locator('#reset-opening').isEnabled());
    await page.evaluate(() => {
      window.resetPlain = value => JSON.stringify(value, (_, v) =>
        typeof v === 'bigint' ? String(v) : v instanceof Map ? [...v] : v);
      window.resetInitial = captureWorkspace();
      $('msg').value = 'A new signal.';
      $('sig').value = 'Sender';
      commit();
      setAim('reply', 0, false);
      $('msg').value = 'We hear you.';
      $('sig').value = 'Receiver';
      commit();
      setAim('edit', 0, false);
      $('msg').value = 'Unfinished root draft';
      setAim('reply', 1, false);
      $('msg').value = 'Unfinished reply';
      $('sig').value = 'Draft author';
      state.tight = .4; $('tight').value = .4;
      state.handMix = 20; $('handmix').value = 20;
      reshape();
      zoomWall(2);
      state.me = 'My observer name'; $('me').value = state.me; rememberMe();
      setTheme('light');
      window.resetBefore = captureWorkspace();
      window.resetHistoryCount = historyPast.length;
    });
    let prompt = '';
    page.once('dialog', async dialog => { prompt = dialog.message(); await dialog.dismiss(); });
    await page.locator('#reset-opening').click();
    check('confirmation describes replacement and undo', /drafts/.test(prompt) && /undo/.test(prompt));
    check('cancel preserves wall, composer, drafts, and history', await page.evaluate(() =>
      resetPlain(captureWorkspace()) === resetPlain(resetBefore) && historyPast.length === resetHistoryCount));

    page.once('dialog', dialog => dialog.accept());
    await page.locator('#reset-opening').click();
    check('reset restores exact initial SVG and drawing settings', await page.evaluate(() =>
      state.svg === resetInitial.svg && resetPlain(captureWorkspace().settings) === resetPlain(resetInitial.settings)));
    check('reset restores opening text, signature, target and dialect', await page.evaluate(() =>
      resetPlain(captureWorkspace().composer) === resetPlain(resetInitial.composer)
      && state.scroll.length === 1 && state.scrollSource === 'opening'
      && resetPlain(state.aim) === resetPlain(resetInitial.aim)));
    check('reset removes old reply and rewrite drafts', await page.evaluate(() =>
      ![...state.editDrafts.values()].some(d => /Unfinished/.test(d.text))));
    check('theme, language and remembered identity are preserved', await page.evaluate(() =>
      LANG === 'en' && isNight() === false && state.me === 'My observer name'
      && localStorage.getItem('nomai.me') === state.me));
    await page.locator('#editor-undo').click();
    check('undo restores exact prior wall, composer, drafts, settings and view', await page.evaluate(() =>
      resetPlain(captureWorkspace()) === resetPlain(resetBefore)));
    await page.locator('#editor-redo').click();
    check('redo returns to opening again', await page.evaluate(() =>
      state.svg === resetInitial.svg && $('msg').value === FIRST.en[0]));

    // A pending debounced shape change must be included in the undo checkpoint.
    await page.locator('#editor-undo').click();
    await page.evaluate(() => {
      lastBuildMs = 300; state.tight = .34; $('tight').value = .34; reshape();
      window.resetPending = !!reshapeTimer;
      const nativeConfirm = window.confirm;
      try {
        window.confirm = () => true;
        resetToOpening();
      } finally {
        window.confirm = nativeConfirm;
      }
    });
    check('reset flushes pending reshape before remembering undo', await page.evaluate(() =>
      resetPending && !reshapeTimer && historyPast.at(-1).settings.tight === .34
      && historyPast.at(-1).placements.every(p => p.tight === .34)));

    await page.locator('#lang-zh').click();
    await page.evaluate(() => {
      $('msg').value = '临时写的一句'; $('sig').value = '测试'; commit();
      setDialectUI('upstream');
    });
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#reset-opening').click();
    const chineseReset = await page.evaluate(() => ({
      lang: LANG, text: $('msg').value, sig: $('sig').value,
      committedText: state.scroll[0].text, base: state.base, dialect: state.dialect,
      expected: FIRST.zh, initialLang: openingWorkspace.lang, aim: state.aim,
      source: state.scrollSource, initialAim: openingWorkspace.aim
    }));
    check('reset uses current Chinese opening, not startup English' +
      (chineseReset.text === chineseReset.expected[0] ? '' : ': ' + JSON.stringify(chineseReset)),
      chineseReset.lang === 'zh' && chineseReset.text === chineseReset.expected[0]
      && chineseReset.sig === chineseReset.expected[1] && chineseReset.committedText === chineseReset.expected[0]
      && chineseReset.base === 200000 && chineseReset.dialect === 'strict');
    check('Chinese reset label is translated', (await page.locator('#reset-opening').innerText()) === '回到初始状态');
    await page.evaluate(() => saveWorkspace(false));
    await page.reload();
    await page.waitForFunction(() => workspaceReady);
    check('reload retains the reset opening, not the old user wall', await page.evaluate(() =>
      state.scroll.length === 1 && state.scroll[0].text === FIRST.zh[0]
      && $('sig').value === FIRST.zh[1] && isNight() === false && state.me === 'My observer name'));

    // Ordinary refresh still restores writing; the pristine checkpoint must not
    // accidentally become that restored wall on the following page load.
    await page.evaluate(async () => {
      $('msg').value = '刷新后应保留的作品'; $('sig').value = '作者'; commit();
      await saveWorkspace(false);
    });
    await page.reload();
    await page.waitForFunction(() => workspaceReady);
    check('ordinary refresh still restores user writing', await page.evaluate(() =>
      state.scroll[0].text === '刷新后应保留的作品'));
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#reset-opening').click();
    check('reset after autosave restoration uses pristine startup checkpoint', await page.evaluate(() =>
      state.scroll.length === 1 && state.scroll[0].text === FIRST.zh[0]));

    page.once('dialog', dialog => dialog.accept());
    await page.locator('#clear-wall').click();
    check('existing clear-wall still keeps current text and signature', await page.evaluate(() =>
      !state.scroll.length && $('msg').value === FIRST.zh[0] && $('sig').value === FIRST.zh[1]));
    check('reset stays available on an empty wall', await page.locator('#reset-opening').isEnabled());
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#reset-opening').click();
    check('empty wall returns to opening', await page.evaluate(() => state.scroll.length === 1));
    await page.locator('#m-read').click();
    check('writer reset is hidden in reader mode', !(await page.locator('#reset-opening').isVisible()));
    await page.locator('#m-write').click();

    await page.setViewportSize({width: 390, height: 844});
    await page.locator('#reset-opening').scrollIntoViewIfNeeded();
    check('mobile reset fits within viewport', await page.locator('#reset-opening').evaluate(el => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.left >= 0 && r.right <= innerWidth
        && document.documentElement.scrollWidth <= innerWidth;
    }));
    await page.screenshot({path: 'output/playwright/reset-opening-mobile.png', fullPage: true});
    await page.setViewportSize({width: 1440, height: 1000});
    await page.evaluate(() => setTheme('dark'));
    await page.locator('#reset-opening').scrollIntoViewIfNeeded();
    await page.screenshot({path: 'output/playwright/reset-opening-desktop.png', fullPage: true});
    return {passed: checks.length, checks};
  } finally {
    await context.close();
  }
}
