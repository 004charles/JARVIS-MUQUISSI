import { motion } from "framer-motion";
import { useEffect, useRef } from "react";
import type { AssistantState, FaceMood, MusicState } from "../types/api";
import type { BackdropTheme } from "./BackdropCanvas";
import { MuquissiFace } from "./MuquissiFace";

interface JarvisCoreWheelProps {
  state: AssistantState;
  mood?: FaceMood;
  speechEnergy?: number;
  music?: MusicState;
  theme?: BackdropTheme;
  onCoreClick?: () => void;
}

const DARK_STATE_META: Record<
  AssistantState,
  { label: string; ringColor: string; glowColor: string; coreRgb: string }
> = {
  idle: {
    label: "DISPONÍVEL",
    ringColor: "#22d3ee",
    glowColor: "rgba(34, 211, 238, 0.35)",
    coreRgb: "34, 211, 238",
  },
  listening: {
    label: "A OUVIR",
    ringColor: "#38bdf8",
    glowColor: "rgba(56, 189, 248, 0.55)",
    coreRgb: "56, 189, 248",
  },
  processing: {
    label: "A PROCESSAR",
    ringColor: "#60a5fa",
    glowColor: "rgba(96, 165, 250, 0.55)",
    coreRgb: "96, 165, 250",
  },
  speaking: {
    label: "A FALAR",
    ringColor: "#67e8f9",
    glowColor: "rgba(103, 232, 249, 0.72)",
    coreRgb: "103, 232, 249",
  },
  executing: {
    label: "A EXECUTAR",
    ringColor: "#34d399",
    glowColor: "rgba(52, 211, 153, 0.55)",
    coreRgb: "52, 211, 153",
  },
  error: {
    label: "ERRO",
    ringColor: "#fb7185",
    glowColor: "rgba(251, 113, 133, 0.55)",
    coreRgb: "251, 113, 133",
  },
};

const LIGHT_STATE_META: Record<
  AssistantState,
  { label: string; ringColor: string; glowColor: string; coreRgb: string }
> = {
  idle: {
    label: "DISPONÍVEL",
    ringColor: "#0284c7",
    glowColor: "rgba(14, 165, 233, 0.35)",
    coreRgb: "14, 165, 233",
  },
  listening: {
    label: "A OUVIR",
    ringColor: "#0369a1",
    glowColor: "rgba(2, 132, 199, 0.45)",
    coreRgb: "2, 132, 199",
  },
  processing: {
    label: "A PROCESSAR",
    ringColor: "#2563eb",
    glowColor: "rgba(37, 99, 235, 0.45)",
    coreRgb: "37, 99, 235",
  },
  speaking: {
    label: "A FALAR",
    ringColor: "#0284c7",
    glowColor: "rgba(14, 165, 233, 0.62)",
    coreRgb: "14, 165, 233",
  },
  executing: {
    label: "A EXECUTAR",
    ringColor: "#059669",
    glowColor: "rgba(5, 150, 105, 0.45)",
    coreRgb: "5, 150, 105",
  },
  error: {
    label: "ERRO",
    ringColor: "#e11d48",
    glowColor: "rgba(225, 29, 72, 0.45)",
    coreRgb: "225, 29, 72",
  },
};

