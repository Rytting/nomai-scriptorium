/* Run in the built page with playwright-cli eval (read this file as its argument).
   Real SVG geometry is exported and re-read; no dialect metadata is supplied. */
() => {
  const checks = [];
  const check = (name, ok, detail) => {
    checks.push({ name, ok: !!ok, ...(ok ? {} : { detail }) });
  };
  const fingerprint = g => JSON.stringify({ glyphs: [...g.glyphs], paths: g.paths,
    conns: g.conns, x: String(g.x) });
  const write = (text, dialect, kind, index, base = 256) => {
    state.aim = { kind, index }; setDialectUI(dialect); setBaseUI(base);
    setSigned(false); $("msg").value = text; commit();
  };
  state.hw = 0;
  write("Hello", "strict", "new", 0);
  const root = state.scroll[0].grid, rootBefore = fingerprint(root);
  write("hi", "upstream", "reply", 0);
  check("original reply preserves strict root grid and integer",
    state.scroll[0].grid === root && fingerprint(root) === rootBefore);
  const original = state.scroll[1].grid, originalBefore = fingerprint(original);
  write("你好", "strict", "reply", 1);
  check("Chinese reply widens only its own alphabet",
    state.scroll.map(s => s.base).join() === "256,256,200000");
  check("strict reply preserves original parent",
    state.scroll[1].grid === original && fingerprint(original) === originalBefore);
  const mixedSVG = state.svg;
  const geometry = analyzeScroll(mixedSVG);
  const decoded = geometry.spirals.map(c => readSpiral(c));
  check("mixed SVG automatically detects each dialect",
    decoded.map(d => d.dialect).join() === "strict,upstream,strict",
    decoded.map(d => ({ dialect: d.dialect, texts: d.readings.map(r => r.text) })));
  check("mixed SVG detects each alphabet",
    decoded.map(d => d.base).join() === "256,256,200000");
  check("both kinds of replies survive SVG geometry round trip",
    decoded[0].readings.some(r => r.text === "Hello")
    && decoded[1].readings.some(r => r.text === "hi")
    && decoded[2].readings.some(r => r.text === "你好"));
  const tree = mixedTree(geometry.edges, decoded);
  check("mixed tree preserves nested parents", tree.ok && tree.parents.join() === ",0,1", tree);
  const child = state.scroll[2].grid;
  write("changed", "strict", "edit", 1);
  check("explicit rewrite changes only target grid",
    state.scroll[1].grid !== original && state.scroll[1].dialect === "strict"
    && state.scroll[0].grid === root && state.scroll[2].grid === child);
  setDialectUI("upstream"); setBaseUI(200000); build(false);
  check("draft mode and redraw cannot re-encode existing spirals",
    state.scroll[0].grid === root && state.scroll[2].grid === child
    && state.scroll[0].base === 256);
  setAim("edit", 0);
  check("rewrite restores target dialect and alphabet", state.dialect === "strict" && state.base === 256);
  const pure = analyzeScroll(state.svg);
  const pureDecoded = pure.spirals.map(c => readSpiral(c));
  check("all strict scroll still reads", pureDecoded.every(d => d.dialect === "strict")
    && mixedTree(pure.edges, pureDecoded).ok);
  const timed = readSpiral(geometry.spirals[1], -1);
  check("search timeout remains undetermined", timed.dialect === "unknown" && timed.slow);
  check("broken reply joins rejected", !mixedTree([], decoded).ok);
  const conflict = decoded.map(d => ({ ...d, readings: d.readings.map(r => ({ ...r })) }));
  conflict[2].readings[0].parent = 0;
  check("conflicting strict reply frame rejected", !mixedTree(geometry.edges, conflict).ok);
  write("hi", "upstream", "new", 0);
  const upstreamRoot = state.scroll[0].grid;
  write("Hello", "strict", "reply", 0);
  const reverse = analyzeScroll(state.svg), revDecoded = reverse.spirals.map(c => readSpiral(c));
  check("strict can answer an original root", state.scroll[0].grid === upstreamRoot
    && revDecoded.map(d => d.dialect).join() === "upstream,strict"
    && mixedTree(reverse.edges, revDecoded).ok);
  setMode("read"); readDrawing(mixedSVG, "mixed-dialects.svg");
  check("import keeps answerable mixed scroll", state.scroll.length === 3 && state.pending.tree.ok);
  const imported = state.scroll.map(s => s.grid), prints = imported.map(fingerprint);
  // Settle the candidates for this codec check; the separate UI check holds the
  // actual translator button and exercises its reading chooser.
  state.pending.per.forEach((list, i) => {
    state.pick[i] = Math.max(0, list.findIndex(r => r.text === ["Hello", "hi", "你好"][i]));
    state.scroll[i].text = list[state.pick[i]].text;
    state.seen.add(i);
  });
  paintThread(); paintTranslator();
  const originalLine = document.querySelector("#line .original-message");
  const strictLine = document.querySelector("#line .strict-message");
  check("mixed scroll labels only its original rows, in one bracket, in the common colour",
    originalLine && strictLine && originalLine.textContent.startsWith("[")
    && !strictLine.textContent.startsWith("[")
    && getComputedStyle(originalLine).color === getComputedStyle(strictLine).color
    && document.querySelectorAll("#thread .original-message").length === 1);
  /* A label distinguishes or it is noise. Two places it cannot distinguish: a scroll
     written entirely in one numbering, and the chooser, whose lines are all readings
     of the same spiral. */
  const wasChoosing = state.choosing;
  state.choosing = decoded.findIndex(d => d.dialect === "upstream");
  const chooser = chooseScreen();
  state.choosing = wasChoosing;
  check("the chooser never repeats the label", !/dialect-tag/.test(chooser));
  const wasScroll = state.scroll, wasPending = state.pending;
  state.scroll = wasScroll.filter(sp => sp.dialect === "upstream");
  state.pending = null;
  const blanket = mixedDialects();
  state.scroll = wasScroll; state.pending = wasPending;
  check("a scroll of one numbering carries no label at all", blanket === false);
  setAim("reply", 1); setDialectUI("strict"); $("msg").value = "Yes"; commit();
  check("reply to imported original preserves every existing grid",
    imported.every((g, i) => state.scroll[i].grid === g && fingerprint(g) === prints[i]));
  window.dialectTestSVG = mixedSVG;
  return { passed: checks.filter(c => c.ok).length, total: checks.length, checks };
}
