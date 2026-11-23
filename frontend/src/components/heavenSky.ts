/**
 * A heavenly sky for the Arcanjo: deep blue zenith fading into warm golden light behind him,
 * divine light rays from above, sun-lit cumulus clouds (pre-rendered sprites, cheap per frame),
 * a sea of clouds below and floating motes of light.
 */

interface CloudSprite {
  image: HTMLCanvasElement;
  x: number; // 0..1 of width (wraps)
  y: number; // 0..1 of height
  speed: number; // width-fraction per second
  alpha: number;
}

interface Mote {
  x: number;
  y: number;
  r: number;
  speed: number;
  phase: number;
}

function seeded(seed: number) {
  let s = Math.abs(Math.imul(seed + 1, 2654435761) ^ 0x5bd1e995) % 2147483647;
  if (s <= 0) s += 2147483646;
  const next = () => (s = (s * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 6; i++) next(); // decorrelate nearby seeds
  return next;
}

/** Draw one realistic cumulus: many overlapping billows of varied size inside a dome,
 * sun-lit from above with cool blue-grey undersides, soft edges and a faded base. */
function makeCloud(width: number, height: number, seed: number, blur: number): HTMLCanvasElement {
  const rand = seeded(seed);
  const pad = Math.ceil(height * 0.7);
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(width + pad * 2);
  canvas.height = Math.ceil(height + pad * 2);
  const c = canvas.getContext("2d");
  if (!c) return canvas;

  const baseY = pad + height;
  const puffs: { x: number; y: number; r: number }[] = [];
  const count = 34 + Math.floor(rand() * 18);
  for (let i = 0; i < count; i++) {
    const u = rand();
    const dome = Math.pow(Math.sin(u * Math.PI), 0.8); // taller towards the middle
    const x = pad + width * (0.04 + u * 0.92);
    const lift = Math.pow(rand(), 0.75) * dome * height * 0.85;
    const r = height * (0.1 + dome * 0.22 + rand() * 0.12) * (lift > height * 0.5 ? 0.85 : 1);
    puffs.push({ x, y: baseY - r * 0.55 - lift, r });
  }
  puffs.sort((a, b) => b.y - a.y); // lower billows first, upper ones on top

  c.filter = `blur(${blur}px)`;
  for (const p of puffs) {
    // Cool shadowed body
    const sh = c.createRadialGradient(p.x, p.y + p.r * 0.45, p.r * 0.15, p.x, p.y + p.r * 0.2, p.r * 1.08);
    sh.addColorStop(0, "rgba(158, 176, 206, 0.95)");
    sh.addColorStop(0.7, "rgba(186, 200, 224, 0.7)");
    sh.addColorStop(1, "rgba(200, 212, 232, 0)");
    c.fillStyle = sh;
    c.beginPath();
    c.arc(p.x, p.y + p.r * 0.2, p.r * 1.08, 0, Math.PI * 2);
    c.fill();
    // Sun-lit crown (light from above, slightly from the left)
    const lit = c.createRadialGradient(p.x - p.r * 0.25, p.y - p.r * 0.4, p.r * 0.05, p.x, p.y - p.r * 0.05, p.r * 0.98);
    lit.addColorStop(0, "rgba(255, 255, 255, 1)");
    lit.addColorStop(0.55, "rgba(253, 252, 250, 0.9)");
    lit.addColorStop(1, "rgba(250, 248, 246, 0)");
    c.fillStyle = lit;
    c.beginPath();
    c.arc(p.x, p.y - p.r * 0.05, p.r * 0.98, 0, Math.PI * 2);
    c.fill();
  }
  c.filter = "none";

  // Warm golden light on the upper edges
  c.globalCompositeOperation = "source-atop";
  const rim = c.createLinearGradient(0, pad - height * 0.2, 0, baseY);
  rim.addColorStop(0, "rgba(255, 222, 160, 0.38)");
  rim.addColorStop(0.5, "rgba(255, 240, 215, 0)");
  c.fillStyle = rim;
  c.fillRect(0, 0, canvas.width, canvas.height);

  // Fade the base so clouds dissolve into haze instead of having a hard flat bottom
  c.globalCompositeOperation = "destination-out";
  const fade = c.createLinearGradient(0, baseY - height * 0.35, 0, baseY + pad * 0.3);
  fade.addColorStop(0, "rgba(0,0,0,0)");
  fade.addColorStop(1, "rgba(0,0,0,0.85)");
  c.fillStyle = fade;
  c.fillRect(0, 0, canvas.width, canvas.height);
  c.globalCompositeOperation = "source-over";
  return canvas;
}

export function createHeavenSky() {
  let builtFor = "";
  let clouds: CloudSprite[] = [];
  const motes: Mote[] = Array.from({ length: 70 }, (_, i) => {
    const rand = seeded(1000 + i * 7);
    return { x: rand(), y: rand(), r: 0.6 + rand() * 1.8, speed: 0.004 + rand() * 0.01, phase: rand() * 6.28 };
  });

  const build = (w: number, h: number) => {
    const key = `${Math.round(w / 50)}x${Math.round(h / 50)}`;
    if (key === builtFor) return;
    builtFor = key;
    clouds = [];
    const layers = [
      // far, small, high
      { n: 7, yMin: 0.12, yMax: 0.42, wMin: 0.12, wMax: 0.22, speed: 0.0035, alpha: 0.72, blur: 3 },
      // mid
      { n: 5, yMin: 0.38, yMax: 0.62, wMin: 0.22, wMax: 0.34, speed: 0.006, alpha: 0.88, blur: 2 },
      // sea of clouds below
      { n: 8, yMin: 0.8, yMax: 0.98, wMin: 0.34, wMax: 0.5, speed: 0.009, alpha: 1, blur: 1.5 },
    ];
    let seed = 7;
    for (const layer of layers) {
      for (let i = 0; i < layer.n; i++) {
        const rand = seeded(seed++ * 97);
        const cw = w * (layer.wMin + rand() * (layer.wMax - layer.wMin));
        clouds.push({
          image: makeCloud(cw, cw * (0.36 + rand() * 0.14), seed * 31, layer.blur),
          x: (i / layer.n) * 1.3 - 0.15 + rand() * 0.1,
          y: layer.yMin + rand() * (layer.yMax - layer.yMin),
          speed: layer.speed * (0.7 + rand() * 0.6),
          alpha: layer.alpha,
        });
      }
    }
  };

  return function render(ctx: CanvasRenderingContext2D, w: number, h: number, time: number) {
    build(w, h);

    // Sky: deep blue zenith → soft blue → luminous warm white near the horizon
    const sky = ctx.createLinearGradient(0, 0, 0, h);
    sky.addColorStop(0, "#3f74b8");
    sky.addColorStop(0.32, "#82b3e2");
    sky.addColorStop(0.62, "#d7e9f8");
    sky.addColorStop(1, "#fff6e8");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, w, h);

    // Heavenly glow behind the Arcanjo
    const gx = w / 2;
    const gy = h * 0.45;
    const glow = ctx.createRadialGradient(gx, gy, 10, gx, gy, Math.max(w, h) * 0.6);
    glow.addColorStop(0, "rgba(255, 246, 222, 0.95)");
    glow.addColorStop(0.25, "rgba(255, 233, 196, 0.55)");
    glow.addColorStop(0.6, "rgba(255, 230, 200, 0.12)");
    glow.addColorStop(1, "rgba(255, 230, 200, 0)");
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);

    // Divine light rays from above
    ctx.save();
    ctx.globalCompositeOperation = "screen";
    const ox = w / 2;
    const oy = -h * 0.2;
    const len = h * 1.35;
    for (let i = 0; i < 13; i++) {
      const spread = (i - 6) * 0.105 + Math.sin(time * 0.12 + i * 1.7) * 0.025;
      const a = Math.PI / 2 + spread;
      const half = 0.022 + (i % 3) * 0.008;
      const strength = 0.1 + 0.08 * (0.5 + 0.5 * Math.sin(time * 0.35 + i));
      const ray = ctx.createLinearGradient(ox, oy, ox + Math.cos(a) * len, oy + Math.sin(a) * len);
      ray.addColorStop(0, `rgba(255, 250, 230, ${strength})`);
      ray.addColorStop(0.7, `rgba(255, 244, 220, ${strength * 0.4})`);
      ray.addColorStop(1, "rgba(255, 244, 220, 0)");
      ctx.fillStyle = ray;
      ctx.beginPath();
      ctx.moveTo(ox, oy);
      ctx.lineTo(ox + Math.cos(a - half) * len, oy + Math.sin(a - half) * len);
      ctx.lineTo(ox + Math.cos(a + half) * len, oy + Math.sin(a + half) * len);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();

    // Clouds (far → near)
    for (const cl of clouds) {
      const span = 1 + cl.image.width / w;
      const x = ((((cl.x + time * cl.speed) % span) + span) % span) * w - cl.image.width * 0.5;
      const y = cl.y * h - cl.image.height * 0.5 + Math.sin(time * 0.25 + cl.x * 9) * 3;
      ctx.globalAlpha = cl.alpha;
      ctx.drawImage(cl.image, x, y);
    }
    ctx.globalAlpha = 1;

    // Floating motes of light
    for (const m of motes) {
      const y = (((m.y - time * m.speed) % 1) + 1) % 1;
      const x = m.x + Math.sin(time * 0.3 + m.phase) * 0.01;
      const tw = 0.35 + 0.65 * Math.abs(Math.sin(time * 1.3 + m.phase));
      ctx.fillStyle = `rgba(255, 244, 210, ${0.55 * tw})`;
      ctx.beginPath();
      ctx.arc(x * w, y * h, m.r, 0, Math.PI * 2);
      ctx.fill();
    }
  };
}