export function JarvisCoreWheel({
  state,
  mood = "neutral",
  speechEnergy = 0,
  music,
  theme = "clouds",
  onCoreClick,
}: JarvisCoreWheelProps) {
  const waveCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef(state);
  const energyRef = useRef(speechEnergy);
  const themeRef = useRef(theme);

  stateRef.current = state;
  energyRef.current = speechEnergy;
  themeRef.current = theme;

  useEffect(() => {
    const canvas = waveCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const size = 400;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const bars = 72;
    const amplitudes = new Float32Array(bars);
    let phase = 0;
    let frameId = 0;

    const draw = () => {
      const currentState = stateRef.current;
      const palette =
        themeRef.current === "clouds" ? LIGHT_STATE_META : DARK_STATE_META;
      const meta = palette[currentState];
      const boost = energyRef.current;
      phase += currentState === "speaking" ? 0.14 : currentState === "processing" ? 0.11 : 0.035;

      ctx.clearRect(0, 0, size, size);
      const cx = size / 2;
      const cy = size / 2;
      const baseRadius = 116;

      if (currentState === "speaking" || currentState === "listening") {
        const rippleR =
          baseRadius + 40 + Math.sin(phase * 1.3) * (currentState === "speaking" ? 15 : 7);
        ctx.beginPath();
        ctx.arc(cx, cy, rippleR, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${meta.coreRgb}, ${currentState === "speaking" ? 0.42 : 0.25})`;
        ctx.lineWidth = 1.6;
        ctx.stroke();
      }

      for (let i = 0; i < bars; i++) {
        const angle = (i / bars) * Math.PI * 2 + phase * 0.22;
        let targetAmp = 4;

        if (currentState === "speaking") {
          const wave1 = Math.sin(phase * 2.1 + i * 0.45);
          const wave2 = Math.cos(phase * 3.3 - i * 0.8);
          const syllable = Math.abs(Math.sin(phase * 1.4 + (i % 6) * 0.6));
          targetAmp =
            11 +
            (Math.abs(wave1 * 0.6 + wave2 * 0.4) * 30 + syllable * 12) *
              (0.85 + boost * 0.65);
        } else if (currentState === "listening") {
          targetAmp = 7 + Math.abs(Math.sin(phase * 1.8 + i * 0.35)) * 16;
        } else if (currentState === "processing") {
          const sweep = Math.max(0, Math.sin(angle - phase * 2.2));
          targetAmp = 5 + sweep * 22;
        } else if (currentState === "executing") {
          targetAmp = i % 3 === 0 ? 15 + Math.sin(phase * 2) * 5 : 6;
        } else if (currentState === "error") {
          targetAmp = 8 + Math.abs(Math.sin(phase * 3)) * 14;
        } else {
          targetAmp = 4 + Math.sin(phase + i * 0.25) * 2.5;
        }

        amplitudes[i] += (targetAmp - amplitudes[i]) * 0.24;
        const innerR = baseRadius;
        const outerR = baseRadius + amplitudes[i];

        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(angle) * innerR, cy + Math.sin(angle) * innerR);
        ctx.lineTo(cx + Math.cos(angle) * outerR, cy + Math.sin(angle) * outerR);
        ctx.strokeStyle = `rgba(${meta.coreRgb}, ${currentState === "speaking" ? 0.94 : 0.68})`;
        ctx.lineWidth = currentState === "speaking" ? 2.8 : 2;
        ctx.lineCap = "round";
        ctx.stroke();
      }

      frameId = window.requestAnimationFrame(draw);
    };

    frameId = window.requestAnimationFrame(draw);
    return () => window.cancelAnimationFrame(frameId);
  }, []);

  const isLight = theme === "clouds";
  const palette = isLight ? LIGHT_STATE_META : DARK_STATE_META;
  const meta = palette[state];
  const isSpeaking = state === "speaking";
  const isActive = state !== "idle";

  return (
    <div className="relative z-20 flex flex-col items-center justify-center select-none">
      <div className="relative flex h-[360px] w-[360px] sm:h-[400px] sm:w-[400px] items-center justify-center">
        <canvas
          ref={waveCanvasRef}
          className="pointer-events-none absolute inset-0 h-full w-full"
        />

        {/* Outer rotating HUD wheel */}
        <motion.svg
          viewBox="0 0 360 360"
          className="pointer-events-none absolute inset-0 h-full w-full"
          animate={{ rotate: 360 }}
          transition={{
            duration: isSpeaking ? 9 : state === "processing" ? 6 : 28,
            repeat: Infinity,
            ease: "linear",
          }}
        >
          <circle
            cx="180"
            cy="180"
            r="168"
            fill="none"
            stroke={meta.ringColor}
            strokeOpacity={isLight ? "0.28" : "0.22"}
            strokeWidth="1"
            strokeDasharray="6 10"
          />
          <circle
            cx="180"
            cy="180"
            r="156"
            fill="none"
            stroke={meta.ringColor}
            strokeOpacity={isLight ? "0.65" : "0.55"}
            strokeWidth="2.5"
            strokeDasharray="54 22 18 22 72 28"
          />
          {Array.from({ length: 24 }).map((_, idx) => {
            const angle = (idx * 15 * Math.PI) / 180;
            const r1 = idx % 2 === 0 ? 161 : 164;
            const r2 = 171;
            return (
              <line
                key={idx}
                x1={180 + Math.cos(angle) * r1}
                y1={180 + Math.sin(angle) * r1}
                x2={180 + Math.cos(angle) * r2}
                y2={180 + Math.sin(angle) * r2}
                stroke={meta.ringColor}
                strokeOpacity={idx % 2 === 0 ? 0.65 : 0.3}
                strokeWidth={idx % 2 === 0 ? 1.8 : 1}
              />
            );
          })}
        </motion.svg>

        {/* Counter-rotating inner wheel */}
        <motion.svg
          viewBox="0 0 360 360"
          className="pointer-events-none absolute inset-0 h-full w-full"
          animate={{ rotate: -360 }}
          transition={{
            duration: isSpeaking ? 5.5 : state === "processing" ? 4 : 18,
            repeat: Infinity,
            ease: "linear",
          }}
        >
          <circle
            cx="180"
            cy="180"
            r="102"
            fill="none"
            stroke={meta.ringColor}
            strokeOpacity="0.6"
            strokeWidth="2"
            strokeDasharray="36 14 10 14"
          />
          <circle
            cx="180"
            cy="180"
            r="88"
            fill="none"
            stroke={meta.ringColor}
            strokeOpacity="0.35"
            strokeWidth="1.2"
            strokeDasharray="4 6"
          />
        </motion.svg>

        {/* Foreground Luminous White Cloud Sphere = Arcanjo Dynamic Face */}
        <motion.button
          type="button"
          onClick={onCoreClick}
          title={`Arcanjo · ${meta.label}`}
          animate={{
            scale: isSpeaking
              ? [1, 1.07, 0.98, 1.06, 1]
              : isActive
                ? [1, 1.03, 1]
                : [1, 1.015, 1],
          }}
          transition={{
            duration: isSpeaking ? 0.55 : isActive ? 1.4 : 3.4,
            repeat: Infinity,
            ease: "easeInOut",
          }}
          style={{
            boxShadow: `0 0 ${isSpeaking ? "75px" : "44px"} ${meta.glowColor}, 0 12px 35px rgba(14, 165, 233, 0.22)`,
          }}
          className={`relative z-30 flex h-48 w-48 cursor-pointer items-center justify-center overflow-hidden rounded-full border-2 bg-white transition-colors focus:outline-none ${
            isLight ? "border-sky-400/60" : "border-cyan-300/65"
          }`}
        >
          <MuquissiFace mood={mood} state={state} speechEnergy={speechEnergy} music={music} />
        </motion.button>
      </div>
    </div>
  );
}
