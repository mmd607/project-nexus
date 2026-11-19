// Pre-rendered glow sprites and rasterised icon images. Avoids shadowBlur per node,
// which is the single most expensive Canvas 2D operation.
const glowCache = new Map();
const iconCache = new Map();

export function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function rgba(hex, a) {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${a})`;
}

export function mix(hexA, hexB, t) {
  const a = hexToRgb(hexA), b = hexToRgb(hexB);
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export function glowSprite(color, size = 128, inner = 0.55) {
  const key = `${color}:${size}:${inner}`;
  if (glowCache.has(key)) return glowCache.get(key);
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, rgba(color, inner));
  g.addColorStop(0.35, rgba(color, inner * 0.35));
  g.addColorStop(1, rgba(color, 0));
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  glowCache.set(key, c);
  return c;
}

/** Rasterise an SVG <symbol> from the sprite sheet into an Image (async; check .complete). */
export function iconImage(symbolId, color, size = 40) {
  const key = `${symbolId}:${color}:${size}`;
  if (iconCache.has(key)) return iconCache.get(key);
  const symbol = document.getElementById(symbolId);
  const img = new Image();
  if (symbol) {
    const viewBox = symbol.getAttribute('viewBox') || '0 0 24 24';
    const attrs = [...symbol.attributes].filter(a => !['id', 'viewBox'].includes(a.name)).map(a => `${a.name}="${a.value}"`).join(' ');
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="${viewBox}" ${attrs} color="${color}">${symbol.innerHTML}</svg>`;
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  }
  iconCache.set(key, img);
  return img;
}

export function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}
