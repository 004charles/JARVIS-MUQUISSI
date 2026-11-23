import { useEffect, useRef } from "react";
import type { AssistantState, FaceMood, MusicState } from "../types/api";
import { HeavenClouds } from "./HeavenClouds";

/**
 * The Arcanjo exactly as in the reference video, brought to life:
 * - the giant eye follows the mouse (and looks at you while listening/speaking, up while
 *   thinking, with idle glances): the real iris of the video is displaced inside the eyeball by a
 *   WebGL shader, using a per-frame track of the eye (eye-track.json). It fades out whenever a
 *   ring passes in front of the eye, so nothing else is distorted;
 * - playback speed follows his state (slower while listening, faster while thinking);
 * - a divine glow pulses with his voice while speaking;
 * - the whole vision sways to the beat when music plays.
 * He floats in a living heaven (HeavenClouds): a painted sky behind, a sea of clouds in front.
 */

interface ArchangelVideoProps {
  state: AssistantState;
  mood?: FaceMood;
  speechEnergy?: number;
  music?: MusicState;
  onClick?: () => void;
  aside?: boolean; // step aside (left, smaller) while a vision is shown
}

const VIDEO_URL = "/assets/arcanjo/arcanjo.mp4?v=loop3"; // seamless 10 s loop cut at a natural cycle (frames 240-540 of the source)
const TRACK_URL = "/assets/arcanjo/eye-track.json?v=loop3";

interface EyeTrack {
  fps: number;
  width: number;
  height: number;
  frames: [number, number, number, number][]; // cx, cy, irisRadius (px), confidence
}

const VERT = `
attribute vec2 a_pos;
varying vec2 v_uv;
void main() {
  v_uv = vec2(a_pos.x * 0.5 + 0.5, 0.5 - a_pos.y * 0.5); // y grows downwards like pixels
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;

const FRAG = `
precision mediump float;
uniform sampler2D u_tex;
uniform vec2 u_center;   // eye centre (uv)
uniform float u_irisR;   // iris radius (width units)
uniform float u_eyeR;    // eyeball radius (width units)
uniform vec2 u_offset;   // gaze displacement (uv)
uniform float u_strength;
uniform float u_aspect;  // height / width
varying vec2 v_uv;

// How much a colour looks like the rose-gold rings (saturated, warm) rather than the
// white of the eye (low saturation) or the iris (blue).
float ringness(vec3 c) {
  float mx = max(c.r, max(c.g, c.b));
  float mn = min(c.r, min(c.g, c.b));
  float sat = mx - mn;
  float warm = smoothstep(0.02, 0.10, c.r - c.b);
  return smoothstep(0.10, 0.20, sat) * warm;
}

