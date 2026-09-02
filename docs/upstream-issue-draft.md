# 给上游的话，草稿

**改版原因**：先前那版打算另开一个 issue 讲歧义 bug。重读上游之后改了主意。

查到的事实（`gh` 拉的，2026-09-02）：

* 上游 **2025-12-31 之后没再推过**，HEAD 仍是 `b8ca259`。我们那六条断言对当前代码依然成立。
* **issue #2「[Suggestions] - decode feature / branch generation」问的正是我们做的这两件事**，
  作者回过，另有两个人（Nixie-Cull、xxfast）在里面出主意、提出想帮忙实现分支。
* issue #3 也问了解码，作者答：从图像完整解码「不在我的清单上，而且以 NomaiText 的
  底层实现来说会非常难」。
* 作者在 #2 里明说：正在育儿假，之后带孩子加本职工作，中期内没精力做深度开发；
  **"You're more than welcome to fork it, of course, I'd love to see where you take it."**
* 同一段里还说：**"this is a purely passion project... I just want to build
  NomaiText.jl by hand"**，并把这条列为"你可能更想 fork"的理由之一。
  他补了一句他不反对 AI 本身，只是不想用在这个项目上。

**由此定下三条：**

1. **不提 PR。** 他说了想手工建这个项目。递代码是没听懂话。
2. **fork 是他明确邀请的**，所以把我们做出来的东西说给他听不算自我推销，是他要的。
3. **主动说明用了 AI。** 不是道歉——他并不反对——而是不让人事后才发现。

**发在哪**：issue #2 底下回一帖。歧义那份完整写法留着，帖里提一句，
他要就另开 issue 给他，不主动塞。

**链接已就位**（2026-09-02）：
仓库 https://github.com/Rytting/nomai-scriptorium （公开，MIT，附上游版权声明）
页面 https://rytting.github.io/nomai-scriptorium/ （GitHub Pages，已实测可写可读）

**还没发。** 发到公开 issue 是挂你名字的对外动作，等你读过草稿点头。

---

## 拟发内容（issue #2 的评论）

Hi @evanfields — you said above that you'd love to see where a fork went, so: here's
where one went. Also @Nixie-Cull @xxfast, since this is the thread you were in.

Up front, so nobody finds out later and feels misled: **I built this with heavy AI
assistance.** I saw your note that NomaiText.jl is a passion project you want to build
by hand, and I've kept well clear of your repo — nothing here is a patch or a PR, and
I'm not asking you for anything. It's a separate thing that borrows your alphabet and
your spiral, credited and under your MIT licence.

### Decoding from the image works

You wrote that this would be "very tricky, but hypothetically possible if we resolve
point 5". It turned out point 5 wasn't the obstacle, and it isn't necessary to resolve
it — though what *is* going on is worth knowing, and I'll come to that.

There's no machine learning in it. An SVG is vector data, not pixels, and three
properties of `draw` make it a parsing-and-geometry problem rather than a recognition
one:

* `handwrite` moves shared points through a single `point_map`, so the strokes of a
  glyph — and the two ends of a connection — carry *bit-identical* coordinates.
  Clustering needs no tolerance at all.
* the SVG preserves vertex order, so matching a stroke to a canonical `PolySpec` is an
  ordered Procrustes fit in closed form, not unordered point-set matching.
* connections only ever join column *i* to column *i+1*, so the connection graph is
  layered and a BFS from the innermost glyph recovers the column index exactly.

Given the grid back, decoding is exact inversion rather than search: at each step the
*k* of `ask!(o, k)` is determined by the structure already recovered, so the answers
can be replayed and the mixed-radix accumulation `X = Σ (aᵢ−1)·Mᵢ` run forwards.

Measured on 60 spirals from nomai-writing.com: **52/60 recovered exactly** (glyphs,
rows and connections all correct). It degrades with handwriting — reliable to about
0.3, and the site's default is 0.4, which is right at the edge.

### But your drawings are genuinely ambiguous, and item 5 is not the main reason

This is the part that might be worth your time even if you never touch the code again.

A drawing does not determine its message, and the dominant cause is not the
`Oracle` wrap-around of item 5. It's the `sort!` in `next!`. Two row questions are
asked and their answers are then sorted, which throws away *which* was asked first.
There's a second, smaller leak: `allpoints` builds annotations from core vertices, so
duplicate points make some connection-pair questions carry fewer distinct outcomes
than the count passed to `ask!`.

Concretely, at base 256:

* `"hi"` and `"&i"` render byte-identically.
* `"Curious Archaeology"` — 19 characters — has **184 distinct integers** producing
  the same drawing. I enumerated them and confirmed all 184 in Julia against
  `b8ca259`.

Of those 184, the large majority come from the `sort!`, not from wrap-around.

I have a write-up with a runnable Julia reproduction for each claim (six of them,
all passing against `b8ca259`). Happy to open it as its own issue if that's useful to
you, or to leave it alone — your call, and no hurry.

There's a way to close all three leaks without changing which drawings are possible:
ask one joint question over the sorted pair instead of two, deduplicate the tied
connection pairs, and frame the record with its length. The set of producible drawings
is unchanged; only the message→drawing map differs, and it becomes injective. On that
numbering, decoding is a linear replay with no search and no language prior, and
600/600 test messages round-tripped uniquely.

### Branching works too

You called this "the clear missing feature", and I agree — it's most of what makes a
Nomai wall feel like a Nomai wall.

A conversation is one drawing: a root spiral plugged into a socket at the bottom of
the panel, with replies growing off whichever spiral they answer, placed automatically
and joined by a line with a bead at its midpoint. The bead is the whole trick for
reading them back — nothing else in a drawing puts a dot in the middle of a two-point
stroke, so cutting the beaded lines separates the spirals cleanly and the ordinary
reader then runs on each one unchanged.

@Nixie-Cull — your pin-and-callback idea is close to what this does, but it turned out
the position doesn't need encoding at all. A reply is drawn attached to its parent, so
where it sits is already visible; what each reply records is just *which* spiral it
answers, and that's used to check the tree the geometry gives rather than to supply
it. Layout picks the spot: it tries places along the parent, both sides, and both
windings, and takes the first that clears everything already on the sheet.

Replies also vary their coil and handedness, since a real wall has them curling both
ways.

### What it is and isn't

* Reading a drawing made by *your* numbering gives ranked candidates, not an answer —
  that's the ambiguity above, and it's a property of the drawing, not a weakness of
  the reader. On the modified numbering there is exactly one reading.
* Works in the browser with no server: write, render, read, translate.
* Reference implementation in Python, including scrolls, plus a JS port for the page.
  `python tools/check_scroll.py` writes four conversation shapes across both windings
  and three tightnesses and reads them back: 21 of 24, the three failures being the
  same per-drawing limits the single-spiral reader has.
* Known limits: a few drawings still fail to read at one winding — the page warns you
  when it has made one of those, since it can tell — and heavy handwriting degrades it.

Thanks for building the thing in the first place — the alphabet and the spiral are
yours, and none of this would exist without them. Enjoy the leave.

---

* Try it: **https://rytting.github.io/nomai-scriptorium/** — no server, nothing leaves
  the page.
* Code: **https://github.com/Rytting/nomai-scriptorium** — MIT, with your notice
  reproduced. Python reference implementation, a JS port for the page, and the working
  log including the measurements above and the several things that did not work.
