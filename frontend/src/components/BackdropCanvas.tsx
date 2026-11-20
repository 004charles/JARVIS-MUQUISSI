import { useEffect, useRef } from "react";

export type BackdropTheme = "clouds" | "galaxy" | "aurora";

interface BackdropCanvasProps {
  theme: BackdropTheme;
}

interface CloudPuff {
  x: number;
  y: number;
  rx: number;
  ry: number;
  speed: number;
  alpha: number;
}

interface Star {
  x: number;
  y: number;
  size: number;
  alpha: number;
  twinkleSpeed: number;
  phase: number;
}

interface GalaxyParticle {
  angle: number;
  radius: number;
  armOffset: number;
  speed: number;
  size: number;
  hue: number;
  alpha: number;
}

export function BackdropCanvas({ theme }: BackdropCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const themeRef = useRef(theme);
  themeRef.current = theme;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationId = 0;
    let width = window.innerWidth;
    let height = window.innerHeight;
    let dpr = Math.min(window.devicePixelRatio || 1, 2);

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();

    const clouds: CloudPuff[] = Array.from({ length: 24 }, (_, idx) => ({
      x: Math.random() * 1.4 - 0.2,
      y: 0.08 + (idx % 6) * 0.16 + (Math.random() - 0.5) * 0.08,
      rx: 150 + Math.random() * 240,
      ry: 55 + Math.random() * 85,
      speed: 0.00008 + Math.random() * 0.00016,
      alpha: 0.45 + Math.random() * 0.42,
    }));

    const stars: Star[] = Array.from({ length: 150 }, () => ({
      x: Math.random(),
      y: Math.random(),
      size: Math.random() * 1.6 + 0.4,
      alpha: Math.random() * 0.65 + 0.2,
      twinkleSpeed: Math.random() * 0.02 + 0.005,
      phase: Math.random() * Math.PI * 2,
    }));

    const armCount = 3;
    const galaxyParticles: GalaxyParticle[] = Array.from({ length: 260 }, (_, idx) => {
      const arm = idx % armCount;
      const dist = Math.pow(Math.random(), 0.72);
      return {
        angle: (arm * (Math.PI * 2)) / armCount + dist * 4.2 + (Math.random() - 0.5) * 0.65,
        radius: 0.06 + dist * 0.48,
        armOffset: (Math.random() - 0.5) * 26,
        speed: 0.00045 + (1 - dist) * 0.0009,
        size: Math.random() * 2.1 + 0.6,
        hue: Math.random() > 0.35 ? 195 + Math.random() * 25 : 225 + Math.random() * 25,
        alpha: (1 - dist * 0.65) * (Math.random() * 0.45 + 0.25),
      };
    });

    let tick = 0;

    const renderClouds = () => {
      const skyGrad = ctx.createLinearGradient(0, 0, 0, height);
      skyGrad.addColorStop(0, "#e6f2ff");
      skyGrad.addColorStop(0.45, "#f7fbff");
      skyGrad.addColorStop(1, "#ffffff");
      ctx.fillStyle = skyGrad;
      ctx.fillRect(0, 0, width, height);

      // Soft luminous atmospheric halo in the center
      const sunHalo = ctx.createRadialGradient(
        width * 0.5,
        height * 0.48,
        20,
        width * 0.5,
        height * 0.48,
        Math.min(width, height) * 0.55,
      );
      sunHalo.addColorStop(0, "rgba(255, 255, 255, 0.96)");
      sunHalo.addColorStop(0.55, "rgba(186, 230, 253, 0.28)");
      sunHalo.addColorStop(1, "rgba(255, 255, 255, 0)");
      ctx.fillStyle = sunHalo;
      ctx.fillRect(0, 0, width, height);

      // Volumetric drifting clouds
      for (const puff of clouds) {
        puff.x += puff.speed;
        if (puff.x > 1.25) puff.x = -0.25;

        const cx = puff.x * width;
        const cy = puff.y * height + Math.sin(tick * 0.008 + puff.rx) * 6;

        ctx.save();
        ctx.translate(cx, cy);
        ctx.scale(1, puff.ry / puff.rx);
        const grad = ctx.createRadialGradient(0, 0, puff.rx * 0.1, 0, 0, puff.rx);
        grad.addColorStop(0, `rgba(255, 255, 255, ${puff.alpha})`);
        grad.addColorStop(0.55, `rgba(240, 249, 255, ${puff.alpha * 0.65})`);
        grad.addColorStop(1, "rgba(224, 242, 254, 0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(0, 0, puff.rx, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    };

    const renderGalaxy = () => {
      const bgGrad = ctx.createRadialGradient(
        width * 0.5,
        height * 0.48,
        20,
        width * 0.5,
        height * 0.5,
        Math.max(width, height) * 0.85,
      );
      bgGrad.addColorStop(0, "#081b3a");
      bgGrad.addColorStop(0.42, "#040c1f");
      bgGrad.addColorStop(1, "#01030a");
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, width, height);

      const cx = width * 0.5;
      const cy = height * 0.5;
      const maxRadius = Math.min(width, height) * 0.95;

      const nebulaA = ctx.createRadialGradient(cx, cy, 10, cx, cy, maxRadius * 0.48);
      nebulaA.addColorStop(0, "rgba(34, 211, 238, 0.16)");
      nebulaA.addColorStop(0.4, "rgba(37, 99, 235, 0.10)");
      nebulaA.addColorStop(1, "rgba(2, 6, 23, 0)");
      ctx.fillStyle = nebulaA;
      ctx.fillRect(0, 0, width, height);

      for (const s of stars) {
        const twinkle = 0.55 + 0.45 * Math.sin(tick * s.twinkleSpeed + s.phase);
        ctx.fillStyle = `rgba(207, 250, 254, ${s.alpha * twinkle})`;
        ctx.beginPath();
        ctx.arc(s.x * width, s.y * height, s.size, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(-0.24);
      ctx.scale(1.18, 0.72);
      for (const p of galaxyParticles) {
        p.angle += p.speed;
        const r = p.radius * maxRadius;
        const px = Math.cos(p.angle) * r + p.armOffset;
        const py = Math.sin(p.angle) * r + p.armOffset * 0.4;
        ctx.fillStyle = `hsla(${p.hue}, 92%, 68%, ${p.alpha})`;
        ctx.beginPath();
        ctx.arc(px, py, p.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    };

    const renderAurora = () => {
      const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
      bgGrad.addColorStop(0, "#020617");
      bgGrad.addColorStop(0.5, "#061830");
      bgGrad.addColorStop(1, "#030b1a");
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, width, height);

      for (let band = 0; band < 3; band++) {
        ctx.beginPath();
        const baseY = height * (0.35 + band * 0.14);
        ctx.moveTo(0, height);
        for (let x = 0; x <= width; x += 24) {
          const wave =
            Math.sin(x * 0.004 + tick * 0.012 + band * 1.6) * 48 +
            Math.cos(x * 0.009 - tick * 0.008) * 24;
          ctx.lineTo(x, baseY + wave);
        }
        ctx.lineTo(width, height);
        ctx.closePath();
        const grad = ctx.createLinearGradient(0, baseY - 70, 0, height);
        grad.addColorStop(0, band === 1 ? "rgba(52, 211, 153, 0.16)" : "rgba(56, 189, 248, 0.14)");
        grad.addColorStop(1, "rgba(2, 6, 23, 0)");
        ctx.fillStyle = grad;
        ctx.fill();
      }
    };

    const render = () => {
      tick += 1;
      ctx.clearRect(0, 0, width, height);

      if (themeRef.current === "clouds") {
        renderClouds();
      } else if (themeRef.current === "aurora") {
        renderAurora();
      } else {
        renderGalaxy();
      }

      animationId = window.requestAnimationFrame(render);
    };

    animationId = window.requestAnimationFrame(render);
    window.addEventListener("resize", resize);

    return () => {
      window.cancelAnimationFrame(animationId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 h-full w-full"
    />
  );
}
