/* Verify exact writer-wall restoration across read/write transitions.
   Run against a served web/nomai-scriptorium.html page with playwright-cli:
   $code = Get-Content -Raw -Encoding utf8 tools/check_writer_transitions.js
   playwright-cli -s=preview run-code $code
   A separate, temporary browser context protects the caller's saved wall. */
async caller => {
  const context = await caller.context().browser().newContext({
    viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce'
  });
  const checks = [];
  const check = (name, ok) => {
    checks.push({ name, ok: !!ok });
    if (!ok) throw Error(name);
  };
  try {
    const page = await context.newPage();
    await page.goto(caller.url().split('#')[0]);
    await page.waitForFunction(() => workspaceReady);
    await page.evaluate(() => {
      if (state.mode !== 'write') setMode('write');
      state.hw = 0;
      state.seed = 47;
      const words = [
        'We found a signal.', 'Where does it come from?',
        'Beyond the southern sky.', 'Let us build a new locator.',
        'I will calibrate it.', 'We can try again tomorrow.'
      ];
      state.scroll = words.map((text, i) => ({
        text, sig: '', parent: i ? i - 1 : null, base: 256, dialect: 'strict',
        grid: gridFor(text, '', i ? i - 1 : null, 'strict', 256)
      }));
      state.aim = { kind: 'edit', index: 0 };
      state.aimChosen = true;
      state.seen = new Set(words.map((_, i) => i));
      // A deliberate write gets more layout time than a shape-control redraw.
      state.layoutKey = null;
      build(true);
      setAim('edit', 3, false);
      zoomWall(2);
    });
    await page.locator('#msg').fill('Keep this unfinished transition draft');
    await page.evaluate(() => {
      window.transitionBefore = captureWorkspace();
      window.transitionPlain = value => JSON.stringify(value, (_, v) =>
        typeof v === 'bigint' ? String(v) : v instanceof Map ? [...v] : v);
    });
    await page.locator('#m-read').click();
    check('read icon enters reader without committing draft', await page.evaluate(() =>
      state.mode === 'read'
        && state.writerDraft.workspace.scroll[3].text !== 'Keep this unfinished transition draft'));
    await page.locator('#m-write').click();
    check('mode icon round trip preserves exact committed SVG', await page.evaluate(() =>
      state.svg === transitionBefore.svg));
    check('mode icon round trip preserves all placement parameters', await page.evaluate(() =>
      transitionPlain(captureWorkspace().placements) === transitionPlain(transitionBefore.placements)));
    check('mode icon round trip preserves viewport', await page.evaluate(() =>
      transitionPlain(editorView) === transitionPlain(transitionBefore.view)));
    check('mode icon round trip preserves grids and draft target', await page.evaluate(() =>
      transitionPlain(state.scroll) === transitionPlain(transitionBefore.scroll)
        && transitionPlain(state.aim) === transitionPlain(transitionBefore.aim)
        && $('msg').value === transitionBefore.composer.text));

    // A different reader scroll must not contaminate the saved writer wall.
    await page.locator('#m-read').click();
    await page.evaluate(() => {
      const grid = gridFor('A separate reading.', '', null, 'strict', 256);
      readDrawing(renderSVG(grid, 0, 47, 0, 1, .29), 'Separate reader scroll');
    });
    await page.locator('#m-write').click();
    check('reading another scroll still restores exact writer SVG and view', await page.evaluate(() =>
      state.svg === transitionBefore.svg
        && transitionPlain(editorView) === transitionPlain(transitionBefore.view)));

    // Move a costly shape slider, then switch modes before its debounce expires.
    await page.evaluate(() => {
      lastBuildMs = 300;
      state.tight = .34;
      $('tight').value = .34;
      reshape();
      window.transitionHadPendingReshape = !!reshapeTimer;
      setMode('read');
      window.transitionFlushed = state.writerDraft.workspace;
    });
    check('leaving writer flushes pending shape redraw before snapshot', await page.evaluate(() =>
      transitionHadPendingReshape && !reshapeTimer
        && transitionFlushed.settings.tight === .34
        && transitionFlushed.svg !== transitionBefore.svg));
    await page.locator('#m-write').click();
    check('return restores flushed shape exactly without second layout', await page.evaluate(() =>
      state.svg === transitionFlushed.svg
        && transitionPlain(captureWorkspace().placements) === transitionPlain(transitionFlushed.placements)
        && $('msg').value === 'Keep this unfinished transition draft'));
    return { passed: checks.filter(check => check.ok).length, total: checks.length, checks };
  } finally {
    await context.close();
  }
}
