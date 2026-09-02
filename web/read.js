/* Reading a drawing back.

   A faithful port of src/nomai/vision.py plus the strict half of decode.py. Nothing
   here is machine learning: the SVG is vector data, so recovering the grid is
   parsing plus closed-form geometry. Three properties of the drawing carry it:
   a glyph's strokes share exact coordinates with each other and with the ends of
   the connections that attach to them; the SVG preserves vertex order, so matching
   a stroke to a canonical shape is an ordered fit; and connections only ever run
   between consecutive columns, which makes the connection graph layered.

   The Python is the reference implementation and is tested far more thoroughly.
   Keep the two in step. */

/* ---------- similarity fitting ---------- */
function procrustes(src, dst){
  const n = src.length;
  if (!n || dst.length !== n) return null;
  let ax = 0, ay = 0, bx = 0, by = 0;
  for (let i = 0; i < n; i++){ ax += src[i][0]; ay += src[i][1]; bx += dst[i][0]; by += dst[i][1]; }
  ax /= n; ay /= n; bx /= n; by /= n;
  let den = 0, wr = 0, wi = 0;
  for (let i = 0; i < n; i++){
    const px = src[i][0] - ax, py = src[i][1] - ay;
    const qx = dst[i][0] - bx, qy = dst[i][1] - by;
    den += px * px + py * py;
    wr += qx * px + qy * py;
    wi += qy * px - qx * py;
  }
  if (den === 0) return null;
  wr /= den; wi /= den;
  let s = 0;
  for (let i = 0; i < n; i++){
    const px = src[i][0] - ax, py = src[i][1] - ay;
    const qx = dst[i][0] - bx, qy = dst[i][1] - by;
    const rx = wr * px - wi * py, ry = wr * py + wi * px;
    s += (qx - rx) * (qx - rx) + (qy - ry) * (qy - ry);
  }
  return { wr, wi, scale: Math.hypot(wr, wi), theta: Math.atan2(wi, wr),
           resid: Math.sqrt(s / n),
           tx: bx - (wr * ax - wi * ay), ty: by - (wr * ay + wi * ax) };
}
/* residual of src -> dst under a given rotation+scale, translation free */
function residFixed(wr, wi, src, dst){
  const n = src.length;
  let ax = 0, ay = 0, bx = 0, by = 0;
  for (let i = 0; i < n; i++){ ax += src[i][0]; ay += src[i][1]; bx += dst[i][0]; by += dst[i][1]; }
  ax /= n; ay /= n; bx /= n; by /= n;
  let s = 0;
  for (let i = 0; i < n; i++){
    const px = src[i][0] - ax, py = src[i][1] - ay;
    const qx = dst[i][0] - bx, qy = dst[i][1] - by;
    const rx = wr * px - wi * py, ry = wr * py + wi * px;
    s += (qx - rx) * (qx - rx) + (qy - ry) * (qy - ry);
  }
  return Math.sqrt(s / n);
}
/* one similarity across several point sets, each free to shift on its own --
   handwrite draws its jitter translation once per stroke, not once per glyph */
function jointSimilarity(parts){
  const src = [], dst = [];
  for (const [canon, obs] of parts){
    const n = canon.length;
    let ax = 0, ay = 0, bx = 0, by = 0;
    for (let i = 0; i < n; i++){ ax += canon[i][0]; ay += canon[i][1]; bx += obs[i][0]; by += obs[i][1]; }
    ax /= n; ay /= n; bx /= n; by /= n;
    for (let i = 0; i < n; i++){
      src.push([canon[i][0] - ax, canon[i][1] - ay]);
      dst.push([obs[i][0] - bx, obs[i][1] - by]);
    }
  }
  let den = 0, wr = 0, wi = 0;
  for (let i = 0; i < src.length; i++){
    den += src[i][0] ** 2 + src[i][1] ** 2;
    wr += dst[i][0] * src[i][0] + dst[i][1] * src[i][1];
    wi += dst[i][1] * src[i][0] - dst[i][0] * src[i][1];
  }
  if (den === 0) return null;
  wr /= den; wi /= den;
  let s = 0;
  for (let i = 0; i < src.length; i++){
    const rx = wr * src[i][0] - wi * src[i][1], ry = wr * src[i][1] + wi * src[i][0];
    s += (dst[i][0] - rx) ** 2 + (dst[i][1] - ry) ** 2;
  }
  return { wr, wi, resid: Math.sqrt(s / src.length) };
}

