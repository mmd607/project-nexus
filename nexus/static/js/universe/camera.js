// Orbit camera with a real perspective projection over a ground plane.
// World space: x → right, z → away from the viewer (on the plane), y → up.
const TAU = Math.PI * 2;
const lerp = (a, b, t) => a + (b - a) * t;

export class Camera {
  constructor() {
    this.yaw = 0; this.targetYaw = 0;
    this.pitch = 0.98; this.targetPitch = 0.98;   // elevation angle; π/2 = top-down
    this.zoom = 1; this.targetZoom = 1;
    this.panX = 0; this.panY = 0; this.targetPanX = 0; this.targetPanY = 0;
    this.focal = 1500;
    this.flat = false;
    this.width = 1; this.height = 1; this.base = 1;
    this.instant = false;
  }

  setViewport(width, height) {
    this.width = width; this.height = height;
    this.base = Math.min(width / 980, height / 760);
  }

  setFlat(flat) {
    this.flat = flat;
    this.targetPitch = flat ? Math.PI / 2 : 0.98;
  }

  /** Advance smoothing. Returns true while still animating. */
  update(dt) {
    const k = this.instant ? 1 : 1 - Math.pow(0.001, dt);   // ~ settle in a second
    const before = [this.yaw, this.pitch, this.zoom, this.panX, this.panY];
    this.yaw = lerp(this.yaw, this.targetYaw, k);
    this.pitch = lerp(this.pitch, this.targetPitch, k);
    this.zoom = lerp(this.zoom, this.targetZoom, k);
    this.panX = lerp(this.panX, this.targetPanX, k);
    this.panY = lerp(this.panY, this.targetPanY, k);
    if (this.instant) { this.yaw = this.targetYaw; this.pitch = this.targetPitch; this.zoom = this.targetZoom; this.panX = this.targetPanX; this.panY = this.targetPanY; this.instant = false; return false; }
    const eps = 1e-3;
    return Math.abs(before[0] - this.yaw) > eps || Math.abs(before[1] - this.pitch) > eps || Math.abs(before[2] - this.zoom) > 1e-4 ||
      Math.abs(before[3] - this.panX) > 0.05 || Math.abs(before[4] - this.panY) > 0.05;
  }

  /** Project a world point. Returns {x, y, f, depth}; f is the perspective/scale factor for sizes. */
  project(x, y, z) {
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
    const rx = x * cy - z * sy;
    const rz = x * sy + z * cy;
    const sp = Math.sin(this.pitch), cp = Math.cos(this.pitch);
    const depth = this.focal + rz * cp + y * sp;   // distance along the viewing axis
    // 3D uses true perspective; 2D is orthographic (flat, accessible). Blend while the pitch animates.
    const flatness = Math.max(0, Math.min(1, (this.pitch - 0.98) / (Math.PI / 2 - 0.98)));
    const persp = (this.focal / Math.max(200, depth)) * (1 - flatness) + flatness;
    const scale = this.base * this.zoom;
    const sx = rx * persp;
    const syy = (rz * sp - y * cp) * persp;
    return {
      x: this.width / 2 + this.panX + sx * scale,
      y: this.height / 2 + this.panY + syy * scale,
      f: persp * scale,
      depth,
    };
  }

  /** Screen offset of a world point from the viewport centre (with no pan). Used for pan-to-focus. */
  screenOffsetOf(x, z, y = 0) {
    const p = this.project(x, y, z);
    return { dx: p.x - this.width / 2, dy: p.y - this.height / 2 };
  }

  /** Pan so that the world point (x, y, z) lands in the viewport centre — at *zoom* (default: the zoom being animated to). */
  focusOn(x, z, zoom = this.targetZoom, y = 0) {
    const saved = [this.panX, this.panY, this.zoom, this.yaw, this.pitch];
    this.panX = 0; this.panY = 0; this.zoom = zoom; this.yaw = this.targetYaw; this.pitch = this.targetPitch;
    const { dx, dy } = this.screenOffsetOf(x, z, y);
    [this.panX, this.panY, this.zoom, this.yaw, this.pitch] = saved;
    this.targetPanX = -dx; this.targetPanY = -dy;
  }

  reset() {
    this.targetYaw = 0; this.targetZoom = 1; this.targetPanX = 0; this.targetPanY = 0;
  }

  zoomAt(factor, mx, my) {
    const next = Math.max(0.35, Math.min(3.5, this.targetZoom * factor));
    const ratio = next / this.targetZoom;
    const cx = this.width / 2, cyy = this.height / 2;
    this.targetPanX = (mx - cx) - ((mx - cx) - this.targetPanX) * ratio;
    this.targetPanY = (my - cyy) - ((my - cyy) - this.targetPanY) * ratio;
    this.targetZoom = next;
  }

  rotate(delta) { this.targetYaw = (this.targetYaw + delta) % TAU; this.yaw = this.yaw % TAU; }
}
