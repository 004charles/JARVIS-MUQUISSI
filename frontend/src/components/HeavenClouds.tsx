import { useEffect, useRef } from "react";

/**
 * A living heaven painted in real time (WebGL, no images): domain-warped fbm clouds lit by the
 * divine light that shines from behind the Arcanjo.
 * - layer "back": the sky — golden glow, soft god rays and distant cloud banks drifting slowly;
 * - layer "front": a sea of clouds below him, lit from above with shaded undersides, plus thin
 *   wisps at the edges (transparent elsewhere, so the Arcanjo stays clear).
 * Rendered at reduced resolution (clouds are soft) so it runs smoothly on integrated graphics.
 * The light brightens with `glow` (his voice) and the clouds shift slightly with the mouse.
 */

interface HeavenCloudsProps {
  layer: "back" | "front";
  glow?: number; // 0..1
  className?: string;
}

const VERT = `
attribute vec2 a_pos;
varying vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;

const COMMON = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 u_res;
uniform float u_time;
uniform vec2 u_par;
uniform float u_glow;
varying vec2 v_uv;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
const mat2 ROT = mat2(1.6, 1.2, -1.2, 1.6);
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 5; i++) { v += a * noise(p); p = ROT * p; a *= 0.5; }
  return v;
}
// billowing, slowly churning clouds
float clouds(vec2 p, float t) {
  vec2 q = vec2(fbm(p + vec2(0.0, t * 0.03)), fbm(p + vec2(5.2, 1.3) - t * 0.02));
  return fbm(p + 1.7 * q + vec2(t * 0.012, 0.0));
}
const vec2 LIGHT = vec2(0.0, 0.10); // the divine light, behind the Arcanjo
`;

const BACK = `${COMMON}
void main() {
  float aspect = u_res.x / u_res.y;
  vec2 p = (v_uv - 0.5) * vec2(aspect, 1.0);
  float t = u_time;

  // sky: lilac-blue heights, warm cream near the light, pearl below
  vec3 zenith = vec3(0.74, 0.79, 0.92);
  vec3 horizon = vec3(1.0, 0.95, 0.89);
  vec3 sky = mix(horizon, zenith, smoothstep(-0.1, 0.62, p.y));
  vec2 dl = p - LIGHT;
  float r = length(dl);
  float glow = exp(-r * 2.6) * (0.85 + 0.35 * u_glow);
  sky += vec3(1.0, 0.86, 0.62) * glow * 0.55;

  // gentle god rays turning around the light
  float ang = atan(dl.y, dl.x);
  float rays = noise(vec2(ang * 7.0, t * 0.05)) * noise(vec2(ang * 13.0 - t * 0.03, 1.7));
  sky += vec3(1.0, 0.93, 0.78) * rays * smoothstep(1.3, 0.15, r) * (0.22 + 0.15 * u_glow);

  // distant cloud banks: thicker low and to the sides, thin near the light
  vec2 cp = p * 1.9 + u_par * 0.04;
  float d = clouds(cp, t);
  float shape = smoothstep(0.45, -0.45, p.y) * 0.55 + smoothstep(0.3, 1.0, abs(p.x)) * 0.35 + 0.18;
  shape *= smoothstep(0.08, 0.55, r);
  float cover = smoothstep(0.56, 0.70, d + shape * 0.40);
  // light comes from the divine glow: compare density one step towards it
  vec2 toL = normalize(LIGHT - p) * 0.045;
  float lit = clamp((d - clouds(cp + toL * 1.9, t)) * 7.0 + 0.5, 0.0, 1.0);
  float depth = smoothstep(0.56, 0.95, d + shape * 0.40); // thicker = darker core
  vec3 shadow = mix(vec3(0.82, 0.80, 0.89), vec3(0.66, 0.65, 0.80), depth);
  vec3 bright = mix(vec3(1.0, 0.985, 0.96), vec3(1.0, 0.90, 0.72), exp(-r * 2.0) * 0.6);
  vec3 cloudCol = mix(shadow, bright, lit);
  cloudCol += vec3(1.0, 0.85, 0.6) * pow(lit, 6.0) * exp(-r * 1.6) * 0.35; // silver-gold lining
  vec3 col = mix(sky, cloudCol, cover * 0.95);

  col *= 1.0 - 0.10 * smoothstep(0.7, 1.6, length(p * vec2(0.8, 1.0))); // soft vignette
  gl_FragColor = vec4(col, 1.0);
}`;

