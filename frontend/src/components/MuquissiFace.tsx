import { useEffect, useId, useRef, useState } from "react";
import type { AssistantState, FaceMood } from "../types/api";

interface MuquissiFaceProps {
  mood: FaceMood;
  state: AssistantState;
  speechEnergy?: number;
}

interface FaceRigState {
  lidTop: number;
  lidBottom: number;
  browLiftL: number;
  browLiftR: number;
  browTilt: number;
  gazeX: number;
  gazeY: number;
  pupilRadius: number;
  smileCurve: number;
  mouthOpen: number;
  mouthWidth: number;
  cheekOpacity: number;
  fatigueAlpha: number;
  tearAlpha: number;
  headTiltDeg: number;
  headY: number;
}

const INITIAL_RIG: FaceRigState = {
  lidTop: 0.1,
  lidBottom: 0.0,
  browLiftL: 0,
  browLiftR: 0,
  browTilt: 0,
  gazeX: 0,
  gazeY: 0,
  pupilRadius: 4.9,
  smileCurve: 6,
  mouthOpen: 0,
  mouthWidth: 21,
  cheekOpacity: 0.22,
  fatigueAlpha: 0,
  tearAlpha: 0,
  headTiltDeg: 0,
  headY: 0,
};

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function MuquissiFace({ mood, state, speechEnergy = 0 }: MuquissiFaceProps) {
  const uid = useId().replace(/:/g, "");
  const [rig, setRig] = useState<FaceRigState>(INITIAL_RIG);

  const moodRef = useRef<FaceMood>(mood);
  const stateRef = useRef<AssistantState>(state);
  const energyRef = useRef<number>(speechEnergy);
  moodRef.current = mood;
  stateRef.current = state;
  energyRef.current = speechEnergy;

  const pointerGazeRef = useRef<{ x: number; y: number; activeUntil: number }>({
    x: 0,
    y: 0,
    activeUntil: 0,
  });
  const blinkEndRef = useRef<number>(0);
  const nextBlinkRef = useRef<number>(performance.now() + 2600);
  const yawnEndRef = useRef<number>(0);
  const nextYawnRef = useRef<number>(performance.now() + 6500);
  const microGazeRef = useRef<{ x: number; y: number; nextAt: number }>({
    x: 0,
    y: 0,
    nextAt: 0,
  });
  const rigRef = useRef<FaceRigState>({ ...INITIAL_RIG });

  // Track subtle eye contact toward pointer movement on screen
  useEffect(() => {
    const handlePointerMove = (e: PointerEvent) => {
      const nx = (e.clientX / Math.max(1, window.innerWidth) - 0.5) * 2;
      const ny = (e.clientY / Math.max(1, window.innerHeight) - 0.5) * 2;
      pointerGazeRef.current = {
        x: Math.max(-3.6, Math.min(3.6, nx * 3.6)),
        y: Math.max(-2.6, Math.min(2.6, ny * 2.6)),
        activeUntil: performance.now() + 2800,
      };
    };
    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    return () => window.removeEventListener("pointermove", handlePointerMove);
  }, []);

  // 60fps organic facial rig interpolation
  useEffect(() => {
    let raf = 0;
    const t0 = performance.now();

    const tick = (now: number) => {
      const m = moodRef.current;
      const st = stateRef.current;
      const energy = energyRef.current;
      const sec = (now - t0) / 1000;

      // Schedule organic blinks (double-blinks occasionally, slower when tired)
      if (now >= nextBlinkRef.current) {
        const blinkDur = m === "tired" ? 260 : 140;
        blinkEndRef.current = now + blinkDur;
        const baseGap = m === "tired" ? 2100 : m === "surprised" ? 4800 : 3200;
        nextBlinkRef.current = now + baseGap + Math.random() * 2400;
      }
      const isBlinking = now < blinkEndRef.current;

      // Schedule occasional realistic yawn when tired and not speaking
      let yawning = false;
      if (m === "tired" && st !== "speaking") {
        if (now >= nextYawnRef.current) {
          yawnEndRef.current = now + 1850;
          nextYawnRef.current = now + 9500 + Math.random() * 4000;
        }
        yawning = now < yawnEndRef.current;
      }

      // Subtle random micro-saccades when idle
      if (now >= microGazeRef.current.nextAt) {
        microGazeRef.current = {
          x: (Math.random() - 0.5) * 2.4,
          y: (Math.random() - 0.5) * 1.4,
          nextAt: now + 1800 + Math.random() * 1800,
        };
      }

      // Compute target gaze
      let targetGazeX = microGazeRef.current.x;
      let targetGazeY = microGazeRef.current.y;
      if (now < pointerGazeRef.current.activeUntil && st !== "processing") {
        targetGazeX = pointerGazeRef.current.x;
        targetGazeY = pointerGazeRef.current.y;
      }
      if (st === "processing" || m === "thinking") {
        targetGazeX = 3.6 + Math.sin(sec * 1.8) * 0.6;
        targetGazeY = -3.0;
      } else if (m === "sad") {
        targetGazeX *= 0.35;
        targetGazeY = 3.1;
      } else if (m === "tired") {
        targetGazeX *= 0.25;
        targetGazeY = 2.4;
      }

      // Emotional targets
      let targetLidTop = 0.08;
      let targetLidBottom = 0.0;
      let targetBrowLiftL = 0;
      let targetBrowLiftR = 0;
      let targetBrowTilt = 0;
      let targetPupil = 4.9;
      let targetSmile = 6.5;
      let targetWidth = 21;
      let targetOpen = 0;
      let targetCheek = 0.22;
      let targetFatigue = 0;
      let targetTear = 0;
      let targetTilt = Math.sin(sec * 0.9) * 0.9;
      let targetHeadY = Math.sin(sec * 1.5) * 1.4;

      if (m === "happy") {
        targetLidTop = 0.05;
        targetLidBottom = 0.36;
        targetBrowLiftL = -4.5;
        targetBrowLiftR = -4.5;
        targetBrowTilt = 1.5;
        targetPupil = 5.4;
        targetSmile = 17.5;
        targetWidth = 25;
        targetCheek = 0.42;
        targetTilt = Math.sin(sec * 2.0) * 1.8;
      } else if (m === "sad") {
        targetLidTop = 0.28;
        targetLidBottom = 0.14;
        targetBrowLiftL = -1.5;
        targetBrowLiftR = -1.5;
        targetBrowTilt = -8.5; // Classic inner-up empathetic sad brows
        targetPupil = 5.6;
        targetSmile = -12.5;
        targetWidth = 19;
        targetCheek = 0.06;
        targetTear = 1.0;
        targetTilt = -2.2 + Math.sin(sec * 0.7) * 0.5;
        targetHeadY = 2.6 + Math.sin(sec * 1.1) * 1.2;
      } else if (m === "tired") {
        targetLidTop = yawning ? 0.82 : 0.56;
        targetLidBottom = yawning ? 0.22 : 0.12;
        targetBrowLiftL = 4.2;
        targetBrowLiftR = 4.2;
        targetBrowTilt = -2.0;
        targetPupil = 4.4;
        targetSmile = yawning ? -2 : -3.5;
        targetWidth = yawning ? 13 : 18;
        targetOpen = yawning ? 0.72 : 0.12;
        targetCheek = 0.08;
        targetFatigue = 1.0;
        targetTilt = 1.8 + Math.sin(sec * 0.6) * 1.1;
        targetHeadY = 3.2 + Math.sin(sec * 0.9) * 2.2;
      } else if (m === "curious" || st === "listening") {
        targetLidTop = 0.02;
        targetBrowLiftL = -1.5;
        targetBrowLiftR = -6.5; // Noticeable inquisitive raised brow
        targetBrowTilt = 1.0;
        targetPupil = 5.5;
        targetSmile = 4.5;
        targetWidth = 18;
        targetTilt = 2.6;
      } else if (m === "thinking" || st === "processing") {
        targetLidTop = 0.18;
        targetLidBottom = 0.14;
        targetBrowLiftL = 2.5;
        targetBrowLiftR = -2.5;
        targetBrowTilt = 3.5;
        targetPupil = 4.7;
        targetSmile = -1.5;
        targetWidth = 15;
        targetTilt = -2.0;
      } else if (m === "surprised") {
        targetLidTop = 0.0;
        targetBrowLiftL = -8.5;
        targetBrowLiftR = -8.5;
        targetBrowTilt = 0;
        targetPupil = 6.0;
        targetSmile = 0;
        targetWidth = 12;
        targetOpen = 0.68;
        targetCheek = 0.3;
      }

      // Live voice lip-sync & expressive brow cadence while speaking
      if (st === "speaking") {
        const syllable =
          Math.abs(Math.sin(sec * 12.2)) * 0.55 + Math.abs(Math.cos(sec * 7.1)) * 0.45;
        targetOpen = Math.min(1.0, 0.18 + energy * 0.62 + syllable * 0.48);
        targetBrowLiftL -= Math.sin(sec * 4.5) * 1.4;
        targetBrowLiftR -= Math.sin(sec * 4.5) * 1.4;
        targetTilt = Math.sin(sec * 2.4) * 1.9;
      }

      if (isBlinking) {
        targetLidTop = 1.0;
      }

      const c = rigRef.current;
      const lidSpeed = isBlinking ? 0.55 : 0.2;
      c.lidTop = lerp(c.lidTop, targetLidTop, lidSpeed);
      c.lidBottom = lerp(c.lidBottom, targetLidBottom, 0.14);
      c.browLiftL = lerp(c.browLiftL, targetBrowLiftL, 0.14);
      c.browLiftR = lerp(c.browLiftR, targetBrowLiftR, 0.14);
      c.browTilt = lerp(c.browTilt, targetBrowTilt, 0.14);
      c.gazeX = lerp(c.gazeX, targetGazeX, 0.14);
      c.gazeY = lerp(c.gazeY, targetGazeY, 0.14);
      c.pupilRadius = lerp(c.pupilRadius, targetPupil, 0.12);
      c.smileCurve = lerp(c.smileCurve, targetSmile, 0.15);
      c.mouthOpen = lerp(c.mouthOpen, targetOpen, st === "speaking" ? 0.42 : 0.15);
      c.mouthWidth = lerp(c.mouthWidth, targetWidth, 0.15);
      c.cheekOpacity = lerp(c.cheekOpacity, targetCheek, 0.1);
      c.fatigueAlpha = lerp(c.fatigueAlpha, targetFatigue, 0.1);
      c.tearAlpha = lerp(c.tearAlpha, targetTear, 0.1);
      c.headTiltDeg = lerp(c.headTiltDeg, targetTilt, 0.08);
      c.headY = lerp(c.headY, targetHeadY, 0.08);

      setRig({ ...c });
      raf = window.requestAnimationFrame(tick);
    };

    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, []);

  // Anatomical geometry calculation
  const eyeRy = mood === "surprised" ? 16.5 : 14.5;
  const irisOuter =
    mood === "sad"
      ? "#0369a1"
      : mood === "tired"
        ? "#475569"
        : mood === "happy"
          ? "#0284c7"
          : "#0ea5e9";
  const irisInner = mood === "tired" ? "#94a3b8" : "#38bdf8";

  // Curved upper eyelid edge (smooth Bezier draped over eyeball)
  const renderEye = (cx: number, side: "left" | "right", clipId: string) => {
    const cy = 86;
    const rx = 17.5;
    const topEdgeY = cy - eyeRy + rig.lidTop * (eyeRy * 2.05);
    const outerDrop = mood === "sad" ? (side === "left" ? 3.5 : 3.5) : 0;
    const innerLift = mood === "sad" ? -2.2 : 0;
    const leftEdgeY = topEdgeY + (side === "left" ? outerDrop : innerLift);
    const rightEdgeY = topEdgeY + (side === "right" ? outerDrop : innerLift);
    const ctrlY = topEdgeY - (1 - rig.lidTop) * 8;

    const botEdgeY = cy + eyeRy - rig.lidBottom * 12;
    const botCtrlY = botEdgeY - rig.lidBottom * 5;

    return (
      <g>
        {/* Subtle orbital socket shading */}
        <ellipse
          cx={cx}
          cy={cy + 1}
          rx={rx + 4}
          ry={eyeRy + 4}
          fill="#bae6fd"
          opacity="0.28"
        />

        {/* Sclera */}
        <ellipse
          cx={cx}
          cy={cy}
          rx={rx}
          ry={eyeRy}
          fill={`url(#${uid}-sclera)`}
          stroke="#7dd3fc"
          strokeOpacity="0.55"
          strokeWidth="1"
        />

        <g clipPath={`url(#${clipId})`}>
          {/* Iris + Pupil + Radial Fibers + Catchlights */}
          <g transform={`translate(${rig.gazeX.toFixed(2)}, ${rig.gazeY.toFixed(2)})`}>
            <circle cx={cx} cy={cy} r="10.4" fill={`url(#${uid}-iris)`} />
            {/* Subtle iris texture ring */}
            <circle
              cx={cx}
              cy={cy}
              r="7.6"
              fill="none"
              stroke="#ffffff"
              strokeOpacity="0.22"
              strokeWidth="1.2"
              strokeDasharray="1.5 2.5"
            />
            <circle cx={cx} cy={cy} r={rig.pupilRadius} fill="#061224" />
            <circle cx={cx - 3.6} cy={cy - 3.5} r="2.9" fill="#ffffff" opacity="0.96" />
            <circle cx={cx + 3.2} cy={cy + 3.6} r="1.3" fill="#ffffff" opacity="0.72" />
          </g>

          {/* Soft shadow cast by upper eyelid onto sclera/iris */}
          <path
            d={`M ${cx - rx - 3} ${cy - eyeRy - 8} L ${cx + rx + 3} ${cy - eyeRy - 8} L ${cx + rx + 3} ${rightEdgeY + 3.5} Q ${cx} ${ctrlY + 4} ${cx - rx - 3} ${leftEdgeY + 3.5} Z`}
            fill="#0c4a6e"
            opacity="0.14"
          />

          {/* Curved Anatomical Upper Eyelid */}
          <path
            d={`M ${cx - rx - 3} ${cy - eyeRy - 10} L ${cx + rx + 3} ${cy - eyeRy - 10} L ${cx + rx + 3} ${rightEdgeY} Q ${cx} ${ctrlY} ${cx - rx - 3} ${leftEdgeY} Z`}
            fill={`url(#${uid}-lidFill)`}
          />
          {/* Upper Lash Rim */}
          <path
            d={`M ${cx - rx - 1} ${leftEdgeY} Q ${cx} ${ctrlY} ${cx + rx + 1} ${rightEdgeY}`}
            fill="none"
            stroke="#0f2942"
            strokeWidth={rig.lidTop > 0.85 ? "2.4" : "2.1"}
            strokeLinecap="round"
          />

          {/* Curved Lower Eyelid Lift (Duchenne smile / squint) */}
          {rig.lidBottom > 0.02 && (
            <path
              d={`M ${cx - rx - 3} ${cy + eyeRy + 8} L ${cx + rx + 3} ${cy + eyeRy + 8} L ${cx + rx + 3} ${botEdgeY} Q ${cx} ${botCtrlY} ${cx - rx - 3} ${botEdgeY} Z`}
              fill="#eef8ff"
            />
          )}

          {/* Shimmering Moisture / Tear Glisten when Sad */}
          {rig.tearAlpha > 0.05 && rig.lidTop < 0.7 && (
            <ellipse
              cx={side === "left" ? cx + 5.5 : cx - 5.5}
              cy={cy + eyeRy - 3.6}
              rx="5.2"
              ry="2.0"
              fill="#ffffff"
              opacity={0.92 * rig.tearAlpha}
            />
          )}
        </g>

        {/* Outer eye contour */}
        <ellipse
          cx={cx}
          cy={cy}
          rx={rx}
          ry={eyeRy}
          fill="none"
          stroke="#0f2942"
          strokeOpacity="0.62"
          strokeWidth="1.25"
        />

        {/* Delicate Upper Eyelid Crease */}
        {rig.lidTop < 0.72 && (
          <path
            d={`M ${cx - rx + 3} ${leftEdgeY - 4.5} Q ${cx} ${ctrlY - 5.5} ${cx + rx - 3} ${rightEdgeY - 4.5}`}
            fill="none"
            stroke="#7dd3fc"
            strokeOpacity="0.65"
            strokeWidth="1.1"
            strokeLinecap="round"
          />
        )}

        {/* Tiredness Under-Eye Shadows (olheiras) */}
        {rig.fatigueAlpha > 0.05 && (
          <path
            d={`M ${cx - 14} ${cy + eyeRy + 3.5} Q ${cx} ${cy + eyeRy + 9.5} ${cx + 14} ${cy + eyeRy + 3.5}`}
            fill="none"
            stroke="#64748b"
            strokeOpacity={0.62 * rig.fatigueAlpha}
            strokeWidth="2.0"
            strokeLinecap="round"
          />
        )}
      </g>
    );
  };

  // Smooth Eyebrow Geometry
  const lInnerY = 64 + rig.browLiftL + rig.browTilt;
  const lOuterY = 67 + rig.browLiftL - rig.browTilt * 0.7;
  const lCtrlY = (lInnerY + lOuterY) / 2 - 5.5;
  const rInnerY = 64 + rig.browLiftR + rig.browTilt;
  const rOuterY = 67 + rig.browLiftR - rig.browTilt * 0.7;
  const rCtrlY = (rInnerY + rOuterY) / 2 - 5.5;

  // Dynamic Mouth + Lips Geometry
  const mY = 136;
  const mw = rig.mouthWidth;
  const openPx = rig.mouthOpen * 18;
  const cornerY = mY - rig.smileCurve * 0.25;
  const upperLipCtrlY = mY - Math.max(0, rig.mouthOpen * 4.5) - rig.smileCurve * 0.08;
  const lowerLipCtrlY = mY + rig.smileCurve * 0.88 + openPx * 1.15;

  return (
    <svg
      viewBox="0 0 200 200"
      className="h-full w-full select-none"
      aria-label={`Rosto do Muquissi (${mood})`}
    >
      <defs>
        <radialGradient id={`${uid}-cloudBg`} cx="38%" cy="28%" r="74%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="58%" stopColor="#f8fcff" />
          <stop offset="86%" stopColor="#e0f2fe" />
          <stop offset="100%" stopColor="#bae6fd" />
        </radialGradient>

        <radialGradient id={`${uid}-lidFill`} cx="50%" cy="25%" r="80%">
          <stop offset="0%" stopColor="#f8fcff" />
          <stop offset="100%" stopColor="#d8eefc" />
        </radialGradient>

        <radialGradient id={`${uid}-sclera`} cx="50%" cy="42%" r="60%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="82%" stopColor="#f8fafc" />
          <stop offset="100%" stopColor="#e2e8f0" />
        </radialGradient>

        <radialGradient id={`${uid}-iris`} cx="44%" cy="38%" r="62%">
          <stop offset="0%" stopColor={irisInner} />
          <stop offset="68%" stopColor={irisOuter} />
          <stop offset="100%" stopColor="#082f49" />
        </radialGradient>

        <clipPath id={`${uid}-leftEyeClip`}>
          <ellipse cx="65" cy="86" rx="17.5" ry={eyeRy} />
        </clipPath>
        <clipPath id={`${uid}-rightEyeClip`}>
          <ellipse cx="135" cy="86" rx="17.5" ry={eyeRy} />
        </clipPath>
      </defs>

      {/* Luminous White Cloud Face Sphere */}
      <circle cx="100" cy="100" r="99" fill={`url(#${uid}-cloudBg)`} />
      <circle cx="52" cy="46" r="34" fill="#ffffff" opacity="0.58" />
      <circle cx="144" cy="52" r="28" fill="#ffffff" opacity="0.45" />
      <ellipse cx="100" cy="177" rx="68" ry="18" fill="#bae6fd" opacity="0.34" />

      {/* Organic Head Orientation & Breathing */}
      <g transform={`translate(0, ${rig.headY.toFixed(2)}) rotate(${rig.headTiltDeg.toFixed(2)}, 100, 102)`}>
        {/* Soft Cheeks */}
        <ellipse
          cx="46"
          cy="115"
          rx="15"
          ry="8.5"
          fill={mood === "sad" || mood === "tired" ? "#94a3b8" : "#fda4af"}
          opacity={rig.cheekOpacity}
        />
        <ellipse
          cx="154"
          cy="115"
          rx="15"
          ry="8.5"
          fill={mood === "sad" || mood === "tired" ? "#94a3b8" : "#fda4af"}
          opacity={rig.cheekOpacity}
        />

        {/* Expressive Eyebrows */}
        <path
          d={`M 45 ${lOuterY.toFixed(1)} Q 64 ${lCtrlY.toFixed(1)} 82 ${lInnerY.toFixed(1)}`}
          fill="none"
          stroke="#0f2942"
          strokeWidth="4.3"
          strokeLinecap="round"
        />
        <path
          d={`M 118 ${rInnerY.toFixed(1)} Q 136 ${rCtrlY.toFixed(1)} 155 ${rOuterY.toFixed(1)}`}
          fill="none"
          stroke="#0f2942"
          strokeWidth="4.3"
          strokeLinecap="round"
        />

        {/* Anatomical Eyes */}
        {renderEye(65, "left", `${uid}-leftEyeClip`)}
        {renderEye(135, "right", `${uid}-rightEyeClip`)}

        {/* Sculpted Nose */}
        <g>
          <path
            d="M 98.5 84 Q 95.5 103 92.5 111"
            fill="none"
            stroke="#7dd3fc"
            strokeOpacity="0.58"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
          <line
            x1="101"
            y1="86"
            x2="101"
            y2="108"
            stroke="#ffffff"
            strokeOpacity="0.92"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <ellipse cx="100" cy="113" rx="8.5" ry="4.6" fill="#bae6fd" opacity="0.45" />
          <path
            d="M 91.5 112.5 Q 100 118.5 108.5 112.5"
            fill="none"
            stroke="#0f2942"
            strokeOpacity="0.65"
            strokeWidth="2.1"
            strokeLinecap="round"
          />
          <circle cx="94.5" cy="113.5" r="1.4" fill="#0f2942" opacity="0.45" />
          <circle cx="105.5" cy="113.5" r="1.4" fill="#0f2942" opacity="0.45" />
        </g>

        {/* Expressive Mouth & Lips */}
        <g>
          {rig.mouthOpen > 0.04 ? (
            <g>
              {/* Inner Mouth Cavity */}
              <path
                d={`M ${(100 - mw).toFixed(1)} ${cornerY.toFixed(1)} Q 100 ${upperLipCtrlY.toFixed(1)} ${(100 + mw).toFixed(1)} ${cornerY.toFixed(1)} Q 100 ${lowerLipCtrlY.toFixed(1)} ${(100 - mw).toFixed(1)} ${cornerY.toFixed(1)} Z`}
                fill="#0f2942"
                stroke="#0f2942"
                strokeWidth="2.3"
                strokeLinejoin="round"
              />
              {/* Warm Tongue */}
              <ellipse
                cx="100"
                cy={(mY + openPx * 0.52 + Math.max(0, rig.smileCurve) * 0.25).toFixed(1)}
                rx={Math.max(4.5, mw * 0.46)}
                ry={Math.max(1.8, openPx * 0.3)}
                fill="#fb7185"
                opacity="0.78"
              />
              {/* Upper Teeth Hint */}
              {openPx >= 5 && mood !== "sad" && (
                <path
                  d={`M ${(100 - mw * 0.56).toFixed(1)} ${(cornerY + 1).toFixed(1)} Q 100 ${(upperLipCtrlY + 2.5).toFixed(1)} ${(100 + mw * 0.56).toFixed(1)} ${(cornerY + 1).toFixed(1)}`}
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  opacity="0.9"
                />
              )}
            </g>
          ) : (
            <path
              d={`M ${(100 - mw).toFixed(1)} ${cornerY.toFixed(1)} Q 100 ${(mY + rig.smileCurve).toFixed(1)} ${(100 + mw).toFixed(1)} ${cornerY.toFixed(1)}`}
              fill="none"
              stroke="#0f2942"
              strokeWidth="3.2"
              strokeLinecap="round"
            />
          )}

          {/* Soft Lower-Lip Shadow Contour */}
          <path
            d={`M ${(100 - mw * 0.42).toFixed(1)} ${(mY + 11 + openPx * 0.68 + Math.max(0, rig.smileCurve) * 0.35).toFixed(1)} Q 100 ${(mY + 14.5 + openPx * 0.72 + Math.max(0, rig.smileCurve) * 0.42).toFixed(1)} ${(100 + mw * 0.42).toFixed(1)} ${(mY + 11 + openPx * 0.68 + Math.max(0, rig.smileCurve) * 0.35).toFixed(1)}`}
            fill="none"
            stroke="#7dd3fc"
            strokeOpacity="0.65"
            strokeWidth="2.1"
            strokeLinecap="round"
          />
        </g>
      </g>
    </svg>
  );
}
