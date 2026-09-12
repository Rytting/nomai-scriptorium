/* Page decoration only: it observes the two mode buttons, never the wall SVG. */
function initEyeBackdrop(){
  const backdrop = document.getElementById("eye-backdrop");
  const canvas = backdrop.querySelector("svg");
  const symbol = document.getElementById("eye-symbol");
  const wrap = document.querySelector(".wrap");
  const modes = document.querySelector(".seg.modes");
  const links = [...backdrop.querySelectorAll(".eye-link")].map(group => ({
    group, button:document.getElementById(`m-${group.dataset.mode}`),
    ray:group.querySelector(".eye-ray"), glint:group.querySelector(".eye-glint")
  }));
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  let frame = 0;
  function layout(){
    frame = 0;
    const origin = backdrop.getBoundingClientRect();
    const bounds = modes.getBoundingClientRect();
    const width = origin.width;
    if (!width) return;
    const top = bounds.top - origin.top, bottom = bounds.bottom - origin.top;
    const height = bottom + 110;
    const compact = width <= 600;
    // Keep the eye on the page's right side even when the reader narrows .wrap.
    const scale = compact ? Math.max(2.2, width / 170) : Math.min(5.8, Math.max(3.5, width / 300));
    const introRight = wrap.querySelector(".sub").getBoundingClientRect().right - origin.left;
    const cx = compact ? width * 1.01 : Math.max(width * .84, introRight + 28 + 102.954 * scale);
    const cy = compact ? 36 : Math.min(160, top * .43);
    const tx = cx - 102.954 * scale, ty = cy - 80.466 * scale;
    backdrop.style.height = `${height}px`;
    canvas.setAttribute("viewBox", `0 0 ${width} ${height}`);
    symbol.setAttribute("transform", `translate(${tx} ${ty}) scale(${scale})`);
    const point = (x,y) => [tx + x * scale, ty + y * scale];
    const ends = links.map(({button}) => {
      const b = button.getBoundingClientRect();
      return {x:b.left - origin.left + b.width / 2, top:b.top - origin.top, bottom:b.bottom - origin.top};
    });
    const [write,read] = ends;
    const left = point(0,81.364), lower = point(40.406,138.644);
    const above = top - 13, below = bottom + 13;
    // Angular bends continue the engraving through the clear bands around the
    // controls. Ends meet opposite button edges without crossing either icon.
    const elbow = Math.max(write.x + 34, left[0] - Math.max(0,above - left[1]));
    const lowerElbow = Math.max(read.x + 28, lower[0] - Math.max(0,below - lower[1]) / .887);
    const paths = compact ? [
      `M ${point(101.718,145.508)} L ${width - 10} ${above} H ${write.x} V ${write.top}`,
      `M ${point(106.839,122.489)} L ${width - 3} ${below} H ${read.x} V ${read.bottom}`
    ] : [
      `M ${left} L ${elbow} ${above} H ${write.x} V ${write.top}`,
      `M ${lower} L ${lowerElbow} ${below} H ${read.x} V ${read.bottom}`
    ];
    links.forEach((link,i) => {
      link.ray.setAttribute("d", paths[i]);
      link.glint.setAttribute("d", paths[i]);
    });
    backdrop.classList.add("ready");
  }
  function schedule(){if (!frame) frame = requestAnimationFrame(layout);}
  function pulse(link){
    link.glint.getAnimations().forEach(animation => animation.cancel());
    if (reducedMotion.matches) return;
    link.glint.animate([
      {strokeDashoffset:0,opacity:0},
      {strokeDashoffset:-.12,opacity:.65,offset:.18},
      {strokeDashoffset:-.8,opacity:.65,offset:.8},
      {strokeDashoffset:-1,opacity:0}
    ],{duration:720,easing:"ease-out"});
  }
  function sync(){
    links.forEach(link => {
      const active = link.button.getAttribute("aria-pressed") === "true";
      const wasActive = link.group.dataset.active === "true";
      link.group.dataset.active = String(active);
      if (active && !wasActive) pulse(link);
    });
    schedule();
  }
  links.forEach(link => {
    const highlight = () => {
      link.group.dataset.hot = "true";
      pulse(link);
    };
    const unhighlight = () => {
      link.group.dataset.hot = String(link.button.matches(":hover,:focus-visible"));
    };
    link.button.addEventListener("pointerenter", e => {if(e.pointerType !== "touch") highlight();});
    link.button.addEventListener("pointerleave", unhighlight);
    link.button.addEventListener("focus", highlight);
    link.button.addEventListener("blur", unhighlight);
  });
  new MutationObserver(sync).observe(modes,{attributes:true,subtree:true,attributeFilter:["aria-pressed"]});
  const resize = new ResizeObserver(schedule);
  [wrap,modes,wrap.querySelector("header")].forEach(el => resize.observe(el));
  window.addEventListener("resize", schedule, {passive:true});
  document.fonts.ready.then(schedule);
  reducedMotion.addEventListener("change", () => {
    if (reducedMotion.matches) links.forEach(link => link.glint.getAnimations().forEach(a => a.cancel()));
  });
  sync();
}