/* ---------- the canonical alphabet, indexed by stroke pattern ---------- */
const PARTS = G.glyphs.map(g => g.a ? [[g.c, !!g.cc], [g.a, !!g.ac]] : [[g.c, !!g.cc]]);
const SIG = PARTS.map(ps => ps.map(([p, c]) => len2(p) + ":" + (c ? 1 : 0)).sort().join("|"));
function len2(a){ return a.length; }
function sigOf(strokes){
  return strokes.map(s => s.pts.length + ":" + (s.closed ? 1 : 0)).sort().join("|");
}
/* only two body shapes in the alphabet can carry a spike at all */
const SPIKE_TABLE = (() => {
  const t = new Map();
  PARTS.forEach((ps, i) => {
    const sp = ps.filter(([p, c]) => p.length === 2 && !c);
    if (!sp.length) return;
    const body = ps.filter(([p, c]) => !(p.length === 2 && !c));
    const key = body.map(([p, c]) => p.length + ":" + (c ? 1 : 0)).sort().join("|");
    if (!t.has(key)) t.set(key, []);
    t.get(key).push([body[0], sp[0][0]]);
  });
  return t;
})();

const rolls = (pts, closed) => {
  if (!closed) return [pts];
  const out = [];
  for (let r = 0; r < pts.length; r++) out.push(pts.slice(r).concat(pts.slice(0, r)));
  return out;
};

function spikeResidual(bodyStrokes, stroke){
  const cands = SPIKE_TABLE.get(sigOf(bodyStrokes));
  if (!cands) return Infinity;
  let best = Infinity;
  for (const [[corePts, coreClosed], spikePts] of cands){
    for (const bs of bodyStrokes){
      if (bs.pts.length !== corePts.length || bs.closed !== coreClosed) continue;
      for (const rolled of rolls(corePts, coreClosed)){
        for (const pts of [stroke.pts, stroke.pts.slice().reverse()]){
          const fit = jointSimilarity([[rolled, bs.pts], [spikePts, pts]]);
          if (fit && fit.resid < best) best = fit.resid;
        }
      }
    }
  }
  return best;
}

