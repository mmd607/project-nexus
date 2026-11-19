// Scene renderer for the Universe. Pure drawing: takes a scene description and a
// camera, writes pixels, returns hit regions. No DOM access apart from the canvas.
import { drawCrystal } from './crystal.js';
import { glowSprite, iconImage, rgba, roundRect } from './sprites.js';
import { CATEGORY_COLORS, CATEGORY_ICONS, STATUS_COLORS } from '../store.js';
import { ringsFor, hash } from './layout.js';

const TAU = Math.PI * 2;
const LABEL_FONT = '600 12.5px "Inter", "Segoe UI", system-ui, sans-serif';
const SUB_FONT = '11px "Inter", "Segoe UI", system-ui, sans-serif';
const SAT_FONT = '500 11px "Inter", "Segoe UI", system-ui, sans-serif';
const SAT_SUB_FONT = '10px "Inter", "Segoe UI", system-ui, sans-serif';

function overlaps(a, b) { return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y; }

export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d', { alpha: true });
    this.dpr = 1;
    this.width = 0; this.height = 0;
    this.stars = [];
    this.particles = [];
    this.hits = [];
    this.labelRects = [];
    this.textWidthCache = new Map();
    this.theme = 'dark';
    this.labelChoice = new Map();   // node id → { index, variant } chosen last frame (keeps labels from flickering while nodes move)
    this.upgradeTick = -1;
  }

  resize(width, height) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (width === this.width && height === this.height && dpr === this.dpr) return;
    this.width = width; this.height = height; this.dpr = dpr;
    this.canvas.width = Math.max(1, Math.round(width * dpr));
    this.canvas.height = Math.max(1, Math.round(height * dpr));
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.stars = [];
    const count = Math.round((width * height) / 9000);
    for (let i = 0; i < count; i++) this.stars.push({ x: Math.random() * width, y: Math.random() * height, r: Math.random() * 1.1 + 0.2, a: Math.random() * 0.5 + 0.15 });
    if (!this.particles.length) {
      for (let i = 0; i < 90; i++) this.particles.push({ a: Math.random() * TAU, r: 120 + Math.random() * 420, y: (Math.random() - 0.5) * 40, s: 0.02 + Math.random() * 0.05, size: Math.random() * 1.4 + 0.5, alpha: 0.2 + Math.random() * 0.4 });
    }
  }

  measure(text, font) {
    const key = font + '|' + text;
    let w = this.textWidthCache.get(key);
    if (w == null) {
      this.ctx.font = font;
      w = this.ctx.measureText(text).width;
      if (this.textWidthCache.size > 4000) this.textWidthCache.clear();
      this.textWidthCache.set(key, w);
    }
    return w;
  }

  /** First candidate rectangle that does not collide with an already placed label (or the least bad one when forced). */
  place(w, h, candidates, forced, preferred = -1) {
    let fallback = null;
    const order = preferred >= 0 && preferred < candidates.length ? [preferred, ...candidates.map((_, i) => i).filter(i => i !== preferred)] : candidates.map((_, i) => i);
    for (const i of order) {
      const c = candidates[i];
      const rect = { x: Math.max(6, Math.min(this.width - w - 6, c.x)), y: Math.max(6, Math.min(this.height - h - 6, c.y)), w, h, index: i };
      if (!this.labelRects.some(other => overlaps(rect, other))) return rect;
      if (!fallback) fallback = rect;
    }
    return forced ? fallback : null;
  }

  /**
   * @param scene {
   *   camera, nodes: [{id, project, pos:{x,y,z,r,parentId,depth}, alpha, visible, selected, hovered, focused}],
   *   hubLabel, hubSub, time, rotationOn, reducedMotion, particles, showRelations, relations:[{a,b,weight}],
   *   maxLabels, theme, focus: null | { id, satellites: [{id, label, sub, color, pos:{x,y,z}, selected, hovered}] }
   * }
   */
  draw(scene) {
    const ctx = this.ctx, cam = scene.camera, W = this.width, H = this.height;
    this.theme = scene.theme || 'dark';
    const dark = this.theme !== 'light';
    ctx.clearRect(0, 0, W, H);
    this.hits = [];
    // DOM overlays (stats card, filter bar, breadcrumb, controls) are opaque: never put a label under them.
    this.labelRects = (scene.reserved || []).map(r => ({ ...r }));

    // Stars
    ctx.fillStyle = dark ? '#ffd9e2' : '#c34a72';
    for (const s of this.stars) {
      ctx.globalAlpha = s.a * (dark ? 1 : 0.35);
      ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, TAU); ctx.fill();
    }
    ctx.globalAlpha = 1;

    const n = scene.nodes.length;
    const rings = ringsFor(n);
    const hub = cam.project(0, 0, 0);
    const focusDim = scene.focus ? 0.55 : 1;   // the whole universe steps back a little while a project is in focus

    // Ground glow under the hub
    const hubGlow = glowSprite('#fa2559', 256, dark ? 0.5 : 0.25);
    const gs = 420 * hub.f;
    ctx.drawImage(hubGlow, hub.x - gs / 2, hub.y - gs * 0.5 * (cam.flat ? 1 : 0.62), gs, gs * (cam.flat ? 1 : 0.62));

    // Orbit rings (projected circles)
    ctx.lineWidth = 1;
    rings.forEach((radius, i) => {
      ctx.beginPath();
      for (let k = 0; k <= 96; k++) {
        const a = (k / 96) * TAU;
        const p = cam.project(Math.cos(a) * radius, 0, Math.sin(a) * radius);
        if (k === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
      }
      ctx.strokeStyle = rgba('#fa2559', (dark ? (0.22 - i * 0.03) : (0.28 - i * 0.04)) * focusDim);
      ctx.stroke();
      if (i === 0) {
        ctx.strokeStyle = rgba('#ff7a9c', (dark ? 0.35 : 0.4) * focusDim);
        ctx.setLineDash([2, 6]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    });

    // Particles drifting on the plane
    if (scene.particles) {
      ctx.fillStyle = dark ? '#ff9db5' : '#d13d6a';
      for (const p of this.particles) {
        if (scene.rotationOn && !scene.reducedMotion) p.a += p.s * 0.004;
        const q = cam.project(Math.cos(p.a) * p.r, p.y, Math.sin(p.a) * p.r);
        ctx.globalAlpha = p.alpha * (dark ? 0.7 : 0.4) * focusDim;
        ctx.beginPath(); ctx.arc(q.x, q.y, p.size * q.f, 0, TAU); ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    // Project nodes (with viewport culling — off-screen nodes still take part in links/hit-tests via byId)
    const margin = 140;
    const all = scene.nodes.map(nd => {
      const p = cam.project(nd.pos.x, nd.pos.y, nd.pos.z);
      const ground = cam.project(nd.pos.x, 0, nd.pos.z);
      const onScreen = p.x > -margin && p.x < W + margin && p.y > -margin && p.y < H + margin;
      return { ...nd, sx: p.x, sy: p.y, f: p.f, depth: p.depth, gx: ground.x, gy: ground.y, onScreen, h: nd.h ?? hash(nd.id), alpha: nd.alpha ?? 1 };
    });
    const byId = new Map(all.map(p => [p.id, p]));
    const projected = all.filter(p => p.onScreen);
    // Level of detail: big scenes drop strokes/beams/pulses; tiny nodes become flat diamonds.
    const lod = all.length > 140 ? 2 : all.length > 70 ? 1 : 0;

    // Links hub → project, parent → promoted sub-project
    for (const nd of projected) {
      const strength = nd.alpha;
      const alpha = (nd.selected ? 0.9 : nd.hovered ? 0.6 : 0.34) * Math.max(0.12, strength);
      const color = nd.selected || nd.hovered ? '#ff6b8f' : (nd.pos.parentId ? '#9b7cff' : '#c22a58');
      ctx.strokeStyle = rgba(color, dark ? alpha : alpha * 0.9);
      ctx.lineWidth = nd.selected ? 1.6 : nd.pos.parentId ? 0.9 : 1;
      let from = hub, fromX = 0, fromZ = 0;
      if (nd.pos.parentId) {
        const parent = byId.get(nd.pos.parentId);
        if (parent) { from = { x: parent.gx, y: parent.gy }; fromX = parent.pos.x; fromZ = parent.pos.z; }
      }
      const lift = cam.project((nd.pos.x + fromX) / 2, cam.flat ? 0 : 26, (nd.pos.z + fromZ) / 2);
      if (nd.pos.parentId) ctx.setLineDash([4, 6]);
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.quadraticCurveTo(lift.x, lift.y, nd.gx, nd.gy);
      ctx.stroke();
      ctx.setLineDash([]);
      if (strength > 0.5 && !nd.pos.parentId && scene.rotationOn && !scene.reducedMotion && lod === 0) {
        // energy pulse travelling along the link
        const t = (scene.time * 0.12 + nd.h) % 1;
        const px = (1 - t) * (1 - t) * from.x + 2 * (1 - t) * t * lift.x + t * t * nd.gx;
        const py = (1 - t) * (1 - t) * from.y + 2 * (1 - t) * t * lift.y + t * t * nd.gy;
        ctx.fillStyle = rgba('#ff8fab', 0.55 * strength);
        ctx.beginPath(); ctx.arc(px, py, 1.6 * nd.f + 0.6, 0, TAU); ctx.fill();
      }
    }

    // Optional relation links (shared technology)
    if (scene.showRelations && scene.relations) {
      ctx.setLineDash([3, 5]);
      for (const rel of scene.relations) {
        const a = byId.get(rel.a), b = byId.get(rel.b);
        if (!a || !b) continue;
        const strong = a.selected || b.selected;
        if (a.alpha < 0.3 && b.alpha < 0.3) continue;
        ctx.strokeStyle = rgba(strong ? '#67ccfa' : '#9b7cff', strong ? 0.7 : 0.16);
        ctx.lineWidth = strong ? 1.2 : 0.7;
        ctx.beginPath(); ctx.moveTo(a.gx, a.gy); ctx.lineTo(b.gx, b.gy); ctx.stroke();
      }
      ctx.setLineDash([]);
    }

    // Nodes far → near
    projected.sort((a, b) => b.depth - a.depth);
    const spin = scene.reducedMotion ? 0 : scene.time * 0.35;
    for (const nd of projected) {
      const color = CATEGORY_COLORS[nd.project.categories[0]] || CATEGORY_COLORS.Other;
      const alpha = nd.alpha;
      const r = nd.pos.r * nd.f;
      const squash = cam.flat ? 1 : Math.max(0.28, 0.5 - Math.cos(cam.pitch) * 0.2);
      ctx.globalAlpha = alpha;
      // pedestal glow + rings on the ground
      const glow = glowSprite(color, 128, dark ? 0.5 : 0.3);
      const gsz = r * (nd.pos.parentId ? 3.6 : 4.4);
      ctx.drawImage(glow, nd.gx - gsz / 2, nd.gy - (gsz * squash) / 2, gsz, gsz * squash);
      ctx.lineWidth = 1;
      ctx.strokeStyle = rgba(color, 0.55);
      ctx.beginPath(); ctx.ellipse(nd.gx, nd.gy, r * 1.35, r * 1.35 * squash, 0, 0, TAU); ctx.stroke();
      if (lod < 2) {
        ctx.strokeStyle = rgba(color, 0.28);
        ctx.beginPath(); ctx.ellipse(nd.gx, nd.gy, r * 1.85, r * 1.85 * squash, 0, 0, TAU); ctx.stroke();
      }
      // secondary categories as small beads on the outer ring
      const extra = nd.project.categories.slice(1, 4);
      if (extra.length && lod < 2 && r > 9) {
        extra.forEach((cat, i) => {
          const a = -Math.PI / 2 + (i + 1) * (TAU / (extra.length + 1)) + nd.h * TAU;
          const bx = nd.gx + Math.cos(a) * r * 1.85, by = nd.gy + Math.sin(a) * r * 1.85 * squash;
          ctx.fillStyle = CATEGORY_COLORS[cat] || CATEGORY_COLORS.Other;
          ctx.beginPath(); ctx.arc(bx, by, Math.max(2, r * 0.12), 0, TAU); ctx.fill();
        });
      }
      if (nd.selected || nd.focused) {
        const pulse = scene.reducedMotion ? 1 : 1 + Math.sin(scene.time * 3) * 0.06;
        ctx.strokeStyle = rgba(nd.selected ? '#ffffff' : '#ffd166', 0.85);
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.ellipse(nd.gx, nd.gy, r * 2.3 * pulse, r * 2.3 * pulse * squash, 0, 0, TAU); ctx.stroke();
        if (nd.selected) {
          // focus halo around the crystal itself
          const halo = glowSprite('#ffffff', 128, 0.35);
          const hs = r * 5.2;
          ctx.drawImage(halo, nd.sx - hs / 2, nd.sy + r * 0.9 - hs / 2, hs, hs);
        }
      } else if (nd.hovered) {
        ctx.strokeStyle = rgba('#ffffff', 0.5);
        ctx.beginPath(); ctx.ellipse(nd.gx, nd.gy, r * 2.2, r * 2.2 * squash, 0, 0, TAU); ctx.stroke();
      }
      // vertical "beam" from ground to crystal in 3D
      if (!cam.flat && (lod === 0 || nd.selected || nd.hovered)) {
        ctx.strokeStyle = rgba(color, 0.35);
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(nd.gx, nd.gy); ctx.lineTo(nd.sx, nd.sy + r * 0.9); ctx.stroke();
      }
      // crystal
      const size = nd.pos.r * (nd.selected ? 1.18 : nd.hovered ? 1.1 : 1);
      const detailed = nd.selected || nd.hovered || nd.focused || lod === 0 || (lod === 1 && r > 7);
      drawCrystal(ctx, cam, nd.pos.x, nd.pos.y + nd.pos.r * 0.9, nd.pos.z, size, color, spin + nd.h * TAU,
        { alpha: 1, glass: true, light: !dark, stroke: detailed, simple: !detailed && r < 9 });
      // status dot
      const sc = STATUS_COLORS[nd.project.status] || STATUS_COLORS.Idle;
      ctx.fillStyle = sc;
      ctx.beginPath(); ctx.arc(nd.sx + r * 1.05, nd.sy - r * 0.6, Math.max(2.2, r * 0.18), 0, TAU); ctx.fill();
      ctx.globalAlpha = 1;
      nd.screenR = r;
      this.hits.push({ id: nd.id, x: nd.sx, y: nd.sy, r: Math.max(18, r * 1.7), depth: nd.depth });
    }

    // Hub crystal
    const hubR = 46 * hub.f;
    for (let i = 0; i < 3; i++) {
      const rr = hubR * (1.25 + i * 0.5);
      ctx.strokeStyle = rgba('#fa2559', (0.75 - i * 0.22) * focusDim);
      ctx.lineWidth = i === 0 ? 1.6 : 1;
      ctx.beginPath(); ctx.ellipse(hub.x, hub.y, rr, rr * (cam.flat ? 1 : 0.55), 0, 0, TAU); ctx.stroke();
    }
    const pulse = scene.reducedMotion ? 1 : 1 + Math.sin(scene.time * 1.6) * 0.04;
    ctx.globalAlpha = focusDim;
    ctx.drawImage(glowSprite('#ff3d6c', 256, 0.9), hub.x - hubR * 3 * pulse, hub.y - hubR * 3 * pulse, hubR * 6 * pulse, hubR * 6 * pulse);
    ctx.fillStyle = dark ? 'rgba(48,14,32,0.85)' : 'rgba(255,230,238,0.9)';
    ctx.beginPath(); ctx.ellipse(hub.x, hub.y, hubR * 1.05, hubR * 1.05 * (cam.flat ? 1 : 0.55), 0, 0, TAU); ctx.fill();
    drawCrystal(ctx, cam, 0, 40, 0, 40, '#fa2559', spin * 0.4, { alpha: 1, glass: false, stretch: 1.55, light: !dark });
    ctx.globalAlpha = 1;
    this.hits.push({ id: '__hub__', x: hub.x, y: hub.y - 30 * hub.f, r: hubR * 1.4, depth: hub.depth });
    // Hub label
    ctx.textAlign = 'center';
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = dark ? '#ffffff' : '#1d1219';
    const hubFont = `600 ${Math.min(21, Math.max(14, 18 * hub.f))}px "Inter", "Segoe UI", system-ui, sans-serif`;
    ctx.font = hubFont;
    ctx.globalAlpha = focusDim;
    ctx.fillText(scene.hubLabel, hub.x, hub.y + hubR * 2.3);
    ctx.fillStyle = dark ? '#c7b8c2' : '#5f4f5a';
    ctx.font = `${Math.min(13, Math.max(11, 12 * hub.f))}px "Inter", "Segoe UI", system-ui, sans-serif`;
    ctx.fillText(scene.hubSub, hub.x, hub.y + hubR * 2.3 + 18);
    ctx.globalAlpha = 1;

    // Reserve the hub + its caption so project labels never cover them.
    const hubW = Math.max(160, this.measure(scene.hubLabel, hubFont) + 40);
    this.labelRects.push({ x: hub.x - hubW / 2, y: hub.y - hubR * 2.2, w: hubW, h: hubR * 2.2 + hubR * 2.3 + 30 });

    // Focused project: its internal parts orbit it as small satellites (never permanent nodes).
    if (scene.focus && byId.has(scene.focus.id)) this.drawSatellites(scene, byId.get(scene.focus.id), dark);

    // Labels: priority order, declutter against already-placed rectangles. In focus view only the focused
    // project and its relatives keep their labels (the rest stays visible as dimmed crystals).
    const minAlpha = scene.focus ? 0.5 : 0.25;
    const labelCandidates = projected.filter(nd => nd.alpha > minAlpha || nd.hovered || nd.selected).sort((a, b) => {
      const pa = (a.selected ? 4 : 0) + (a.hovered ? 3 : 0) + (a.focused ? 2 : 0) + (a.pos.parentId ? -1 : 0);
      const pb = (b.selected ? 4 : 0) + (b.hovered ? 3 : 0) + (b.focused ? 2 : 0) + (b.pos.parentId ? -1 : 0);
      return pb - pa || a.depth - b.depth;
    });
    const maxLabels = scene.maxLabels ?? 60;
    // Every couple of seconds labels may try to grow back to a bigger variant; otherwise they keep last frame's choice.
    const tick = Math.floor(scene.time / 2);
    const allowUpgrade = tick !== this.upgradeTick;
    this.upgradeTick = tick;
    let drawn = 0;
    const seen = new Set();
    for (const nd of labelCandidates) {
      const forced = nd.selected || nd.hovered || nd.focused;
      if (!forced && drawn >= maxLabels) continue;
      const prev = this.labelChoice.get(nd.id);
      const startVariant = prev && !allowUpgrade && !forced ? prev.variant : null;
      if (this.drawLabel(nd, hub, forced, dark, scene.focus ? 0.7 : 1, startVariant)) { drawn++; seen.add(nd.id); }
    }
    for (const id of [...this.labelChoice.keys()]) if (!seen.has(id)) this.labelChoice.delete(id);
    ctx.globalAlpha = 1;
  }

  /**
   * Label pill next to a node. Variants: 'full' (icon, name, categories), 'compact' (icon + name) and 'mini'
   * (name only). When the requested variant does not fit between already placed labels, the next smaller
   * one is tried, so a node only stays unlabelled when even its bare name would collide.
   */
  drawLabel(nd, hub, forced, dark, dimFactor = 1, variant = null) {
    const ctx = this.ctx;
    const project = nd.project;
    const color = CATEGORY_COLORS[project.categories[0]] || CATEGORY_COLORS.Other;
    variant = variant || ((!forced && (nd.f < 0.6 || nd.pos.parentId)) ? 'compact' : 'full');
    const compact = variant !== 'full', mini = variant === 'mini';
    const maxChars = mini ? 22 : compact ? 26 : 32;
    const full = project.name;
    const name = full.length > maxChars ? full.slice(0, maxChars - 1) + '…' : full;
    const sub = nd.pos.parentId ? (project.parentName ? `↳ ${project.parentName}` : project.categories.slice(0, 2).join(' / ')) : project.categories.slice(0, 2).join(' / ');
    const pad = mini ? 8 : 10, iconR = mini ? 0 : compact ? 12 : 15, gap = mini ? 0 : 8;
    const font = mini ? SAT_FONT : LABEL_FONT;
    const nameW = this.measure(name, font);
    const subW = compact ? 0 : this.measure(sub, SUB_FONT);
    const w = Math.max(mini ? 40 : compact ? 72 : 96, pad + iconR * 2 + gap + Math.max(nameW, subW) + pad);
    const h = mini ? 22 : compact ? 32 : 46;
    const r = nd.screenR || 12;
    const right = nd.sx >= hub.x;
    const dx = r * 1.2 + 6;
    // Candidate anchors: beside the node (away from the hub), then the other side, above, below.
    const candidates = [
      { x: right ? nd.sx + dx : nd.sx - dx - w, y: nd.sy - r * 1.4 - h },
      { x: right ? nd.sx - dx - w : nd.sx + dx, y: nd.sy - r * 1.4 - h },
      { x: nd.sx - w / 2, y: nd.sy - r * 2.4 - h },
      { x: nd.sx - w / 2, y: nd.sy + r * 1.6 },
      { x: right ? nd.sx + dx : nd.sx - dx - w, y: nd.sy + r * 0.2 },
    ];
    const prev = this.labelChoice.get(nd.id);
    const rect = this.place(w, h, candidates, forced, prev && prev.variant === variant ? prev.index : -1);
    if (!rect) return mini ? false : this.drawLabel(nd, hub, forced, dark, dimFactor, compact ? 'mini' : 'compact');   // no room → smaller variant
    this.labelRects.push(rect);
    this.labelChoice.set(nd.id, { index: rect.index, variant });
    const { x, y } = rect;
    ctx.globalAlpha = Math.min(1, Math.max(0.35, nd.alpha)) * (forced ? 1 : dimFactor);
    roundRect(ctx, x, y, w, h, mini ? 8 : compact ? 10 : 14);
    ctx.fillStyle = dark ? 'rgba(27,18,27,0.92)' : 'rgba(255,255,255,0.94)';
    ctx.fill();
    ctx.lineWidth = nd.selected ? 1.5 : 1;
    ctx.strokeStyle = nd.selected || nd.hovered ? color : (mini ? rgba(color, 0.55) : (dark ? '#4a3143' : '#d9c6d2'));
    ctx.stroke();
    if (!mini) {
      // icon circle
      const ix = x + pad + iconR, iy = y + h / 2;
      ctx.beginPath(); ctx.arc(ix, iy, iconR, 0, TAU);
      ctx.fillStyle = dark ? 'rgba(12,8,11,0.9)' : 'rgba(246,241,244,1)';
      ctx.fill();
      ctx.strokeStyle = rgba(color, 0.85); ctx.lineWidth = 1.2; ctx.stroke();
      const img = iconImage(CATEGORY_ICONS[project.categories[0]] || 'c-other', color, 40);
      const isz = compact ? 14 : 18;
      if (img.complete && img.naturalWidth) ctx.drawImage(img, ix - isz / 2, iy - isz / 2, isz, isz);
    }
    // text
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = dark ? '#f7ecf2' : '#1d1219';
    ctx.font = font;
    ctx.fillText(name, x + pad + iconR * 2 + gap, y + (mini ? 15 : compact ? 20.5 : 20));
    if (!compact) {
      ctx.fillStyle = dark ? '#b3a5ae' : '#5f4f5a';
      ctx.font = SUB_FONT;
      ctx.fillText(sub, x + pad + iconR * 2 + gap, y + 35);
    }
    ctx.globalAlpha = 1;
    this.hits.push({ id: nd.id, rect, depth: -1 });
    return true;
  }

  /** Small orbs around the focused node: components, manifests, README, entry points … */
  drawSatellites(scene, host, dark) {
    const ctx = this.ctx, cam = scene.camera;
    const sats = scene.focus.satellites || [];
    const hostTop = { x: host.sx, y: host.sy + (host.screenR || 12) * 0.9 };
    const items = sats.map(s => {
      const p = cam.project(s.pos.x, s.pos.y, s.pos.z);
      const g = cam.project(s.pos.x, 0, s.pos.z);
      return { ...s, sx: p.x, sy: p.y, f: p.f, depth: p.depth, gx: g.x, gy: g.y };
    }).sort((a, b) => b.depth - a.depth);
    const appear = scene.focus.progress ?? 1;   // 0 → 1 while the satellites fly out
    for (const s of items) {
      const r = Math.max(4.5, 7.5 * s.f) * (s.selected ? 1.35 : s.hovered ? 1.2 : 1);
      const sx = hostTop.x + (s.sx - hostTop.x) * appear, sy = hostTop.y + (s.sy - hostTop.y) * appear;
      ctx.globalAlpha = appear;
      // tether
      ctx.strokeStyle = rgba(s.color, s.selected ? 0.9 : 0.45);
      ctx.lineWidth = s.selected ? 1.4 : 0.9;
      ctx.setLineDash([3, 5]);
      ctx.beginPath(); ctx.moveTo(hostTop.x, hostTop.y); ctx.lineTo(sx, sy); ctx.stroke();
      ctx.setLineDash([]);
      // orb
      const glow = glowSprite(s.color, 64, dark ? 0.7 : 0.4);
      const gsz = r * 6;
      ctx.drawImage(glow, sx - gsz / 2, sy - gsz / 2, gsz, gsz);
      ctx.fillStyle = dark ? 'rgba(20,10,18,0.95)' : 'rgba(255,255,255,0.95)';
      ctx.beginPath(); ctx.arc(sx, sy, r, 0, TAU); ctx.fill();
      ctx.strokeStyle = s.color; ctx.lineWidth = s.selected ? 2 : 1.3;
      ctx.beginPath(); ctx.arc(sx, sy, r, 0, TAU); ctx.stroke();
      ctx.fillStyle = s.color;
      ctx.beginPath(); ctx.arc(sx, sy, r * 0.42, 0, TAU); ctx.fill();
      if (s.selected) {
        ctx.strokeStyle = 'rgba(255,255,255,0.85)'; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(sx, sy, r * 1.9, 0, TAU); ctx.stroke();
      }
      this.hits.push({ id: 'sat:' + s.id, x: sx, y: sy, r: Math.max(14, r * 2.2), depth: s.depth - 1 });
      if (appear < 0.6) continue;
      // label pill
      const name = s.label.length > 22 ? s.label.slice(0, 21) + '…' : s.label;
      const nameW = this.measure(name, SAT_FONT);
      const subW = s.sub ? this.measure(s.sub, SAT_SUB_FONT) : 0;
      const w = Math.max(56, 18 + Math.max(nameW, subW));
      const h = s.sub ? 32 : 22;
      const right = sx >= hostTop.x;
      const rect = this.place(w, h, [
        { x: right ? sx + r + 6 : sx - r - 6 - w, y: sy - h / 2 },
        { x: sx - w / 2, y: sy - r - 6 - h },
        { x: sx - w / 2, y: sy + r + 6 },
        { x: right ? sx - r - 6 - w : sx + r + 6, y: sy - h / 2 },
      ], s.selected || s.hovered);
      if (!rect) continue;
      this.labelRects.push(rect);
      ctx.globalAlpha = Math.min(1, (appear - 0.6) / 0.4);
      roundRect(ctx, rect.x, rect.y, w, h, 8);
      ctx.fillStyle = dark ? 'rgba(27,18,27,0.9)' : 'rgba(255,255,255,0.94)';
      ctx.fill();
      ctx.strokeStyle = s.selected ? s.color : (dark ? '#4a3143' : '#d9c6d2'); ctx.lineWidth = 1; ctx.stroke();
      ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
      ctx.fillStyle = dark ? '#f7ecf2' : '#1d1219';
      ctx.font = SAT_FONT;
      ctx.fillText(name, rect.x + 9, rect.y + (s.sub ? 14 : 15));
      if (s.sub) { ctx.fillStyle = dark ? '#a99ba5' : '#5f4f5a'; ctx.font = SAT_SUB_FONT; ctx.fillText(s.sub, rect.x + 9, rect.y + 26); }
      this.hits.push({ id: 'sat:' + s.id, rect, depth: -2 });
    }
    ctx.globalAlpha = 1;
  }

  hitTest(px, py) {
    // Labels first (they are on top), then nearest nodes (drawn last = nearest).
    for (let i = this.hits.length - 1; i >= 0; i--) {
      const hit = this.hits[i];
      if (hit.rect) {
        if (px >= hit.rect.x && px <= hit.rect.x + hit.rect.w && py >= hit.rect.y && py <= hit.rect.y + hit.rect.h) return hit.id;
      }
    }
    let best = null, bestDepth = Infinity;
    for (const hit of this.hits) {
      if (hit.rect) continue;
      if (Math.hypot(hit.x - px, hit.y - py) <= hit.r && hit.depth < bestDepth) { best = hit.id; bestDepth = hit.depth; }
    }
    return best;
  }

  screenPosition(id) {
    const hit = this.hits.find(h => h.id === id && !h.rect);
    return hit ? { x: hit.x, y: hit.y, r: hit.r } : null;
  }
}