void main() {
  vec2 d = v_uv - u_center;
  d.y *= u_aspect;
  float dist = length(d);
  // 1 over the iris, easing to 0 at the edge of the eyeball: the iris slides over the white
  float w = (1.0 - smoothstep(u_irisR * 1.05, u_eyeR, dist)) * u_strength;
  vec4 original = texture2D(u_tex, v_uv);
  vec2 shiftedUv = v_uv - u_offset * w;
  vec4 shifted = texture2D(u_tex, shiftedUv);
  // Rings in front of the eye stay put, and ring pixels are never pulled into the eye
  float keep = max(ringness(original.rgb), ringness(shifted.rgb));
  gl_FragColor = mix(shifted, original, keep);
}`;

function setupGL(canvas: HTMLCanvasElement) {
  const gl = canvas.getContext("webgl", { premultipliedAlpha: false, alpha: true });
  if (!gl) return null;
  const compile = (type: number, src: string) => {
    const sh = gl.createShader(type)!;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh) || "shader");
    return sh;
  };
  const prog = gl.createProgram()!;
  gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
  gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
  gl.linkProgram(prog);
  gl.useProgram(prog);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "a_pos");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  const u = (n: string) => gl.getUniformLocation(prog, n);
  return {
    gl,
    uCenter: u("u_center"),
    uIrisR: u("u_irisR"),
    uEyeR: u("u_eyeR"),
    uOffset: u("u_offset"),
    uStrength: u("u_strength"),
    uAspect: u("u_aspect"),
  };
}

export function ArchangelVideo({ state, speechEnergy = 0, music, onClick, aside = false }: ArchangelVideoProps) {
  const fgRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const glowRef = useRef<HTMLDivElement | null>(null);
  const live = useRef({ state, speechEnergy, music, aside });
  live.current = { state, speechEnergy, music, aside };

  useEffect(() => {
    const fg = fgRef.current;
    const canvas = canvasRef.current;
    const stage = stageRef.current;
    const glowEl = glowRef.current;
    if (!fg || !canvas || !stage || !glowEl) return;

    let glx: ReturnType<typeof setupGL> = null;
    try {
      glx = setupGL(canvas);
    } catch {
      glx = null;
    }
    // Without WebGL show the plain video (no eye-following, everything else still works)
    if (glx) {
      // keep decoding frames (display:none can pause decoding in some browsers)
      Object.assign(fg.style, { position: "absolute", opacity: "0", pointerEvents: "none" });
      canvas.style.display = "block";
    }

    // ?gaze=x,y forces the gaze direction (-1..1) — for visual checks without a mouse
    const forced = new URLSearchParams(window.location.search).get("gaze");
    const forcedGaze = forced ? forced.split(",").map(Number) : null;
    let track: EyeTrack | null = null;
    void fetch(TRACK_URL)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: EyeTrack | null) => {
        track = data;
      })
      .catch(() => undefined);

    const tryPlay = () => {
      void fg.play().catch(() => undefined);
    };
    tryPlay();
    document.addEventListener("pointerdown", tryPlay, { once: true });

    const pointer = { x: 0, y: 0, until: 0 };
    const onMove = (e: PointerEvent) => {
      pointer.x = e.clientX;
      pointer.y = e.clientY;
      pointer.until = performance.now() + 2500;
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    let raf = 0;
    let rate = 1;
    let glow = 0;
    let bob = 0;
    let asideAmt = 0;
    const gaze = { x: 0, y: 0, tx: 0, ty: 0, nextSaccade: 0, strength: 0 };

    const tick = (now: number) => {
      const { state: st, speechEnergy: energy, music: mu } = live.current;
      const dancing = Boolean(mu?.playing && mu.bpm > 0);
      const sec = now / 1000;

      // Playback speed by state (smoothed)
      let targetRate = 1;
      if (st === "processing" || st === "executing") targetRate = 1.9;
      else if (st === "speaking") targetRate = 1.25;
      else if (st === "listening") targetRate = 0.6;
      if (dancing) targetRate = Math.min(2, Math.max(0.8, mu!.bpm / 100));
      rate += (targetRate - rate) * 0.05;
      if (Math.abs(fg.playbackRate - rate) > 0.02) {
        fg.playbackRate = rate;
      }

      // Divine glow
      const targetGlow =
        st === "speaking" ? 0.45 + energy * 0.55 : st === "listening" ? 0.3 : st === "processing" ? 0.38 : 0.08;
      glow += (targetGlow - glow) * 0.12;
      const pulse = st === "speaking" ? 0.85 + 0.15 * Math.sin(sec * 9) : 1;
      glowEl.style.opacity = String(Math.min(1, glow * pulse));

      // Breathing / dancing motion
      const targetBob = dancing ? Math.abs(Math.sin(Math.PI * sec * (mu!.bpm / 60))) * -14 : Math.sin(sec * 0.9) * 3;
      bob += (targetBob - bob) * (dancing ? 0.35 : 0.08);
      const sway = dancing ? Math.sin(Math.PI * sec * (mu!.bpm / 60)) * 1.6 : 0;
      const scale = 1 + (st === "speaking" ? energy * 0.02 : 0);
      // Step aside for a vision: glide to the left and shrink (smoothly), come back when it closes
      asideAmt += ((live.current.aside ? 1 : 0) - asideAmt) * 0.06;
      const ax = -34 * asideAmt; // vw
      const as = 1 - 0.45 * asideAmt;
      stage.style.transform = `translateX(${ax.toFixed(2)}vw) translateY(${bob.toFixed(2)}px) rotate(${sway.toFixed(2)}deg) scale(${(scale * as).toFixed(3)})`;
      const filt = `brightness(${(1 + glow * 0.12).toFixed(3)}) saturate(${(1 + glow * 0.15).toFixed(3)})`;
      fg.style.filter = filt;
      canvas.style.filter = filt;

      // ---- the eye follows you
      if (glx && fg.readyState >= 2 && fg.videoWidth > 0) {
        const { gl } = glx;
        if (canvas.width !== fg.videoWidth) {
          canvas.width = fg.videoWidth;
          canvas.height = fg.videoHeight;
          gl.viewport(0, 0, canvas.width, canvas.height);
        }
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, fg);

        const W = fg.videoWidth;
        const H = fg.videoHeight;
        let cx = W * 0.578;
        let cy = H * 0.441;
        let r = 38;
        let conf = 0;
        if (track && track.frames.length) {
          const idx = Math.floor(fg.currentTime * track.fps) % track.frames.length;
          [cx, cy, r, conf] = track.frames[idx];
        }

        // Where to look: mouse → idle glances → straight at you while listening/speaking → up when thinking
        if (now >= gaze.nextSaccade) {
          gaze.tx = (Math.random() - 0.5) * 0.8;
          gaze.ty = (Math.random() - 0.5) * 0.5;
          gaze.nextSaccade = now + (st === "processing" ? 500 : 1700) + Math.random() * 1800;
        }
        let gx = gaze.tx;
        let gy = gaze.ty;
        const rect = canvas.getBoundingClientRect();
        if (now < pointer.until && rect.width > 0) {
          const ex = rect.left + (cx / W) * rect.width;
          const ey = rect.top + (cy / H) * rect.height;
          const reach = Math.max(rect.width, rect.height) * 0.45;
          gx = Math.max(-1, Math.min(1, (pointer.x - ex) / reach));
          gy = Math.max(-1, Math.min(1, (pointer.y - ey) / reach));
        }
        if (st === "listening" || st === "speaking") {
          gx *= 0.15;
          gy *= 0.15;
        }
        if (st === "processing") {
          gx = 0.7 * Math.cos(sec * 1.6);
          gy = -0.8;
        }
        if (forcedGaze && forcedGaze.length === 2) {
          gx = forcedGaze[0];
          gy = forcedGaze[1];
        }
        gaze.x += (gx - gaze.x) * 0.12;
        gaze.y += (gy - gaze.y) * 0.12;

        // Only where the tracked iris is clearly visible (no ring in front)
        const targetStrength = conf >= 0.72 ? 1 : conf <= 0.5 ? 0 : (conf - 0.5) / 0.22;
        gaze.strength += (targetStrength - gaze.strength) * 0.15;

        const irisR = r / W;
        const eyeR = (r * 2.1) / W;
        const maxShift = (eyeR - irisR) * 0.42; // keep the iris inside the white of the eye
        gl.uniform2f(glx.uCenter, cx / W, cy / H);
        gl.uniform1f(glx.uIrisR, irisR);
        gl.uniform1f(glx.uEyeR, eyeR);
        gl.uniform2f(glx.uOffset, gaze.x * maxShift, gaze.y * maxShift * (W / H));
        gl.uniform1f(glx.uStrength, gaze.strength);
        gl.uniform1f(glx.uAspect, H / W);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      }

      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("pointerdown", tryPlay);
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  const cloudGlow = state === "speaking" ? 0.5 + speechEnergy * 0.5 : state === "listening" ? 0.3 : state === "processing" ? 0.4 : 0.1;
  const mask = "radial-gradient(ellipse 47% 49% at 50% 47%, #000 55%, transparent 100%)";
  return (
    <div className="fixed inset-0 z-0 cursor-pointer overflow-hidden bg-[#e9ebed]" onClick={onClick} title={`Arcanjo · ${state}`}>
      {/* The sky of heaven behind him */}
      <HeavenClouds layer="back" glow={cloudGlow} />
      <div ref={stageRef} className="absolute inset-0 flex items-center justify-center will-change-transform">
        {/* Source of the frames (hidden when WebGL draws the living eye) */}
        <video
          ref={fgRef}
          src={VIDEO_URL}
          muted
          loop
          playsInline
          autoPlay
          className="h-full max-w-none object-contain"
          style={{ WebkitMaskImage: mask, maskImage: mask }}
        />
        <canvas
          ref={canvasRef}
          className="h-full max-w-none"
          style={{ aspectRatio: "540 / 612", WebkitMaskImage: mask, maskImage: mask, display: "none" }}
        />
        {/* Divine light that pulses with his voice */}
        <div
          ref={glowRef}
          className="pointer-events-none absolute inset-0"
          style={{
            opacity: 0,
            background:
              "radial-gradient(circle at 50% 42%, rgba(255,247,226,0.85) 0%, rgba(255,232,200,0.35) 22%, rgba(255,232,200,0) 48%)",
            mixBlendMode: "screen",
          }}
        />
      </div>
      {/* The sea of clouds he floats above (hides the bottom of the original footage) */}
      <HeavenClouds layer="front" glow={cloudGlow} />
    </div>
  );
}
