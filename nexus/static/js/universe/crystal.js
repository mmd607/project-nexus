// Shaded octahedral crystal rendered through the scene camera, so it sits in the
// same perspective as the rings and links. Cheap: 8 triangles per node.
import { hexToRgb } from './sprites.js';

const LIGHT = normalize([-0.45, 0.85, -0.35]);

function normalize(v) { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; }
function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
function cross(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

/**
 * @param ctx      2D context
 * @param camera   Camera
 * @param cx,cy,cz world centre
 * @param size     world half-height of the crystal
 * @param color    hex
 * @param spin     local rotation (radians) around Y
 * @param opts     { alpha, glass, stretch }
 */
export function drawCrystal(ctx, camera, cx, cy, cz, size, color, spin, opts = {}) {
  const alpha = opts.alpha ?? 1;
  const stretch = opts.stretch ?? 1.45;
  if (opts.simple) {
    // Low-detail: a flat shaded diamond (4 points) — used for small/far nodes in big scenes.
    const top = camera.project(cx, cy + size * stretch, cz), bottom = camera.project(cx, cy - size * 0.9, cz);
    const left = camera.project(cx - size * 0.72, cy, cz), right = camera.project(cx + size * 0.72, cy, cz);
    const [r, g, b] = hexToRgb(color);
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.beginPath(); ctx.moveTo(top.x, top.y); ctx.lineTo(right.x, right.y); ctx.lineTo(bottom.x, bottom.y); ctx.lineTo(left.x, left.y); ctx.closePath();
    ctx.fillStyle = `rgba(${Math.min(255, r * 0.95 + 30)},${Math.min(255, g * 0.95 + 30)},${Math.min(255, b * 0.95 + 30)},0.92)`; ctx.fill();
    ctx.beginPath(); ctx.moveTo(top.x, top.y); ctx.lineTo(left.x, left.y); ctx.lineTo(bottom.x, bottom.y); ctx.closePath();
    ctx.fillStyle = `rgba(${Math.round(r * 0.55)},${Math.round(g * 0.55)},${Math.round(b * 0.55)},0.92)`; ctx.fill();
    ctx.restore();
    return [top, bottom, left, right];
  }
  const w = size * 0.72, hh = size * stretch;
  const cs = Math.cos(spin), sn = Math.sin(spin);
  const local = [
    [0, hh, 0], [0, -hh * 0.9, 0],
    [w * cs, 0, w * sn], [-w * sn, 0, w * cs], [-w * cs, 0, -w * sn], [w * sn, 0, -w * cs],
  ];
  const world = local.map(v => [cx + v[0], cy + v[1], cz + v[2]]);
  const screen = world.map(v => camera.project(v[0], v[1], v[2]));
  const faces = [[0, 2, 3], [0, 3, 4], [0, 4, 5], [0, 5, 2], [1, 3, 2], [1, 4, 3], [1, 5, 4], [1, 2, 5]];
  const [r, g, b] = hexToRgb(color);
  const items = faces.map(f => {
    const n = normalize(cross(sub(world[f[1]], world[f[0]]), sub(world[f[2]], world[f[0]])));
    const depth = (screen[f[0]].depth + screen[f[1]].depth + screen[f[2]].depth) / 3;
    return { f, n, depth };
  }).sort((a, b) => b.depth - a.depth);   // far faces first
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.lineJoin = 'round';
  for (const { f, n } of items) {
    const lambert = Math.max(0, dot(n, LIGHT));
    const top = f[0] === 0 ? 0.18 : 0;   // upper pyramid a little brighter
    const k = opts.light ? 0.6 + 0.5 * lambert + top : 0.28 + 0.62 * lambert + top;
    const fr = Math.min(255, Math.round(r * k + 255 * Math.max(0, k - 0.9) * 2));
    const fg = Math.min(255, Math.round(g * k + 255 * Math.max(0, k - 0.9) * 2));
    const fb = Math.min(255, Math.round(b * k + 255 * Math.max(0, k - 0.9) * 2));
    ctx.beginPath();
    ctx.moveTo(screen[f[0]].x, screen[f[0]].y);
    ctx.lineTo(screen[f[1]].x, screen[f[1]].y);
    ctx.lineTo(screen[f[2]].x, screen[f[2]].y);
    ctx.closePath();
    ctx.fillStyle = `rgba(${fr},${fg},${fb},${opts.glass ? 0.82 : 0.94})`;
    ctx.fill();
    if (opts.stroke !== false) {
      ctx.strokeStyle = `rgba(255,255,255,${0.16 + lambert * 0.28})`;
      ctx.lineWidth = Math.max(0.6, screen[0].f * 0.9);
      ctx.stroke();
    }
  }
  // Specular sparkle near the top vertex.
  const tip = screen[0];
  const sp = Math.max(1.2, size * tip.f * 0.14);
  ctx.fillStyle = 'rgba(255,255,255,0.75)';
  ctx.beginPath();
  ctx.arc(tip.x + sp * 0.4, tip.y + sp * 2.2, sp, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  return screen;
}