const FRONT = `${COMMON}
float seaDensity(vec2 p, float t) {
  vec2 sp = vec2(p.x * 1.15 + t * 0.018, p.y * 2.1) + u_par * 0.10;
  float d = clouds(sp, t * 0.8);
  // the sea rises towards the bottom, its surface billowing
  float base = smoothstep(-0.12, -0.50, p.y + 0.05 * sin(p.x * 2.3 + t * 0.07));
  return d * 1.1 + base * 0.8 - 0.70;
}
void main() {
  float aspect = u_res.x / u_res.y;
  vec2 p = (v_uv - 0.5) * vec2(aspect, 1.0);
  float t = u_time;

  float dens = seaDensity(p, t);
  float alpha = smoothstep(0.0, 0.07, dens);
  // lit from above: tops bright and warm, undersides lilac shadow
  float above = seaDensity(p + vec2(0.0, 0.03), t);
  float lit = clamp((dens - above) * 6.0 + 0.45, 0.0, 1.0);
  float r = length(p - LIGHT);
  float depth = smoothstep(0.05, 0.45, dens);
  vec3 shadow = mix(vec3(0.80, 0.78, 0.88), vec3(0.62, 0.61, 0.77), depth);
  vec3 bright = mix(vec3(1.0, 0.99, 0.97), vec3(1.0, 0.92, 0.78), exp(-r * 1.5) * 0.5);
  vec3 col = mix(shadow, bright, lit);
  col += vec3(1.0, 0.88, 0.65) * pow(lit, 5.0) * 0.12; // sunlit crests
  col += vec3(1.0, 0.9, 0.7) * u_glow * 0.06;

  // thin wisps drifting at the far edges, for depth
  float side = smoothstep(0.55, 1.05, abs(p.x) / max(aspect * 0.5, 0.5));
  float wisp = smoothstep(0.55, 0.85, clouds(p * vec2(1.2, 2.4) + vec2(t * 0.02, 3.0) + u_par * 0.12, t)) * side;
  float a = max(alpha, wisp * 0.55);
  vec3 c = mix(mix(shadow, bright, 0.8), col, alpha / max(a, 0.001));
  gl_FragColor = vec4(c * a, a); // premultiplied
}`;

function makeProgram(gl: WebGLRenderingContext, frag: string) {
  const compile = (type: number, src: string) => {
    const sh = gl.createShader(type)!;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh) || "shader");
    return sh;
  };
  const prog = gl.createProgram()!;
  gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
  gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, frag));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) || "link");
  gl.useProgram(prog);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "a_pos");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  return prog;
}

const RENDER_SCALE = 0.5; // soft clouds don't need full resolution

export function HeavenClouds({ layer, glow = 0, className = "" }: HeavenCloudsProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const glowRef = useRef(glow);
  glowRef.current = glow;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { premultipliedAlpha: true, alpha: layer === "front", antialias: false });
    if (!gl) return;
    let prog: WebGLProgram;
    try {
      prog = makeProgram(gl, layer === "back" ? BACK : FRONT);
    } catch (err) {
      console.warn("HeavenClouds: shader failed", err);
      return;
    }
    const uRes = gl.getUniformLocation(prog, "u_res");
    const uTime = gl.getUniformLocation(prog, "u_time");
    const uPar = gl.getUniformLocation(prog, "u_par");
    const uGlow = gl.getUniformLocation(prog, "u_glow");

    const mouse = { x: 0, y: 0 };
    const par = { x: 0, y: 0 };
    const onMove = (e: PointerEvent) => {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener("pointermove", onMove);

    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const start = performance.now() - 40_000; // start mid-drift so clouds are already formed
    let smoothGlow = 0;
    let raf = 0;
    let last = 0;
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      if (now - last < 33) return; // ~30 fps is plenty for drifting clouds
      last = now;
      const w = Math.max(1, Math.round(canvas.clientWidth * RENDER_SCALE));
      const h = Math.max(1, Math.round(canvas.clientHeight * RENDER_SCALE));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
        gl.viewport(0, 0, w, h);
      }
      par.x += (mouse.x - par.x) * 0.03;
      par.y += (mouse.y - par.y) * 0.03;
      smoothGlow += (glowRef.current - smoothGlow) * 0.1;
      const t = reduced ? 40 : (now - start) / 1000;
      gl.uniform2f(uRes, w, h);
      gl.uniform1f(uTime, t);
      gl.uniform2f(uPar, par.x, -par.y);
      gl.uniform1f(uGlow, Math.min(1, smoothGlow));
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    };
  }, [layer]);

  return <canvas ref={canvasRef} aria-hidden="true" className={`pointer-events-none absolute inset-0 h-full w-full ${className}`} />;
}
