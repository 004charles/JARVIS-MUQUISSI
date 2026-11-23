import { useEffect, useRef } from "react";
import { createHeavenSky } from "./heavenSky";

export type BackdropTheme = "clouds" | "galaxy" | "aurora";

interface BackdropCanvasProps {
  theme: BackdropTheme;
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

    // Heavenly sky for the Arcanjo (blue zenith, golden glow, light rays, lit clouds)
    const heaven = createHeavenSky();
    const renderClouds = () => heaven(ctx, width, height, performance.now() / 1000);

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

    render(); // draw the first frame immediately (no blank flash)
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