/* ---------- SVG in ---------- */
function parseSVG(text){
  const strokes = [];
  const re = /<path([^>]*)>/g;
  let m;
  while ((m = re.exec(text)) !== null){
    const attrs = m[1];
    const d = /[\s;"]d="([^"]*)"/.exec(attrs);
    if (!d) continue;
    const body = d[1];
    const pts = [];
    const cre = /([MLC])((?:\s+-?[\d.]+){2,6})/g;
    let c;
    while ((c = cre.exec(body)) !== null){
      const nums = c[2].trim().split(/\s+/).map(Number);
      for (let i = 0; i + 1 < nums.length; i += 2) pts.push([nums[i], nums[i + 1]]);
    }
    if (!pts.length) continue;
    if (!/stroke-width/.test(attrs)) continue;  /* a filled vertex dot */
    let closed = /[Zz]/.test(body);
    let p = pts;
    if (closed && p.length > 1 &&
        Math.abs(p[0][0] - p[p.length - 1][0]) < 1e-6 &&
        Math.abs(p[0][1] - p[p.length - 1][1]) < 1e-6) p = p.slice(0, -1);
    strokes.push({ pts: p, closed });
  }
  return strokes;
}

/* ---------- clustering, and telling spikes from connections ---------- */
class DSU {
  constructor(n){ this.p = [...Array(n).keys()]; }
  find(i){ while (this.p[i] !== i){ this.p[i] = this.p[this.p[i]]; i = this.p[i]; } return i; }
  union(i, j){ this.p[this.find(i)] = this.find(j); }
}
const pkey = p => p[0] + "," + p[1];

function bfs(adj, src){
  const dist = new Map([[src, 0]]);
  const q = [src];
  while (q.length){
    const u = q.shift();
    for (const v of (adj.get(u) || [])) if (!dist.has(v)){ dist.set(v, dist.get(u) + 1); q.push(v); }
  }
  return dist;
}
function layeringFrom(conns, keys, root){
  const adj = new Map();
  for (const c of conns){
    if (c.ka === c.kb) return null;
    if (!adj.has(c.ka)) adj.set(c.ka, new Set());
    if (!adj.has(c.kb)) adj.set(c.kb, new Set());
    adj.get(c.ka).add(c.kb); adj.get(c.kb).add(c.ka);
  }
  const dist = bfs(adj, root);
  if (dist.size !== keys.length) return null;
  const cols = new Map();
  for (const [k, v] of dist) cols.set(k, v + 1);
  const n = Math.max(...cols.values());
  const sizes = Array(n).fill(0);
  for (const v of cols.values()) sizes[v - 1]++;
  if (sizes[0] !== 1 || Math.max(...sizes) > 2) return null;
  for (const c of conns) if (Math.abs(cols.get(c.ka) - cols.get(c.kb)) !== 1) return null;
  return cols;
}

function decompose(strokes){
  const two = [], body = [];
  strokes.forEach((s, i) => (s.pts.length === 2 ? two : body).push(i));
  const owner = new Map();
  for (const i of body) for (const p of strokes[i].pts){
    const k = pkey(p);
    if (!owner.has(k)) owner.set(k, []);
    owner.get(k).push(i);
  }
  const dsu = new DSU(strokes.length);
  for (const idxs of owner.values()) for (let j = 1; j < idxs.length; j++) dsu.union(idxs[0], idxs[j]);

  const base = new Map();
  for (const i of body){
    const r = dsu.find(i);
    if (!base.has(r)) base.set(r, []);
    base.get(r).push(strokes[i]);
  }
  const keys = [...base.keys()];
  const cent = new Map();
  for (const [k, ss] of base){
    let x = 0, y = 0, n = 0;
    for (const s of ss) for (const p of s.pts){ x += p[0]; y += p[1]; n++; }
    cent.set(k, [x / n, y / n]);
  }
  const home = new Map();
  for (const i of body) for (const p of strokes[i].pts) home.set(pkey(p), dsu.find(i));
  const nearest = p => keys.reduce((best, k) => {
    const d = (cent.get(k)[0] - p[0]) ** 2 + (cent.get(k)[1] - p[1]) ** 2;
    return best === null || d < best[1] ? [k, d] : best;
  }, null)[0];

  /* rank every plausible (stroke, host) pairing by how well it fits as that glyph's
     spike. Measurement says the residuals of spikes and connections overlap, so no
     cutoff separates them -- but the ranking is right, and the drawing itself
     supplies how many to take: one too few leaves a connection end nobody owns, one
     too many steals a connection and the graph stops layering. */
  const ranked = [];
  for (const i of two){
    const hosts = new Set();
    for (const p of strokes[i].pts){ const h = home.get(pkey(p)); if (h !== undefined) hosts.add(h); }
    for (const h of hosts){
      const r = spikeResidual(base.get(h), strokes[i]);
      if (r < Infinity) ranked.push([r, i, h]);
    }
  }
  ranked.sort((a, b) => a[0] - b[0]);
  const chain = [], usedS = new Set(), usedH = new Set();
  for (const [, i, h] of ranked){
    if (usedS.has(i) || usedH.has(h)) continue;
    chain.push([i, h]); usedS.add(i); usedH.add(h);
  }
  const canonical = new Set(SIG);

  function build(nSpikes){
    const cl = new Map();
    for (const [k, ss] of base) cl.set(k, ss.slice());
    const spiked = new Set();
    for (let i = 0; i < nSpikes; i++){
      cl.get(chain[i][1]).push(strokes[chain[i][0]]);
      spiked.add(chain[i][0]);
    }
    for (const ss of cl.values()) if (!canonical.has(sigOf(ss))) return null;
    const owned = new Map();
    for (const [k, ss] of cl) for (const s of ss) for (const p of s.pts) owned.set(pkey(p), k);
    const conns = [];
    for (const i of two){
      if (spiked.has(i)) continue;
      const [a, b] = strokes[i].pts;
      const ka = owned.get(pkey(a)), kb = owned.get(pkey(b));
      if (ka === undefined || kb === undefined) return null;
      conns.push({ ka, pa: a, kb, pb: b });
    }
    return { clusters: cl, conns };
  }
  for (let n = 0; n <= chain.length; n++){
    const got = build(n);
    if (!got) continue;
    const ks = [...got.clusters.keys()];
    for (const root of ks) if (layeringFrom(got.conns, ks, root)) return got;
  }
  const fallback = new Map();
  for (const [k, ss] of base) fallback.set(k, ss.slice());
  const owned = new Map();
  for (const [k, ss] of fallback) for (const s of ss) for (const p of s.pts) owned.set(pkey(p), k);
  return { clusters: fallback, conns: two.map(i => {
    const [a, b] = strokes[i].pts;
    return { ka: owned.get(pkey(a)) ?? nearest(a), pa: a,
             kb: owned.get(pkey(b)) ?? nearest(b), pb: b };
  }) };
}

/* ---------- fitting a cluster to a glyph ---------- */
const perms = n => n === 1 ? [[0]] : n === 2 ? [[0, 1], [1, 0]] : [[0]];
function assignments(strokes, parts){
  if (strokes.length !== parts.length) return [];
  return perms(parts.length).filter(pm => pm.every((_, i) =>
    strokes[pm[i]].pts.length === parts[i][0].length && strokes[pm[i]].closed === parts[i][1]));
}
function fitCluster(strokes){
  const out = [];
  const sig = sigOf(strokes);
  for (let gid = 1; gid <= PARTS.length; gid++){
    if (SIG[gid - 1] !== sig) continue;
    const parts = PARTS[gid - 1];
    for (const pm of assignments(strokes, parts)){
      const [corePts, coreClosed] = parts[0];
      for (let r = 0; r < (coreClosed ? corePts.length : 1); r++){
        const rolled = corePts.slice(r).concat(corePts.slice(0, r));
        const fit = procrustes(rolled, strokes[pm[0]].pts);
        if (!fit) continue;
        let total = fit.resid;
        const rots = [r];
        for (let pi = 1; pi < parts.length; pi++){
          const [pts, closed] = parts[pi];
          let bestR = 0, bestV = Infinity;
          for (let rr = 0; rr < (closed ? pts.length : 1); rr++){
            const v = residFixed(fit.wr, fit.wi, pts.slice(rr).concat(pts.slice(0, rr)),
                                 strokes[pm[pi]].pts);
            if (v < bestV){ bestV = v; bestR = rr; }
          }
          rots.push(bestR); total += bestV;
        }
        out.push({ resid: total, gid, scale: fit.scale, theta: fit.theta,
                   perm: pm, rots, origin: [fit.tx, fit.ty] });
      }
    }
  }
  out.sort((a, b) => a.resid - b.resid);
  return out;
}
/* with the placement already known, the only thing left to decide is which glyph */
function identify(strokes, wr, wi){
  let best = null;
  const sig = sigOf(strokes);
  for (let gid = 1; gid <= PARTS.length; gid++){
    if (SIG[gid - 1] !== sig) continue;
    const parts = PARTS[gid - 1];
    for (const pm of assignments(strokes, parts)){
      const ranges = parts.map(([p, c]) => c ? p.length : 1);
      const idx = parts.map(() => 0);
      const walk = d => {
        if (d === parts.length){
          let total = 0;
          for (let pi = 0; pi < parts.length; pi++){
            const [pts] = parts[pi], r = idx[pi];
            total += residFixed(wr, wi, pts.slice(r).concat(pts.slice(0, r)), strokes[pm[pi]].pts);
          }
          if (!best || total < best.resid) best = { resid: total, gid, perm: pm, rots: idx.slice() };
          return;
        }
        for (let r = 0; r < ranges[d]; r++){ idx[d] = r; walk(d + 1); }
      };
      walk(0);
    }
  }
  return best;
}
function vertexMap(strokes, fit){
  const parts = PARTS[fit.gid - 1];
  const out = new Map();
  let base = 0;
  for (let pi = 0; pi < parts.length; pi++){
    const [pts] = parts[pi], r = fit.rots[pi];
    const order = [];
    for (let i = r; i < pts.length; i++) order.push(i);
    for (let i = 0; i < r; i++) order.push(i);
    const obs = strokes[fit.perm[pi]].pts;
    order.forEach((canonIdx, slot) => {
      const k = pkey(obs[slot]);
      if (!out.has(k)) out.set(k, base + canonIdx);
    });
    base += pts.length;
  }
  return out;
}

/* ---------- rotations, rows, and the global layout ---------- */
const angdiff = (a, b) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));

function solveRotations(columns, centers, fits, ncols){
  const members = i => [...columns.keys()].filter(k => columns.get(k) === i);
  const options = new Map();
  for (let i = 1; i <= ncols; i++){
    const ms = members(i);
    let angles;
    if (ms.length === 2){
      const a = centers.get(ms[0]), b = centers.get(ms[1]);
      const base = Math.atan2(-(b[0] - a[0]), b[1] - a[1]);
      angles = [base, base + Math.PI];
    } else {
      angles = [];
      const cands = fits.get(ms[0]);
      for (const f of cands)
        if (f.resid <= cands[0].resid + 1 && angles.every(a => angdiff(f.theta, a) > 0.02))
          angles.push(f.theta);
    }
    if (!angles.length) angles = [0];
    options.set(i, angles.map(a => {
      let cost = 0;
      for (const k of ms){
        const cands = fits.get(k);
        let m = Infinity;
        for (const f of cands)
          if (f.resid <= cands[0].resid + 1) m = Math.min(m, f.resid + 2 * angdiff(f.theta, a));
        cost += m;
      }
      return [a, cost];
    }));
  }
  /* the spiral's tangent turns gradually, so pick the sequence by shortest path,
     trading fit residual against how sharply the angle would have to turn, and
     accumulate unwrapped -- interpolating wrapped angles puts the midpoint of 176
     and -145 degrees at 16 instead of 196 */
  let best = new Map();
  for (const [a, c] of options.get(1)) best.set(a, { cost: c, prev: null, un: a });
  const trace = [];
  for (let i = 2; i <= ncols; i++){
    const nxt = new Map();
    for (const [a, c] of options.get(i)){
      for (const [pa, st] of best){
        const d = Math.atan2(Math.sin(a - st.un), Math.cos(a - st.un));
        const total = st.cost + c + 3 * Math.abs(d);
        if (!nxt.has(a) || total < nxt.get(a).cost)
          nxt.set(a, { cost: total, prev: pa, un: st.un + d });
      }
    }
    trace.push(nxt); best = nxt;
  }
  const chain = new Map();
  let cur = [...best.keys()].reduce((x, y) => best.get(y).cost < best.get(x).cost ? y : x);
  for (let i = ncols; i > 1; i--){ chain.set(i, trace[i - 2].get(cur).un); cur = trace[i - 2].get(cur).prev; }
  chain.set(1, cur);
  return chain;
}

function globalPlacement(columns, rows, centers, ncols){
  const L = layoutFor(ncols);
  const keys = [...columns.keys()].filter(k => rows.has(k));
  if (keys.length < 3) return null;
  const pred = keys.map(k => L.place(columns.get(k), rows.get(k))([0, 0]));
  const fit = procrustes(pred, keys.map(k => centers.get(k)));
  if (!fit) return null;
  const predict = (i, j) => {
    const z = L.place(i, j)([0, 0]);
    return [fit.wr * z[0] - fit.wi * z[1] + fit.tx, fit.wr * z[1] + fit.wi * z[0] + fit.ty];
  };
  const wmap = new Map();
  for (const k of keys){
    const kk = L.fraction(columns.get(k)), sl = L.slopeAt(kk), s = (2 - 1) * kk + 1;
    const cr = Math.cos(sl) * s, ci = Math.sin(sl) * s;
    wmap.set(k, [fit.wr * cr - fit.wi * ci, fit.wr * ci + fit.wi * cr]);
  }
  return { predict, wmap, resid: fit.resid,
           fit: { wr: fit.wr, wi: fit.wi, tx: fit.tx, ty: fit.ty } };
}

const rowStates = (n, dj) => n === 1 ? [[1, 1], [2, 2], [3, 3]]
  : dj >= 2 ? [[1, ROWS]] : [[1, 2], [2, 3]];
const reachable = (prev, cur) =>
  (jChoices(prev[0]).includes(cur[0]) && jChoices(prev[1]).includes(cur[1])) ||
  (jChoices(prev[0]).includes(cur[1]) && jChoices(prev[1]).includes(cur[0]));

function assignRows(columns, centers, thetas, ncols){
  const delta = ncols > 1 ? 1 / (ncols - 1) : 0;
  const perCol = new Map(), gaps = new Map(), us = new Map();
  for (let i = 1; i <= ncols; i++){
    gaps.set(i, 3 * K * (1 + (i - 1) * delta));
    us.set(i, [-Math.sin(thetas.get(i)), Math.cos(thetas.get(i))]);
    const ms = [...columns.keys()].filter(k => columns.get(k) === i);
    const u = us.get(i);
    ms.sort((a, b) => (centers.get(a)[0] * u[0] + centers.get(a)[1] * u[1])
                    - (centers.get(b)[0] * u[0] + centers.get(b)[1] * u[1]));
    perCol.set(i, ms);
  }
  const states = new Map([[1, [[MIDLINE, MIDLINE]]]]);
  for (let i = 2; i <= ncols; i++){
    const ms = perCol.get(i);
    let dj = 0;
    if (ms.length === 2){
      const u = us.get(i), lo = centers.get(ms[0]), hi = centers.get(ms[1]);
      dj = Math.max(1, Math.round(((hi[0] - lo[0]) * u[0] + (hi[1] - lo[1]) * u[1]) / gaps.get(i)));
    }
    states.set(i, rowStates(ms.length, dj));
  }
  const bl = (i, j) => {
    const c = centers.get(perCol.get(i)[0]), u = us.get(i), d = (j - ROWS) * gaps.get(i);
    return [c[0] - d * u[0], c[1] - d * u[1]];
  };
  /* the bottom line is the spiral, so between columns it advances essentially along
     the tangent; a row guessed wrong displaces it by a whole row gap sideways */
  const step = (i, prev, cur) => {
    const p0 = bl(i - 1, prev[0]), p1 = bl(i, cur[0]);
    const sx = (Math.sin(thetas.get(i - 1)) + Math.sin(thetas.get(i))) / 2;
    const cy = (Math.cos(thetas.get(i - 1)) + Math.cos(thetas.get(i))) / 2;
    const nrm = Math.hypot(sx, cy) || 1;
    return Math.abs((p1[0] - p0[0]) * (-sx / nrm) + (p1[1] - p0[1]) * (cy / nrm)) / gaps.get(i);
  };
  let best = new Map([[JSON.stringify(states.get(1)[0]), { cost: 0, prev: null, st: states.get(1)[0] }]]);
  const trace = [];
  for (let i = 2; i <= ncols; i++){
    const nxt = new Map();
    for (const st of best.values()) for (const cur of states.get(i)){
      if (!reachable(st.st, cur)) continue;
      const key = JSON.stringify(cur), total = st.cost + step(i, st.st, cur);
      if (!nxt.has(key) || total < nxt.get(key).cost)
        nxt.set(key, { cost: total, prev: JSON.stringify(st.st), st: cur });
    }
    if (!nxt.size) throw new Error("no row assignment survives at column " + i);
    trace.push(nxt); best = nxt;
  }
  const chain = new Map();
  let cur = [...best.keys()].reduce((x, y) => best.get(y).cost < best.get(x).cost ? y : x);
  for (let i = ncols; i > 1; i--){ chain.set(i, trace[i - 2].get(cur).st); cur = trace[i - 2].get(cur).prev; }
  chain.set(1, states.get(1)[0]);
  const rows = new Map();
  for (let i = 1; i <= ncols; i++){
    const ms = perCol.get(i), [lo, hi] = chain.get(i);
    rows.set(ms[0], lo); rows.set(ms[ms.length - 1], hi);
  }
  return { rows, perCol };
}

/* re-decide rows against the fitted layout: a wrong row lands a full gap away from
   where the layout predicts, which is a far louder signal than the local cost */
function refineRows(columns, rows, centers, ncols, passes){
  passes = passes || 3;
  const perCol = new Map();
  for (let i = 1; i <= ncols; i++)
    perCol.set(i, [...columns.keys()].filter(k => columns.get(k) === i));
  for (let pass = 0; pass < passes; pass++){
    const placed = globalPlacement(columns, rows, centers, ncols);
    if (!placed) return rows;
    const states = new Map([[1, [[MIDLINE, MIDLINE]]]]);
    for (let i = 2; i <= ncols; i++)
      states.set(i, perCol.get(i).length === 2 ? [[1, 2], [2, 3], [1, ROWS]]
                                              : [[1, 1], [2, 2], [3, 3]]);
    const cost = (i, st) => {
      const ms = perCol.get(i);
      if (ms.length === 1) return dist(centers.get(ms[0]), placed.predict(i, st[0]));
      return Math.min(
        dist(centers.get(ms[0]), placed.predict(i, st[0])) + dist(centers.get(ms[1]), placed.predict(i, st[1])),
        dist(centers.get(ms[1]), placed.predict(i, st[0])) + dist(centers.get(ms[0]), placed.predict(i, st[1])));
    };
    let best = new Map([[JSON.stringify(states.get(1)[0]),
      { cost: cost(1, states.get(1)[0]), prev: null, st: states.get(1)[0] }]]);
    const trace = [];
    let dead = false;
    for (let i = 2; i <= ncols; i++){
      const nxt = new Map();
      for (const st of best.values()) for (const cur of states.get(i)){
        if (!reachable(st.st, cur)) continue;
        const key = JSON.stringify(cur), total = st.cost + cost(i, cur);
        if (!nxt.has(key) || total < nxt.get(key).cost)
          nxt.set(key, { cost: total, prev: JSON.stringify(st.st), st: cur });
      }
      if (!nxt.size){ dead = true; break; }
      trace.push(nxt); best = nxt;
    }
    if (dead) return rows;
    const chain = new Map();
    let cur = [...best.keys()].reduce((x, y) => best.get(y).cost < best.get(x).cost ? y : x);
    for (let i = ncols; i > 1; i--){ chain.set(i, trace[i - 2].get(cur).st); cur = trace[i - 2].get(cur).prev; }
    chain.set(1, states.get(1)[0]);
    const next = new Map();
    for (let i = 1; i <= ncols; i++){
      const ms = perCol.get(i), [lo, hi] = chain.get(i);
      if (ms.length === 1){ next.set(ms[0], lo); continue; }
      const straight = dist(centers.get(ms[0]), placed.predict(i, lo)) + dist(centers.get(ms[1]), placed.predict(i, hi));
      const swapped = dist(centers.get(ms[0]), placed.predict(i, hi)) + dist(centers.get(ms[1]), placed.predict(i, lo));
      const [a, b] = straight <= swapped ? [lo, hi] : [hi, lo];
      next.set(ms[0], a); next.set(ms[1], b);
    }
    let same = next.size === rows.size;
    if (same) for (const [k, v] of next) if (rows.get(k) !== v){ same = false; break; }
    if (same) return rows;
    rows = next;
  }
  return rows;
}
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

/* ---------- the whole thing ---------- */
function analyze(svgText){
  const strokes = parseSVG(svgText);
  if (strokes.length < 2) throw new Error("no Nomai strokes found in that file");
  const { clusters, conns } = decompose(strokes);
  const fits = new Map();
  for (const [k, ss] of clusters){
    const f = fitCluster(ss);
    if (!f.length) throw new Error("a shape in this drawing matches no known glyph");
    fits.set(k, f);
  }
  const keys = [...clusters.keys()].sort((a, b) => fits.get(a)[0].scale - fits.get(b)[0].scale);
  let columns = null;
  for (const root of keys){
    const cand = layeringFrom(conns, keys, root);
    if (cand){ columns = cand; break; }
  }
  if (!columns) throw new Error("the connections in this drawing do not form a spiral");
  const ncols = Math.max(...columns.values());
  const centers = new Map([...clusters.keys()].map(k => [k, fits.get(k)[0].origin]));
  const thetas = solveRotations(columns, centers, fits, ncols);
  let { rows } = assignRows(columns, centers, thetas, ncols);
  rows = refineRows(columns, rows, centers, ncols);

  const chosen = new Map();
  const placed = globalPlacement(columns, rows, centers, ncols);
  for (const [k, cands] of fits){
    let got = null;
    if (placed && placed.wmap.has(k)){
      const [wr, wi] = placed.wmap.get(k);
      got = identify(clusters.get(k), wr, wi);
    }
    if (got) chosen.set(k, { gid: got.gid, perm: got.perm, rots: got.rots });
    else {
      const near = cands.filter(f => f.resid <= cands[0].resid + 1);
      near.sort((a, b) => (angdiff(a.theta, thetas.get(columns.get(k)))
                         - angdiff(b.theta, thetas.get(columns.get(k)))) || (a.resid - b.resid));
      chosen.set(k, near[0]);
    }
  }
  const coord = new Map([...clusters.keys()].map(k => [k, [columns.get(k), rows.get(k)]]));
  const glyphs = new Map();
  for (const k of clusters.keys()) glyphs.set(coord.get(k).join(","), chosen.get(k).gid);
  const paths = [[], []];
  for (let i = 1; i <= ncols; i++){
    const js = [...clusters.keys()].filter(k => columns.get(k) === i).map(k => rows.get(k)).sort();
    paths[0].push([i, js[0]]); paths[1].push([i, js[js.length - 1]]);
  }
  const vmaps = new Map([...clusters.keys()].map(k => [k, vertexMap(clusters.get(k), chosen.get(k))]));
  const conns2 = [];
  for (let c of conns){
    let { ka, pa, kb, pb } = c;
    if (columns.get(ka) > columns.get(kb)) [ka, pa, kb, pb] = [kb, pb, ka, pa];
    const ga = allpoints(G.glyphs[chosen.get(ka).gid - 1]);
    const gb = allpoints(G.glyphs[chosen.get(kb).gid - 1]);
    const ia = vmaps.get(ka).get(pkey(pa)), ib = vmaps.get(kb).get(pkey(pb));
    if (ia === undefined || ib === undefined) throw new Error("a join lands on no vertex");
    conns2.push({ a: coord.get(ka), pa: ga[ia], b: coord.get(kb), pb: gb[ib] });
  }
  const fit = placed ? placed.fit : null;
  return { glyphs, paths, conns: conns2, ncols, fit };
}

/* ---------- observation back to text (unambiguous dialect only) ---------- */
function columnOptionsStrict(obs, col){
  if (col === 1) return [[NG, obs.glyphs.get("1," + MIDLINE)]];
  const heads = [obs.paths[0][col - 2], obs.paths[1][col - 2]];
  const nx = [obs.paths[0][col - 1], obs.paths[1][col - 1]];
  const opts = jointRows(heads[0][1], heads[1][1]);
  const pair = [Math.min(nx[0][1], nx[1][1]), Math.max(nx[0][1], nx[1][1])];
  const at = opts.findIndex(o => o[0] === pair[0] && o[1] === pair[1]);
  if (at < 0) throw new Error("column " + col + " has an impossible pair of rows");
  const seq = [[opts.length, at + 1]];
  const seen = new Set();
  for (const c of nx){
    const key = c.join(",");
    if (seen.has(key)) continue;
    seen.add(key);
    seq.push([NG, obs.glyphs.get(key)]);
  }
  const done = new Set();
  for (let i = 0; i < 2; i++){
    const key = heads[i].join(",") + "|" + nx[i].join(",");
    if (done.has(key)) continue;
    done.add(key);
    const conn = obs.conns.find(c => c.a[0] === heads[i][0] && c.a[1] === heads[i][1]
                                  && c.b[0] === nx[i][0] && c.b[1] === nx[i][1]);
    if (!conn) throw new Error("a join between columns is missing");
    const pairs = dedupe(connectionPairs(
      G.glyphs[obs.glyphs.get(heads[i].join(",")) - 1],
      G.glyphs[obs.glyphs.get(nx[i].join(",")) - 1],
      SPACING * (nx[i][0] - heads[i][0]), SPACING * (nx[i][1] - heads[i][1])), "strict");
    const idx = pairs.findIndex(([x, y]) => samePt(x, conn.pa) && samePt(y, conn.pb));
    if (idx < 0) throw new Error("a join does not land where any glyph allows");
    seq.push([pairs.length, idx + 1]);
  }
  return seq;
}
function readStrict(obs, base){
  const seq = [];
  const colStarts = [];
  for (let col = 1; col <= obs.ncols; col++){
    colStarts.push(seq.length);
    for (const s of columnOptionsStrict(obs, col)) seq.push(s);
  }
  const M = [1n];
  for (const [k] of seq) M.push(M[M.length - 1] * BigInt(k));
  const last = colStarts[colStarts.length - 1];
  let acc = 0n;
  const out = [], seen = new Set();
  for (let i = 0; i < seq.length; i++){
    acc += BigInt(seq[i][1] - 1) * M[i];
    if (i < last || seen.has(acc)) continue;
    seen.add(acc);
    const t = toText(decodeInt(acc, base, "strict"));
    if (t !== null && sameGrid(buildGrid(acc, "strict"), obs)) out.push(t);
  }
  return out;
}
