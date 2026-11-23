import { useEffect, useRef } from "react";
import type { AssistantState, FaceMood, MusicState } from "../types/api";

/**
 * Arcanjo: interlocking rose-gold rings covered in eyes orbiting a giant blue eye
 * (the "biblically accurate" Ophanim look), rendered in real-time 3D on a canvas.
 *
 * It is alive: the central eye blinks, follows the pointer and dilates when listening;
 * rings speed up while thinking, glow while speaking and the whole being dances to music.
 */

interface ArchangelCoreProps {
  state: AssistantState;
  mood?: FaceMood;
  speechEnergy?: number;
  music?: MusicState;
  size?: number;
  onClick?: () => void;
}

interface Ring {
  radius: number;
  band: number;
  tiltX: number;
  tiltY: number;
  speedX: number;
  speedY: number;
  speedZ: number;
  phase: number;
}

interface DrawItem {
  z: number;
  draw: (ctx: CanvasRenderingContext2D) => void;
}

// Armillary layout like the reference: one wide near-horizontal ring and two crossing
// near-vertical rings around the eye. Thick, chunky chain bands.
const RINGS: Ring[] = [
  { radius: 1.0, band: 0.15, tiltX: 1.3, tiltY: 0.0, speedX: 0.0, speedY: 0.0, speedZ: 0.16, phase: 0.2 },
  { radius: 0.84, band: 0.14, tiltX: 0.15, tiltY: 1.15, speedX: 0.13, speedY: 0.04, speedZ: 0.0, phase: 0.6 },
  { radius: 0.7, band: 0.13, tiltX: 0.25, tiltY: -0.55, speedX: -0.08, speedY: 0.15, speedZ: 0.03, phase: 2.4 },
];
const SEGMENTS = 140;
const EYE_EVERY = 4; // one small eye every N segments
const FOCAL = 3.2;
// Global spin multiplier (the reference video turns briskly: ~1 full turn every few seconds)
const SPIN = 4.2;

type Vec3 = [number, number, number];

