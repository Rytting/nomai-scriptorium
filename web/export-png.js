/* Artwork export is a raster copy, never a replacement for the readable SVG.
   Work from committed geometry, not the animated/zoomed live drawing. */
function transparentPngSource(svgText, inks, longEdge = 2048){
  const doc = new DOMParser().parseFromString(svgText, "image/svg+xml");
  const svg = doc.documentElement;
  if(doc.querySelector("parsererror") || svg.localName !== "svg")throw Error("Invalid SVG");
  const box = svg.getAttribute("viewBox")?.trim().split(/[\s,]+/).map(Number);
  if(!box || box.length !== 4 || !box.every(Number.isFinite) || box[2] <= 0 || box[3] <= 0)
    throw Error("Invalid drawing size");
  if(!Number.isFinite(longEdge) || longEdge < 1 || longEdge > 4096)throw Error("Invalid PNG size");
  const scale = longEdge / Math.max(box[2], box[3]);
  const width = Math.max(1, Math.round(box[2] * scale));
  const height = Math.max(1, Math.round(box[3] * scale));
  // document_ emits one paper rectangle before the actual spiral groups.
  const paper = svg.firstElementChild;
  if(paper?.localName === "rect")paper.remove();
  for(const path of svg.querySelectorAll("path")){
    const group = path.closest("[data-spiral]");
    const index = group ? Number(group.getAttribute("data-spiral")) : 0;
    const ink = inks[index] || inks[0] || "#104e8b";
    path.setAttribute(path.hasAttribute("stroke-width") ? "stroke" : "fill", ink);
  }
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  return {text: new XMLSerializer().serializeToString(svg), width, height};
}
async function transparentPngBlob(svgText, inks, longEdge = 2048){
  const source = transparentPngSource(svgText, inks, longEdge);
  const url = URL.createObjectURL(new Blob([source.text], {type: "image/svg+xml"}));
  const canvas = document.createElement("canvas");
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    canvas.width = source.width; canvas.height = source.height;
    const ctx = canvas.getContext("2d");
    if(!ctx)throw Error("Canvas unavailable");
    // A fresh canvas has transparent pixels; never paint a background underneath.
    ctx.drawImage(image, 0, 0, source.width, source.height);
    return await new Promise((resolve, reject) => canvas.toBlob(
      blob => blob ? resolve(blob) : reject(Error("PNG encoding failed")), "image/png"));
  } finally {
    URL.revokeObjectURL(url);
    canvas.width = canvas.height = 0;
  }
}
