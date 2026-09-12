/* Run with playwright-cli run-code (Get-Content -Raw this file) after opening
   the built page on a local server. All saved test data uses a new browser context. */
async page => {
  const checks = [];
  const check = (name, ok, detail) => {
    checks.push({ name, ok: !!ok, ...(detail === undefined ? {} : { detail }) });
    if (!ok) throw Error(name + (detail === undefined ? '' : ': ' + JSON.stringify(detail)));
  };
  // A separate in-memory browser context owns all test storage. Never touch the
  // user's saved wall, or the preview tab's existing IndexedDB data.
  const context = await page.context().browser().newContext({ viewport: { width: 1440, height: 1000 } });
  const work = await context.newPage();
  const origin = await page.evaluate(() => location.origin);
  const url = origin + '/web/nomai-scriptorium.html';
  const serial = value => JSON.stringify(value, (_, v) =>
    typeof v === 'bigint' ? { bigint: v.toString() }
      : v instanceof Map ? { map: [...v] }
      : v instanceof Set ? { set: [...v] } : v);
  const snapshot = async () => work.evaluate(source => {
    const serialize = eval('(' + source + ')');
    return serialize(captureWorkspace());
  }, serial.toString());
  const stored = async () => work.evaluate(async source => {
    const serialize = eval('(' + source + ')');
    const saved = await new Promise((resolve, reject) => {
      const request = workspaceDB.transaction('walls').objectStore('walls').get('current');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return serialize(saved);
  }, serial.toString());
  try {
    await work.goto(url);
    await work.waitForFunction(() => workspaceReady);
    await work.evaluate(async () => {
      setLang('en'); state.hw = 0; setSigned(false);
      state.aim = { kind: 'new', index: 0 };
      $('msg').value = 'Saved writer root'; commit();
      setAim('reply', 0, false); $('msg').value = 'Saved writer reply'; commit();
      setAim('edit', 0, false); $('msg').value = 'Root unfinished rewrite'; syncWrite();
      setAim('edit', 1, false); $('msg').value = 'Reply unfinished rewrite'; syncWrite();
      setAim('reply', 1, false); $('msg').value = 'Unfinished nested reply'; syncWrite();
      zoomWall(2);
      scheduleWorkspaceSave();
      if (!await saveWorkspace(false)) throw Error('Could not save regression fixture');
    });
    const baseline = await snapshot();
    check('fixture stores exact writer wall, multiple drafts and zoom', await stored() === baseline);

    const payload = { version: 1, where: 'Regression library location', lang: 'en',
      turns: [['Library entry remains visible', '', null]] };
    // Navigate through the repository, as the real action does. A same-path hash
    // change alone would not rerun the scriptorium's startup import handler.
    await work.goto(origin + '/web/nomai-repository.html');
    await work.goto(url + '#library-scroll=' + encodeURIComponent(JSON.stringify(payload)));
    await work.waitForFunction(() => workspaceReady && state.mode === 'read'
      && state.scrollSource === 'library' && !!state.pending);
    check('library import stays visible instead of being replaced by the saved wall',
      await work.evaluate(() => state.scroll[0].text === 'Library entry remains visible'
        && !!$('art').querySelector('g[data-spiral]') && !$('read-pane').hidden));
    check('library reader keeps the complete saved writer snapshot in the background', await snapshot() === baseline);
    check('opening a library scroll leaves the stored writer unchanged', await stored() === baseline);

    await work.locator('#m-write').click();
    check('switching back to writing restores exact SVG, grids, drafts, target and viewport', await snapshot() === baseline);
    await work.waitForFunction(() => !workspaceTimer && savedRevision === workspaceRevision);
    await work.evaluate(() => saveQueue);
    check('autosave after returning to writing preserves the original wall and drafts', await stored() === baseline);
    const draftTexts = await work.evaluate(() => {
      const current = $('msg').value;
      setAim('edit', 0, false); const root = $('msg').value;
      setAim('edit', 1, false); const reply = $('msg').value;
      setAim('reply', 1, false);
      return { current, root, reply, nested: $('msg').value };
    });
    check('each saved rewrite and reply draft can still be selected',
      draftTexts.current === 'Unfinished nested reply'
      && draftTexts.root === 'Root unfinished rewrite'
      && draftTexts.reply === 'Reply unfinished rewrite'
      && draftTexts.nested === 'Unfinished nested reply', draftTexts);

    const delayed = await work.evaluate(() => {
      const before = state.svg;
      // Select the normal debounce path deterministically; real long walls reach
      // it after a render takes more than 200 ms. No geometry result is stubbed.
      lastBuildMs = 300;
      const slider = $('tight'); slider.value = '0.5';
      slider.dispatchEvent(new Event('input', { bubbles: true }));
      const queuedBeforeSwitch = !!reshapeTimer;
      setMode('read');
      const s = captureWorkspace();
      return { queuedBeforeSwitch, pendingAfterSwitch: !!reshapeTimer,
        tight: s.settings.tight, renderedTight: s.placements[0].tight,
        changedSvg: s.svg !== before, svg: s.svg };
    });
    check('test reached the pending shape redraw before switching mode', delayed.queuedBeforeSwitch);
    check('switching to reading flushes pending geometry before taking the writer snapshot',
      !delayed.pendingAfterSwitch && delayed.tight === 0.5
      && delayed.renderedTight === 0.5 && delayed.changedSvg,
      { pending: delayed.pendingAfterSwitch, tight: delayed.tight,
        renderedTight: delayed.renderedTight, changedSvg: delayed.changedSvg });
    const shaped = await snapshot();
    await work.waitForFunction(() => !workspaceTimer && savedRevision === workspaceRevision);
    await work.evaluate(() => saveQueue);
    check('automatic save in reader mode stores the completed shape and matching settings', await stored() === shaped);
    await work.locator('#m-write').click();
    check('returning to writing preserves the finished shape and drafts exactly', await snapshot() === shaped);

    // Remove the import hash before refreshing to exercise ordinary writer restore.
    await work.evaluate(async () => { history.replaceState(null, '', location.pathname); await saveWorkspace(false); });
    await work.reload(); await work.waitForFunction(() => workspaceReady);
    check('refresh restores the latest geometry and all unfinished drafts exactly', await snapshot() === shaped);
    await page.evaluate(result => { window.libraryWorkspaceChecks = result; }, checks);
    return checks;
  } catch (error) {
    await page.evaluate(result => { window.libraryWorkspaceChecks = result; }, checks);
    throw error;
  } finally {
    await context.close();
  }
}