function rotate([x, y, z]: Vec3, ax: number, ay: number, az: number): Vec3 {
  // X
  let y1 = y * Math.cos(ax) - z * Math.sin(ax);
  let z1 = y * Math.sin(ax) + z * Math.cos(ax);
  // Y
  const x2 = x * Math.cos(ay) + z1 * Math.sin(ay);
  const z2 = -x * Math.sin(ay) + z1 * Math.cos(ay);
  // Z
  const x3 = x2 * Math.cos(az) - y1 * Math.sin(az);
  y1 = x2 * Math.sin(az) + y1 * Math.cos(az);
  z1 = z2;
  return [x3, y1, z1];
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/** A small realistic eye set into the ring: almond-shaped along the band, with shaded sclera,
 * fibrous iris, pupil, catchlight, pink eyelids and a lash line. */
function drawRingEye(
  c: CanvasRenderingContext2D,
  pp: { x: number; y: number; s: number },
  ta: { x: number; y: number },
  tb: { x: number; y: number },
  baseR: number,
  facing: number,
  blink: boolean,
  gazeX: number,
  gazeY: number,
  glow: number,
) {
  const r = baseR * pp.s;
  if (r < 1.2) return;
  const angle = Math.atan2(tb.y - ta.y, tb.x - ta.x);
  const W = r * 1.15; // half-width along the band
  const H = r * 0.62 * Math.max(0.25, facing) * (blink ? 0.08 : 1); // half-height
  c.save();
  c.translate(pp.x, pp.y);
  c.rotate(angle);

  const almond = (w: number, h: number) => {
    c.beginPath();
    c.moveTo(-w, 0);
    c.quadraticCurveTo(0, -h * 1.45, w, 0);
    c.quadraticCurveTo(0, h * 1.45, -w, 0);
    c.closePath();
  };

  // Eyelid skin rim
  const lid = c.createLinearGradient(0, -H * 1.6, 0, H * 1.6);
  lid.addColorStop(0, "#d99485");
  lid.addColorStop(0.5, "#f2bfb0");
  lid.addColorStop(1, "#e3a596");
  c.fillStyle = lid;
  almond(W * 1.28, Math.max(H, 0.6) * 1.35 + r * 0.12);
  c.fill();

  if (!blink) {
    almond(W, H);
    c.save();
    c.clip();
    // Sclera with soft shading towards the corners
    const sclera = c.createRadialGradient(0, -H * 0.2, r * 0.1, 0, 0, W * 1.05);
    sclera.addColorStop(0, "#ffffff");
    sclera.addColorStop(0.65, "#f4ece8");
    sclera.addColorStop(1, "#cdb3ab");
    c.fillStyle = sclera;
    c.fillRect(-W, -H * 1.6, W * 2, H * 3.2);

    // Iris
    const ix = gazeX * W * 0.32;
    const iy = gazeY * H * 0.25;
    const IR = r * 0.56;
    const iris = c.createRadialGradient(ix, iy, IR * 0.12, ix, iy, IR);
    iris.addColorStop(0, "#a9dcff");
    iris.addColorStop(0.4, `rgb(${Math.round(70 + glow * 50)}, ${Math.round(150 + glow * 40)}, 222)`);
    iris.addColorStop(0.82, "#25679f");
    iris.addColorStop(1, "#0f3456");
    c.fillStyle = iris;
    c.beginPath();
    c.arc(ix, iy, IR, 0, Math.PI * 2);
    c.fill();
    // Fibres
    if (IR > 3) {
      c.strokeStyle = "rgba(225, 242, 255, 0.3)";
      c.lineWidth = Math.max(0.5, IR * 0.04);
      for (let f = 0; f < 18; f++) {
        const a = (f / 18) * Math.PI * 2;
        c.beginPath();
        c.moveTo(ix + Math.cos(a) * IR * 0.45, iy + Math.sin(a) * IR * 0.45);
        c.lineTo(ix + Math.cos(a) * IR * 0.92, iy + Math.sin(a) * IR * 0.92);
        c.stroke();
      }
    }
    // Pupil
    c.fillStyle = "#04070c";
    c.beginPath();
    c.arc(ix, iy, IR * 0.42, 0, Math.PI * 2);
    c.fill();
    // Upper-lid shadow over the eyeball (depth)
    const shadow = c.createLinearGradient(0, -H * 1.3, 0, H * 0.2);
    shadow.addColorStop(0, "rgba(110, 60, 52, 0.45)");
    shadow.addColorStop(1, "rgba(110, 60, 52, 0)");
    c.fillStyle = shadow;
    c.fillRect(-W, -H * 1.6, W * 2, H * 1.8);
    // Catchlight
    c.fillStyle = "rgba(255, 255, 255, 0.92)";
    c.beginPath();
    c.arc(ix - IR * 0.32, iy - IR * 0.34, Math.max(0.6, IR * 0.17), 0, Math.PI * 2);
    c.fill();
    c.restore();

    // Lash line along the upper lid
    c.strokeStyle = "rgba(70, 36, 30, 0.7)";
    c.lineWidth = Math.max(0.6, r * 0.1);
    c.beginPath();
    c.moveTo(-W, 0);
    c.quadraticCurveTo(0, -H * 1.45, W, 0);
    c.stroke();
  } else {
    // Closed eye: just the lash line
    c.strokeStyle = "rgba(70, 36, 30, 0.7)";
    c.lineWidth = Math.max(0.6, r * 0.1);
    c.beginPath();
    c.moveTo(-W, 0);
    c.quadraticCurveTo(0, r * 0.15, W, 0);
    c.stroke();
  }
  c.restore();
}

export function ArchangelCore({
  state,
  mood = "neutral",
  speechEnergy = 0,
  music,
  size = 440,
  onClick,
}: ArchangelCoreProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const live = useRef({ state, mood, speechEnergy, music });
  live.current = { state, mood, speechEnergy, music };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const pointer = { x: 0, y: 0, until: 0 };
    const onMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = Math.max(-1, Math.min(1, (e.clientX - (rect.left + rect.width / 2)) / (window.innerWidth / 2)));
      pointer.y = Math.max(-1, Math.min(1, (e.clientY - (rect.top + rect.height / 2)) / (window.innerHeight / 2)));
      pointer.until = performance.now() + 2500;
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    const sim = {
      angle: 0, // accumulated ring rotation time (speed varies with state)
      gazeX: 0,
      gazeY: 0,
      targetGX: 0,
      targetGY: 0,
      nextSaccade: 0,
      pupil: 0.42,
      lid: 0,
      blinkUntil: 0,
      nextBlink: performance.now() + 2500,
      glow: 0,
      bob: 0,
    };
    let last = performance.now();
    let raf = 0;

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const { state: st, mood: md, speechEnergy: energy, music: mu } = live.current;
      const dancing = Boolean(mu?.playing && mu.bpm > 0);
      const sec = now / 1000;

      // ---------- behaviour ----------
      let speed = 1;
      if (st === "processing" || st === "executing") speed = 3.2;
      else if (st === "speaking") speed = 1.6;
      else if (st === "listening") speed = 0.55;
      if (dancing) speed = Math.max(speed, (mu!.bpm / 60) * 0.6);
      sim.angle += dt * speed * SPIN;

      if (now >= sim.nextSaccade) {
        sim.targetGX = (Math.random() - 0.5) * 0.9;
        sim.targetGY = (Math.random() - 0.5) * 0.6;
        sim.nextSaccade = now + (st === "processing" ? 450 : 1600) + Math.random() * 1800;
      }
      let gx = sim.targetGX;
      let gy = sim.targetGY;
      if (now < pointer.until) {
        gx = pointer.x;
        gy = pointer.y;
      }
      if (st === "listening" || st === "speaking") {
        gx *= 0.25; // looks straight at you
        gy *= 0.25;
      }
      if (st === "processing") {
        gx = 0.75 * Math.cos(sec * 1.7);
        gy = -0.55;
      }
      sim.gazeX = lerp(sim.gazeX, gx, 0.12);
      sim.gazeY = lerp(sim.gazeY, gy, 0.12);

      const targetPupil = st === "listening" ? 0.55 : st === "speaking" ? 0.46 + energy * 0.12 : md === "surprised" ? 0.3 : 0.42;
      sim.pupil = lerp(sim.pupil, targetPupil, 0.08);

      if (now >= sim.nextBlink) {
        sim.blinkUntil = now + 150;
        sim.nextBlink = now + 2600 + Math.random() * 3600;
      }
      let targetLid = md === "tired" ? 0.45 : md === "sad" ? 0.3 : dancing ? 0.25 : 0;
      if (now < sim.blinkUntil) targetLid = 1;
      sim.lid = lerp(sim.lid, targetLid, now < sim.blinkUntil ? 0.6 : 0.15);

      const targetGlow = st === "speaking" ? 0.55 + energy * 0.45 : st === "listening" ? 0.35 : st === "processing" ? 0.45 : 0.12;
      sim.glow = lerp(sim.glow, targetGlow, 0.1);
      const targetBob = dancing ? Math.abs(Math.sin(Math.PI * sec * (mu!.bpm / 60))) * -10 : Math.sin(sec * 0.9) * 4;
      sim.bob = lerp(sim.bob, targetBob, dancing ? 0.35 : 0.08);

      // ---------- render ----------
      ctx.clearRect(0, 0, size, size);
      const cx = size / 2;
      const cy = size / 2 + sim.bob;
      const scale = size * 0.4;
      const items: DrawItem[] = [];

      // Holy glow behind everything
      const halo = ctx.createRadialGradient(cx, cy, scale * 0.1, cx, cy, scale * 1.35);
      halo.addColorStop(0, `rgba(255, 244, 236, ${0.55 + sim.glow * 0.4})`);
      halo.addColorStop(0.5, `rgba(255, 214, 196, ${0.18 + sim.glow * 0.25})`);
      halo.addColorStop(1, "rgba(255, 255, 255, 0)");
      ctx.fillStyle = halo;
      ctx.fillRect(0, 0, size, size);

      const project = (p: Vec3) => {
        const s = FOCAL / (FOCAL + p[2]);
        return { x: cx + p[0] * scale * s, y: cy + p[1] * scale * s, s };
      };

      RINGS.forEach((ring, ri) => {
        const ax = ring.tiltX + sim.angle * ring.speedX + Math.sin(sim.angle * 0.3 + ring.phase) * 0.15;
        const ay = ring.tiltY + sim.angle * ring.speedY;
        const az = ring.phase + sim.angle * ring.speedZ;
        for (let k = 0; k < SEGMENTS; k++) {
          const t0 = (k / SEGMENTS) * Math.PI * 2;
          const t1 = ((k + 1) / SEGMENTS) * Math.PI * 2;
          const p0 = rotate([Math.cos(t0) * ring.radius, Math.sin(t0) * ring.radius, 0], ax, ay, az);
          const p1 = rotate([Math.cos(t1) * ring.radius, Math.sin(t1) * ring.radius, 0], ax, ay, az);
          const zMid = (p0[2] + p1[2]) / 2;
          // Ring plane normal → how much this part of the band faces the camera (shading)
          const n = rotate([0, 0, 1], ax, ay, az);
          const facing = Math.abs(n[2]);
          const depthShade = 0.75 + (0.25 * (1 - zMid)) / 2;
          const link = k % 2 === 0;
          items.push({
            z: zMid,
            draw: (c) => {
              const a = project(p0);
              const b = project(p1);
              const w = ring.band * scale * ((a.s + b.s) / 2) * (0.85 + facing * 0.15);
              const shade = depthShade * (0.9 + facing * 0.1);
              const tone = (r: number, g: number, bl: number) =>
                `rgb(${Math.round(r * shade)}, ${Math.round(g * shade)}, ${Math.round(bl * shade)})`;
              c.lineCap = "butt";
              // Extend each segment a little so neighbours overlap (smooth band, no gaps)
              const ex = (b.x - a.x) * 0.18;
              const ey = (b.y - a.y) * 0.18;
              a.x -= ex;
              a.y -= ey;
              b.x += ex;
              b.y += ey;
              // Soft rim -> light rose-gold body -> bright metallic highlight (cylinder look)
              c.strokeStyle = tone(204, 140, 124);
              c.lineWidth = w;
              c.beginPath();
              c.moveTo(a.x, a.y);
              c.lineTo(b.x, b.y);
              c.stroke();
              c.strokeStyle = link ? tone(246, 200, 182) : tone(238, 186, 166);
              c.lineWidth = w * 0.74;
              c.beginPath();
              c.moveTo(a.x, a.y);
              c.lineTo(b.x, b.y);
              c.stroke();
              c.strokeStyle = `rgba(255, 246, 240, ${0.75 * shade + sim.glow * 0.25})`;
              c.lineWidth = w * 0.22;
              c.beginPath();
              c.moveTo(a.x, a.y - w * 0.2);
              c.lineTo(b.x, b.y - w * 0.2);
              c.stroke();
              // Chain links: small dark cross-bars every other segment
              if (link) {
                const dx = b.x - a.x;
                const dy = b.y - a.y;
                const len = Math.hypot(dx, dy) || 1;
                const nx = (-dy / len) * w * 0.36;
                const ny = (dx / len) * w * 0.36;
                c.strokeStyle = `rgba(168, 104, 90, ${0.38 * shade})`;
                c.lineWidth = Math.max(1, w * 0.07);
                c.beginPath();
                c.moveTo(a.x + nx, a.y + ny);
                c.lineTo(a.x - nx, a.y - ny);
                c.stroke();
              }
            },
          });
          if (k % EYE_EVERY === ri % EYE_EVERY) {
            const tm = (t0 + t1) / 2;
            const pe = rotate([Math.cos(tm) * ring.radius, Math.sin(tm) * ring.radius, 0], ax, ay, az);
            const radial = rotate([Math.cos(tm), Math.sin(tm), 0], ax, ay, az);
            // Eyes sit on the outer face of the band; visible when that face turns to us
            const eyeFacing = Math.max(facing * 0.8, -radial[2]);
            if (eyeFacing > 0.08) {
              const blinkSmall = Math.sin(sec * 0.7 + k * 1.3 + ri) > 0.985;
              const tA = rotate([Math.cos(tm - 0.05) * ring.radius, Math.sin(tm - 0.05) * ring.radius, 0], ax, ay, az);
              const tB = rotate([Math.cos(tm + 0.05) * ring.radius, Math.sin(tm + 0.05) * ring.radius, 0], ax, ay, az);
              items.push({
                z: pe[2] - 0.01,
                draw: (c) => drawRingEye(c, project(pe), project(tA), project(tB), ring.band * scale * 0.34, eyeFacing, blinkSmall, sim.gazeX, sim.gazeY, sim.glow),
              });
            }
          }
        }
      });

      // Central giant eye (z = 0 sorts it between the back and front halves of the rings)
      items.push({
        z: 0,
        draw: (c) => {
          const R = scale * 0.33;
          // Fleshy rose membrane around the eye
          const membrane = c.createRadialGradient(cx, cy, R * 0.85, cx, cy, R * 1.45);
          membrane.addColorStop(0, "rgba(236, 168, 160, 0.95)");
          membrane.addColorStop(1, "rgba(250, 218, 206, 0)");
          c.fillStyle = membrane;
          c.beginPath();
          c.ellipse(cx, cy, R * 1.45, R * 1.3, 0, 0, Math.PI * 2);
          c.fill();

          // Eyeball
          const ball = c.createRadialGradient(cx - R * 0.3, cy - R * 0.35, R * 0.1, cx, cy, R);
          ball.addColorStop(0, "#ffffff");
          ball.addColorStop(0.7, "#f1ece9");
          ball.addColorStop(1, "#cdbdb7");
          c.fillStyle = ball;
          c.beginPath();
          c.arc(cx, cy, R, 0, Math.PI * 2);
          c.fill();

          // Iris
          const ix = cx + sim.gazeX * R * 0.38;
          const iy = cy + sim.gazeY * R * 0.32;
          const IR = R * 0.5;
          const iris = c.createRadialGradient(ix, iy, IR * 0.1, ix, iy, IR);
          iris.addColorStop(0, "#9ed6ff");
          iris.addColorStop(0.45, `rgb(${Math.round(56 + sim.glow * 60)}, ${Math.round(140 + sim.glow * 50)}, 214)`);
          iris.addColorStop(0.85, "#1f5f99");
          iris.addColorStop(1, "#123a5e");
          c.fillStyle = iris;
          c.beginPath();
          c.arc(ix, iy, IR, 0, Math.PI * 2);
          c.fill();
          // Iris fibres
          c.strokeStyle = "rgba(220, 240, 255, 0.28)";
          c.lineWidth = 1;
          for (let f = 0; f < 36; f++) {
            const ang = (f / 36) * Math.PI * 2 + sec * 0.05;
            c.beginPath();
            c.moveTo(ix + Math.cos(ang) * IR * sim.pupil * 1.05, iy + Math.sin(ang) * IR * sim.pupil * 1.05);
            c.lineTo(ix + Math.cos(ang) * IR * 0.92, iy + Math.sin(ang) * IR * 0.92);
            c.stroke();
          }
          // Pupil
          c.fillStyle = "#05080d";
          c.beginPath();
          c.arc(ix, iy, IR * sim.pupil, 0, Math.PI * 2);
          c.fill();
          // Catchlights
          c.fillStyle = "rgba(255,255,255,0.9)";
          c.beginPath();
          c.arc(ix - IR * 0.32, iy - IR * 0.36, IR * 0.14, 0, Math.PI * 2);
          c.fill();
          c.fillStyle = "rgba(255,255,255,0.45)";
          c.beginPath();
          c.arc(ix + IR * 0.25, iy + IR * 0.28, IR * 0.06, 0, Math.PI * 2);
          c.fill();

          // Eyelids (blink / tired / blissful while dancing)
          if (sim.lid > 0.02) {
            c.fillStyle = "#e9b3a6";
            c.save();
            c.beginPath();
            c.arc(cx, cy, R * 1.02, 0, Math.PI * 2);
            c.clip();
            const lidY = cy - R + sim.lid * R * 1.15;
            c.fillRect(cx - R * 1.1, cy - R * 1.1, R * 2.2, lidY - (cy - R * 1.1));
            const lowY = cy + R - sim.lid * R * 0.85;
            c.fillRect(cx - R * 1.1, lowY, R * 2.2, cy + R * 1.1 - lowY);
            c.restore();
          }
        },
      });

      items.sort((a, b) => b.z - a.z); // far (large z) first
      for (const item of items) item.draw(ctx);

      raf = window.requestAnimationFrame(tick);
    };
    tick(performance.now()); // first frame right away
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
    };
  }, [size]);

  return (
    <button
      type="button"
      onClick={onClick}
      title={`Arcanjo · ${state}`}
      className="relative cursor-pointer rounded-full focus:outline-none"
      style={{ width: size, height: size }}
    >
      <canvas ref={canvasRef} style={{ width: size, height: size }} />
    </button>
  );
}

/** The tiny figure on a cliff, giving the colossal scale seen in the video. */
export function CliffWithFigure() {
  return (
    <svg
      viewBox="0 0 400 120"
      className="pointer-events-none fixed bottom-0 left-1/2 z-10 w-[min(420px,70vw)] -translate-x-1/2 opacity-90"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="cliff" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f3f1ef" />
          <stop offset="1" stopColor="#b9b4b0" />
        </linearGradient>
      </defs>
      <path d="M120 120 L132 78 Q150 66 190 70 L262 68 Q284 72 290 92 L300 120 Z" fill="url(#cliff)" />
      <path d="M140 80 Q170 74 200 76 L250 74" stroke="#d7d2ce" strokeWidth="2" fill="none" />
      {/* person */}
      <g fill="#3b3a3a">
        <circle cx="196" cy="47" r="2.6" />
        <rect x="194.2" y="50" width="3.6" height="10" rx="1.4" />
        <rect x="194.4" y="59.5" width="1.4" height="9" />
        <rect x="196.2" y="59.5" width="1.4" height="9" />
      </g>
    </svg>
  );
}
