/**
 * An SVG chosen for the cover, turned into a PNG in the browser before it's
 * sent: the server stores and prints pictures (it can't read an SVG), and
 * an SVG can carry code, so it never reaches the server as such. Drawn at
 * 3600 px on its long side — A4 printed at 300 dpi needs 3508 — with its
 * transparency kept.
 */
const LONG_SIDE = 3600;

export function isSvgFile(file) {
  return Boolean(file) && (file.type === "image/svg+xml" || /\.svg$/i.test(file.name || ""));
}

/** Its width ÷ height, from its viewBox or width/height (1 when unknown). */
export function svgAspect(svg) {
  const vb = (svg.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
  if (vb.length === 4 && vb[2] > 0 && vb[3] > 0) return vb[2] / vb[3];
  const w = parseFloat(svg.getAttribute("width"));
  const h = parseFloat(svg.getAttribute("height"));
  return w > 0 && h > 0 ? w / h : 1;
}

export async function svgToPng(file) {
  const text = await file.text();
  const doc = new DOMParser().parseFromString(text, "image/svg+xml");
  const svg = doc.documentElement;
  if (!svg || svg.nodeName.toLowerCase() !== "svg" || doc.getElementsByTagName("parsererror").length) {
    throw new Error("not an svg");
  }
  const aspect = svgAspect(svg);
  const width = Math.round(aspect >= 1 ? LONG_SIDE : LONG_SIDE * aspect);
  const height = Math.round(aspect >= 1 ? LONG_SIDE / aspect : LONG_SIDE);
  // Drawn at this exact size (an SVG with only a viewBox has none of its own).
  if (!svg.getAttribute("viewBox")) {
    const w = parseFloat(svg.getAttribute("width")) || width;
    const h = parseFloat(svg.getAttribute("height")) || height;
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  }
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    img.decoding = "async";
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = () => reject(new Error("svg could not be drawn"));
      img.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    canvas.getContext("2d").drawImage(img, 0, 0, width, height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("svg could not be drawn");
    return new File([blob], (file.name || "image").replace(/\.svg$/i, "") + ".png", { type: "image/png" });
  } finally {
    URL.revokeObjectURL(url);
  }
}
