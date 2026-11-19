// Deterministic orbital layout: every project is a full node on rings around the hub —
// one node per top-level folder (plus the sub-folders the user promoted, which sit right next to
// their parent and stay linked to it). Positions depend only on the set of ids (stable hashing),
// so nothing jumps between rescans. Internal parts of a focused project are laid out separately
// by focusLayout() and are never permanent nodes.
const TAU = Math.PI * 2;
export const RING_RADII = [110, 200, 285, 370, 455, 540];
export const NODE_R = 30;         // top-level project crystal radius (world units)
export const PROMOTED_R = 24;     // promoted sub-project crystal radius

export function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) / 4294967296;
}

/**
 * Ring plan for n nodes: how many orbits, and how wide, so that neighbouring labels have room.
 * Labels are ~150–190 px wide at zoom 1, so nodes on the same ring keep ≥ minArc world units apart.
 */
export function ringPlan(n) {
  const rings = n <= 9 ? 1 : n <= 22 ? 2 : n <= 48 ? 3 : n <= 110 ? 4 : 5;
  const perRing = Math.ceil(Math.max(1, n) / rings);
  const minArc = 180;
  const rBase = Math.max(250, Math.round((minArc * perRing) / TAU));
  const rGap = n <= 48 ? 96 : 84;
  return { rings, rBase, rGap, radii: Array.from({ length: rings }, (_, i) => rBase + i * rGap) };
}

/**
 * @param projects  all projects (not just visible)
 * @param opts      { cluster: boolean }
 * @returns Map<id, {x, y, z, r, angle, ring, parentId, depth}>
 */
export function computeLayout(projects, opts = {}) {
  const byId = new Map(projects.map(p => [p.id, p]));
  const positions = new Map();
  const n = projects.length;
  if (!n) return positions;

  const cluster = opts.cluster ?? n > 24;
  const { rings, rBase, rGap } = ringPlan(n);
  const top = projects.filter(p => !p.parent_id || !byId.has(p.parent_id));
  const children = new Map();
  for (const p of projects) {
    if (p.parent_id && byId.has(p.parent_id)) {
      if (!children.has(p.parent_id)) children.set(p.parent_id, []);
      children.get(p.parent_id).push(p);
    }
  }

  // Order: cluster by category (largest first) or by stable hash for a natural spread.
  let orderedTop;
  if (cluster) {
    const groups = new Map();
    for (const p of top) {
      const key = p.categories[0] || 'Other';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(p);
    }
    const sortedGroups = [...groups.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
    orderedTop = [];
    for (const [, items] of sortedGroups) orderedTop.push(...items.sort((a, b) => hash(a.id) - hash(b.id)));
  } else {
    orderedTop = [...top].sort((a, b) => hash(a.id) - hash(b.id));
  }
  // Promoted sub-projects follow their parent so they end up as angular neighbours (recursively).
  const ordered = [];
  const push = p => {
    ordered.push(p);
    for (const c of (children.get(p.id) || []).sort((a, b) => a.display_name.localeCompare(b.display_name))) push(c);
  };
  for (const p of orderedTop) push(p);

  // Alternate rings along the order (neighbours never share a radius), then spread each ring evenly
  // around its own circle with a small phase shift so the rings interleave.
  const perRing = Array.from({ length: rings }, () => []);
  ordered.forEach((p, i) => perRing[rings === 1 ? 0 : i % rings].push(p));
  const slot = TAU / Math.max(...perRing.map(r => r.length));   // one angular grid for every ring keeps parents and promoted children aligned
  perRing.forEach((nodes, ring) => {
    const phase = rings === 1 ? 0 : (ring / rings) * slot;
    nodes.forEach((p, k) => {
      const parentId = p.parent_id && byId.has(p.parent_id) ? p.parent_id : null;
      const jitter = (hash(p.id + ':r') - 0.5) * (rings === 1 ? 36 : 18);
      const radius = rBase + ring * rGap + jitter;
      const angle = -Math.PI / 2 + phase + k * slot + (hash(p.id + ':a') - 0.5) * slot * 0.12;
      const y = (hash(p.id + ':y') - 0.5) * 26;
      positions.set(p.id, {
        x: Math.cos(angle) * radius, y, z: Math.sin(angle) * radius, r: parentId ? PROMOTED_R : NODE_R, angle, ring,
        parentId, depth: parentId ? 1 : 0,
      });
    });
  });
  return positions;
}

/** Ring radii that make sense for the current node count (drawn as orbits). */
export function ringsFor(n) {
  const plan = ringPlan(n);
  return n <= 9 ? [110, plan.rBase] : [110, ...plan.radii];
}

/**
 * Positions for the internal parts (satellites) shown around a focused project.
 * They orbit the node on a small circle, starting on the side facing away from the hub so the
 * link to the hub stays clear. Deterministic for a given (node, count).
 * @returns Array<{x, y, z, angle}>
 */
export function focusLayout(center, count) {
  const out = [];
  if (!count) return out;
  const orbit = 92 + Math.min(44, count * 4);
  const away = Math.atan2(center.z, center.x);   // direction from the hub through the node
  for (let i = 0; i < count; i++) {
    const a = away + Math.PI / 2 + ((i + 0.5) / count) * TAU;   // spread all the way round
    out.push({ x: center.x + Math.cos(a) * orbit, y: center.y + 4 + (i % 2) * 10, z: center.z + Math.sin(a) * orbit, angle: a });
  }
  return out;
}

/** Bounding radius of a layout (world units), used to fit the whole universe into the viewport. */
export function layoutRadius(positions) {
  let r = 0;
  for (const p of positions.values()) r = Math.max(r, Math.hypot(p.x, p.z) + (p.r || NODE_R) * 1.5);
  return r;
}
