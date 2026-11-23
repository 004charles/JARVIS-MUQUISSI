import { useEffect, useRef } from "react";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { RGBELoader } from "three/examples/jsm/loaders/RGBELoader.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import type { AssistantState, FaceMood, MusicState } from "../types/api";

/**
 * Photoreal Arcanjo (WebGL / three.js).
 *
 * - Wide, smooth rose-gold bands (lathe profile with rounded edges + engraved bump pattern),
 *   PBR metal reflecting an HDRI heavenly sky.
 * - Real eyes embedded in the bands (no visible lids, as in the reference); they follow the gaze
 *   and blink with a quick vertical squash. The giant eye sits in a fleshy rose rim.
 * - Giant central eye with detailed iris, wet cornea and veined sclera.
 * Behaviour mirrors the 2D version (gaze, blinks, pupil, speed per state, dancing).
 */

interface ArchangelSceneProps {
  state: AssistantState;
  mood?: FaceMood;
  speechEnergy?: number;
  music?: MusicState;
  onClick?: () => void;
  onFail?: () => void;
}

const SKY_URL = "/assets/arcanjo/sky.hdr";
const SPIN = 4.2;
const BLINK_MS = 180;

interface RingSpec {
  radius: number;
  width: number; // along the ring axis
  thickness: number; // radial
  tilt: THREE.Euler;
  spin: number;
  wobble: number;
  eyes: number;
}

const RINGS: RingSpec[] = [
  { radius: 1.8, width: 0.34, thickness: 0.08, tilt: new THREE.Euler(1.32, 0.0, 0.2), spin: 0.16, wobble: 0.05, eyes: 24 },
  { radius: 1.52, width: 0.3, thickness: 0.075, tilt: new THREE.Euler(0.12, 1.2, 0.6), spin: -0.13, wobble: 0.07, eyes: 20 },
  { radius: 1.26, width: 0.27, thickness: 0.07, tilt: new THREE.Euler(0.28, -0.6, 2.4), spin: 0.11, wobble: 0.09, eyes: 17 },
];

function mulberry(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ------------------------------------------------------------------ textures
/** Iris for a sphere cap (polar layout): canvas top = centre/pupil, bottom = limbus. */
function drawIris(canvas: HTMLCanvasElement, pupil: number, glow: number) {
  const c = canvas.getContext("2d");
  if (!c) return;
  const w = canvas.width;
  const h = canvas.height;
  const py = h * pupil;
  const g = c.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, "#000");
  g.addColorStop(Math.max(0.01, pupil - 0.005), "#000");
  g.addColorStop(Math.min(0.99, pupil + 0.015), "#3a2a1c"); // warm ring around the pupil
  g.addColorStop(Math.min(0.99, pupil + 0.08), `rgb(${Math.round(150 + glow * 60)}, ${Math.round(200 + glow * 40)}, 240)`);
  g.addColorStop(0.55, `rgb(${Math.round(70 + glow * 40)}, ${Math.round(140 + glow * 40)}, 210)`);
  g.addColorStop(0.86, "#225f97");
  g.addColorStop(0.95, "#0d2b47");
  g.addColorStop(1, "#071a2c");
  c.fillStyle = g;
  c.fillRect(0, 0, w, h);
  const rand = mulberry(42);
  // Stroma fibres: light and dark radial streaks
  for (let i = 0; i < 900; i++) {
    const x = rand() * w;
    const y0 = py + rand() * (h - py) * 0.25;
    const len = (h - py) * (0.25 + rand() * 0.65);
    const light = rand() > 0.45;
    c.strokeStyle = light ? `rgba(225, 242, 255, ${0.05 + rand() * 0.16})` : `rgba(8, 26, 52, ${0.08 + rand() * 0.22})`;
    c.lineWidth = 0.5 + rand() * 1.6;
    c.beginPath();
    c.moveTo(x, y0);
    c.bezierCurveTo(x + (rand() - 0.5) * 6, y0 + len * 0.4, x + (rand() - 0.5) * 6, y0 + len * 0.7, x + (rand() - 0.5) * 4, y0 + len);
    c.stroke();
  }
  // Crypts (darker pits)
  for (let i = 0; i < 60; i++) {
    c.fillStyle = `rgba(10, 30, 55, ${0.15 + rand() * 0.25})`;
    c.beginPath();
    c.ellipse(rand() * w, py + (h - py) * (0.2 + rand() * 0.5), 1 + rand() * 3, 3 + rand() * 7, 0, 0, Math.PI * 2);
    c.fill();
  }
  // Collarette
  c.fillStyle = "rgba(235, 215, 175, 0.16)";
  c.fillRect(0, py + (h - py) * 0.2, w, 2.5);
}

function makeScleraTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 512;
  const c = canvas.getContext("2d")!;
  const g = c.createLinearGradient(0, 0, 0, 512);
  g.addColorStop(0, "#e8d6cf");
  g.addColorStop(0.5, "#fbf7f5");
  g.addColorStop(1, "#e4cfc7");
  c.fillStyle = g;
  c.fillRect(0, 0, 1024, 512);
  // Veins converging towards the front (u = 0.25 is +Z)
  const rand = mulberry(7);
  for (let i = 0; i < 70; i++) {
    const side = rand() > 0.5 ? 1 : -1;
    let x = 256 + side * (120 + rand() * 260);
    let y = 256 + (rand() - 0.5) * 220;
    c.strokeStyle = `rgba(185, 60, 60, ${0.1 + rand() * 0.25})`;
    c.lineWidth = 0.5 + rand() * 1.4;
    c.beginPath();
    c.moveTo(x, y);
    for (let s = 0; s < 8; s++) {
      x += -side * (6 + rand() * 14);
      y += (rand() - 0.5) * 16;
      c.lineTo(x, y);
    }
    c.stroke();
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

// ------------------------------------------------------------------ eye model
interface EyeRig {
  ball: THREE.Group; // rotates with the gaze; blinks by a quick vertical squash
}

interface EyeParts {
  scleraGeo: THREE.BufferGeometry;
  irisGeo: THREE.BufferGeometry;
  corneaGeo: THREE.BufferGeometry;
  sclera: THREE.Material;
  iris: THREE.Material;
  cornea: THREE.Material;
}

function buildEye(parts: EyeParts): EyeRig {
  const ball = new THREE.Group();
  ball.add(new THREE.Mesh(parts.scleraGeo, parts.sclera));
  const iris = new THREE.Mesh(parts.irisGeo, parts.iris);
  iris.rotation.x = Math.PI / 2;
  ball.add(iris);
  const cornea = new THREE.Mesh(parts.corneaGeo, parts.cornea);
  cornea.rotation.x = Math.PI / 2;
  ball.add(cornea);
  return { ball };
}

export function ArchangelScene({ state, mood = "neutral", speechEnergy = 0, music, onClick, onFail }: ArchangelSceneProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const live = useRef({ state, mood, speechEnergy, music });
  live.current = { state, mood, speechEnergy, music };
  const onFailRef = useRef(onFail);
  onFailRef.current = onFail;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const capture = new URLSearchParams(window.location.search).has("capture");

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        powerPreference: "high-performance",
        preserveDrawingBuffer: capture, // screenshots only
      });
    } catch {
      onFailRef.current?.();
      return;
    }
    let pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(host.clientWidth, host.clientHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.display = "block";
    host.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#a9cbea");
    const camera = new THREE.PerspectiveCamera(32, host.clientWidth / host.clientHeight, 0.1, 100);
    camera.position.set(0, 0.1, 7.6);

    // Reflections from the very first frame (studio env), replaced by the HDRI sky when ready
    const pmrem = new THREE.PMREMGenerator(renderer);
    const roomEnv = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = roomEnv;
    let skyEnv: THREE.Texture | null = null;
    new RGBELoader().load(
      SKY_URL,
      (hdr) => {
        hdr.mapping = THREE.EquirectangularReflectionMapping;
        skyEnv = pmrem.fromEquirectangular(hdr).texture;
        scene.background = hdr;
        scene.backgroundBlurriness = 0.02;
        scene.backgroundIntensity = 1.05;
        scene.backgroundRotation.set(-0.16, 2.2, 0);
        scene.environment = skyEnv;
        scene.environmentRotation.set(-0.16, 2.2, 0);
      },
      undefined,
      () => undefined,
    );

    // Divine light: warm key from above, soft fill, golden back rim
    const key = new THREE.DirectionalLight("#fff0d8", 2.2);
    key.position.set(-3, 6, 4);
    scene.add(key);
    const fill = new THREE.DirectionalLight("#d8e8ff", 0.5);
    fill.position.set(4, -2, 3);
    scene.add(fill);
    const rimLight = new THREE.DirectionalLight("#ffd6a6", 1.4);
    rimLight.position.set(0, 3, -6);
    scene.add(rimLight);
    scene.add(new THREE.HemisphereLight("#fff6ea", "#d9c0b4", 0.35));

    // --- band material: rose-gold with an engraved diamond pattern + beaded edges as bump
    const engr = document.createElement("canvas");
    engr.width = 512;
    engr.height = 64;
    {
      const c = engr.getContext("2d")!;
      c.fillStyle = "#808080";
      c.fillRect(0, 0, 512, 64);
      c.strokeStyle = "#5c5c5c";
      c.lineWidth = 2;
      for (let x = 0; x < 512; x += 16) {
        c.beginPath();
        c.moveTo(x, 32);
        c.lineTo(x + 8, 20);
        c.lineTo(x + 16, 32);
        c.lineTo(x + 8, 44);
        c.closePath();
        c.stroke();
      }
      c.fillStyle = "#b0b0b0";
      c.fillRect(0, 4, 512, 3);
      c.fillRect(0, 57, 512, 3);
    }
    const engrTex = new THREE.CanvasTexture(engr);
    engrTex.wrapS = THREE.RepeatWrapping;
    engrTex.repeat.set(10, 1);
    const roseGold = new THREE.MeshPhysicalMaterial({
      color: "#f4c3ad",
      metalness: 1,
      roughness: 0.24,
      clearcoat: 0.5,
      clearcoatRoughness: 0.15,
      bumpMap: engrTex,
      bumpScale: 0.6,
    });

    // --- eye materials
    const irisCanvas = document.createElement("canvas");
    irisCanvas.width = 512;
    irisCanvas.height = 512;
    let irisPupil = 0.36;
    let irisGlow = 0.1;
    drawIris(irisCanvas, irisPupil, irisGlow);
    const irisTex = new THREE.CanvasTexture(irisCanvas);
    irisTex.colorSpace = THREE.SRGBColorSpace;
    irisTex.anisotropy = 4;

    const sclera = new THREE.MeshPhysicalMaterial({ map: makeScleraTexture(), roughness: 0.28, clearcoat: 0.8, clearcoatRoughness: 0.08 });
    const iris = new THREE.MeshStandardMaterial({
      map: irisTex,
      emissiveMap: irisTex,
      emissive: new THREE.Color("#ffffff"),
      emissiveIntensity: 0.1,
      roughness: 0.5,
    });
    const cornea = new THREE.MeshPhysicalMaterial({
      color: "#ffffff",
      transparent: true,
      opacity: 0.08,
      roughness: 0,
      clearcoat: 1,
      clearcoatRoughness: 0,
      envMapIntensity: 3,
      depthWrite: false,
    });
    const bigParts: EyeParts = {
      scleraGeo: new THREE.SphereGeometry(1, 64, 48),
      irisGeo: new THREE.SphereGeometry(1.003, 64, 24, 0, Math.PI * 2, 0, 0.6),
      corneaGeo: new THREE.SphereGeometry(1.04, 64, 20, 0, Math.PI * 2, 0, 0.7),
      sclera,
      iris,
      cornea,
    };
    const smallParts: EyeParts = {
      scleraGeo: new THREE.SphereGeometry(1, 20, 14),
      irisGeo: new THREE.SphereGeometry(1.004, 20, 8, 0, Math.PI * 2, 0, 0.6),
      corneaGeo: new THREE.SphereGeometry(1.04, 20, 8, 0, Math.PI * 2, 0, 0.7),
      sclera,
      iris,
      cornea,
    };

    // --- the being
    const being = new THREE.Group();
    scene.add(being);

    const socket = new THREE.Group(); // faces the camera; lids live here, eyeball rotates inside
    socket.scale.setScalar(0.66);
    being.add(socket);
    const centralEye = buildEye(bigParts);
    socket.add(centralEye.ball);
    const fleshMat = new THREE.MeshPhysicalMaterial({
      color: "#e8a593",
      roughness: 0.45,
      sheen: 0.8,
      sheenColor: new THREE.Color("#ffd9cc"),
      clearcoat: 0.3,
    });
    const rim = new THREE.Mesh(new THREE.TorusGeometry(0.98, 0.2, 32, 96), fleshMat);
    rim.position.z = -0.05;
    socket.add(rim);

    interface RingRig {
      spec: RingSpec;
      pivot: THREE.Group;
      spinner: THREE.Group;
      eyes: { rig: EyeRig; holder: THREE.Group }[];
    }
    const rings: RingRig[] = RINGS.map((spec) => {
      // Rounded-rectangle cross-section revolved around the ring axis → smooth wide band
      const pts: THREE.Vector2[] = [];
      const rIn = spec.radius - spec.thickness / 2;
      const rOut = spec.radius + spec.thickness / 2;
      const hw = spec.width / 2;
      const round = spec.thickness * 0.45;
      const arc = (cx: number, cy: number, a0: number, a1: number) => {
        for (let i = 0; i <= 6; i++) {
          const a = a0 + ((a1 - a0) * i) / 6;
          pts.push(new THREE.Vector2(cx + Math.cos(a) * round, cy + Math.sin(a) * round));
        }
      };
      arc(rIn + round, -hw + round, Math.PI, Math.PI * 1.5);
      arc(rOut - round, -hw + round, Math.PI * 1.5, Math.PI * 2);
      arc(rOut - round, hw - round, 0, Math.PI * 0.5);
      arc(rIn + round, hw - round, Math.PI * 0.5, Math.PI);
      pts.push(pts[0].clone());
      const band = new THREE.Mesh(new THREE.LatheGeometry(pts, 220), roseGold);
      band.rotation.x = Math.PI / 2; // lathe axis Y → ring axis Z

      const pivot = new THREE.Group();
      pivot.rotation.copy(spec.tilt);
      being.add(pivot);
      const spinner = new THREE.Group();
      pivot.add(spinner);
      spinner.add(band);

      const eyes = Array.from({ length: spec.eyes }, (_, i) => {
        const a = (i / spec.eyes) * Math.PI * 2;
        const holder = new THREE.Group();
        const eyeR = spec.width * 0.3;
        const embed = rOut - eyeR * 0.55; // sunk into the band, only the front shows
        holder.position.set(Math.cos(a) * embed, Math.sin(a) * embed, 0);
        holder.lookAt(new THREE.Vector3(Math.cos(a) * 10, Math.sin(a) * 10, 0));
        holder.scale.setScalar(eyeR);
        const rig = buildEye(smallParts);
        holder.add(rig.ball);
        spinner.add(holder);
        return { rig, holder };
      });
      return { spec, pivot, spinner, eyes };
    });

    // Motes of light
    const moteCount = 160;
    const moteGeo = new THREE.BufferGeometry();
    const motePos = new Float32Array(moteCount * 3);
    const rnd = mulberry(99);
    for (let i = 0; i < moteCount; i++) {
      motePos[i * 3] = (rnd() - 0.5) * 12;
      motePos[i * 3 + 1] = (rnd() - 0.5) * 8;
      motePos[i * 3 + 2] = (rnd() - 0.5) * 6 - 1;
    }
    moteGeo.setAttribute("position", new THREE.BufferAttribute(motePos, 3));
    const moteMat = new THREE.PointsMaterial({
      color: "#fff2cf",
      size: 0.03,
      transparent: true,
      opacity: 0.8,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    scene.add(new THREE.Points(moteGeo, moteMat));

    // Post-processing
    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(host.clientWidth, host.clientHeight), 0.28, 0.5, 0.88);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());
    let useBloom = true;

    const resize = () => {
      const w = host.clientWidth;
      const h = host.clientHeight;
      camera.aspect = w / h;
      camera.position.z = w < h ? 7.6 * (h / w) * 0.75 : 7.6;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h);
    };
    window.addEventListener("resize", resize);
    resize();

    const pointer = { x: 0, y: 0, until: 0 };
    const onMove = (e: PointerEvent) => {
      pointer.x = (e.clientX / window.innerWidth - 0.5) * 2;
      pointer.y = (e.clientY / window.innerHeight - 0.5) * 2;
      pointer.until = performance.now() + 2500;
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    const sim = {
      angle: 0,
      gazeX: 0,
      gazeY: 0,
      tgx: 0,
      tgy: 0,
      nextSaccade: 0,
      pupil: 0.36,
      lid: 0,
      blinkUntil: 0,
      nextBlink: performance.now() + 2500,
      glow: 0.1,
      bob: 0,
    };
    const target = new THREE.Vector3();
    const wp = new THREE.Vector3();
    const wn = new THREE.Vector3();
    const wq = new THREE.Quaternion();
    const toT = new THREE.Vector3();

    let frames = 0;
    let fpsStart = performance.now();
    let last = performance.now();
    let raf = 0;
    let stopped = false;

    const frame = (now: number) => {
      if (stopped) return;
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const sec = now / 1000;
      const { state: st, mood: md, speechEnergy: energy, music: mu } = live.current;
      const dancing = Boolean(mu?.playing && mu.bpm > 0);

      let speed = 1;
      if (st === "processing" || st === "executing") speed = 3.2;
      else if (st === "speaking") speed = 1.6;
      else if (st === "listening") speed = 0.55;
      if (dancing) speed = Math.max(speed, (mu!.bpm / 60) * 0.6);
      sim.angle += dt * speed * SPIN * 0.25;

      if (now >= sim.nextSaccade) {
        sim.tgx = (Math.random() - 0.5) * 0.9;
        sim.tgy = (Math.random() - 0.5) * 0.5;
        sim.nextSaccade = now + (st === "processing" ? 450 : 1600) + Math.random() * 1800;
      }
      let gx = sim.tgx;
      let gy = sim.tgy;
      if (now < pointer.until) {
        gx = pointer.x;
        gy = pointer.y;
      }
      if (st === "listening" || st === "speaking") {
        gx *= 0.2;
        gy *= 0.2;
      }
      if (st === "processing") {
        gx = 0.8 * Math.cos(sec * 1.7);
        gy = -0.7;
      }
      sim.gazeX = THREE.MathUtils.lerp(sim.gazeX, gx, 0.1);
      sim.gazeY = THREE.MathUtils.lerp(sim.gazeY, gy, 0.1);

      const tp = st === "listening" ? 0.46 : st === "speaking" ? 0.36 + energy * 0.1 : md === "surprised" ? 0.22 : 0.32;
      sim.pupil = THREE.MathUtils.lerp(sim.pupil, tp, 0.08);
      if (now >= sim.nextBlink) {
        sim.blinkUntil = now + BLINK_MS; // blink window [blinkUntil - BLINK_MS, blinkUntil]
        sim.nextBlink = now + 2600 + Math.random() * 3600;
      }
      const tg = st === "speaking" ? 0.55 + energy * 0.45 : st === "listening" ? 0.35 : st === "processing" ? 0.45 : 0.1;
      sim.glow = THREE.MathUtils.lerp(sim.glow, tg, 0.1);
      const tb = dancing ? Math.abs(Math.sin(Math.PI * sec * (mu!.bpm / 60))) * -0.18 : Math.sin(sec * 0.9) * 0.06;
      sim.bob = THREE.MathUtils.lerp(sim.bob, tb, dancing ? 0.35 : 0.08);

      // Textures only when they visibly change
      if (Math.abs(sim.pupil - irisPupil) > 0.012 || Math.abs(sim.glow - irisGlow) > 0.05) {
        irisPupil = sim.pupil;
        irisGlow = sim.glow;
        drawIris(irisCanvas, irisPupil, irisGlow);
        irisTex.needsUpdate = true;
      }
      // Time-based blink (same speed on any GPU): close and reopen within BLINK_MS
      const into = BLINK_MS - (sim.blinkUntil - now);
      sim.lid = into >= 0 && into <= BLINK_MS ? Math.sin((Math.PI * into) / BLINK_MS) : 0;
      const blinkSquash = 1 - sim.lid * 0.92;
      iris.emissiveIntensity = 0.06 + sim.glow * 0.5;
      bloom.strength = 0.22 + sim.glow * 0.4;

      being.position.y = sim.bob;
      being.rotation.z = dancing ? Math.sin(Math.PI * sec * (mu!.bpm / 60)) * 0.06 : Math.sin(sec * 0.4) * 0.02;

      target.set(sim.gazeX * 2.6, -sim.gazeY * 1.8 + 0.1, camera.position.z);
      socket.lookAt(camera.position);
      centralEye.ball.lookAt(target);
      centralEye.ball.scale.set(1, blinkSquash, 1);

      rings.forEach((ring, ri) => {
        ring.spinner.rotation.z = sim.angle * ring.spec.spin * 6;
        ring.pivot.rotation.x = ring.spec.tilt.x + Math.sin(sim.angle * 0.9 + ri) * ring.spec.wobble;
        ring.pivot.rotation.y = ring.spec.tilt.y + sim.angle * ring.spec.spin * 1.4;
        for (const { rig, holder } of ring.eyes) {
          holder.getWorldPosition(wp);
          holder.getWorldQuaternion(wq);
          wn.set(0, 0, 1).applyQuaternion(wq);
          toT.copy(target).sub(wp).normalize();
          const facing = toT.dot(wn);
          rig.ball.scale.set(1, 1 - sim.lid * 0.85, 1);
          if (facing > 0.2) {
            toT.multiplyScalar(0.5).add(wn.multiplyScalar(0.5)).normalize();
            rig.ball.lookAt(wp.add(toT));
          } else {
            rig.ball.quaternion.identity();
          }
        }
      });

      const p = moteGeo.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < moteCount; i++) {
        let y = p.getY(i) + dt * (0.08 + (i % 7) * 0.02);
        if (y > 4) y = -4;
        p.setY(i, y);
      }
      p.needsUpdate = true;

      if (useBloom) composer.render();
      else renderer.render(scene, camera);

      // Adaptive quality for weak GPUs (disabled for screenshots)
      frames++;
      if (!capture && now - fpsStart > 2500) {
        const fps = (frames * 1000) / (now - fpsStart);
        frames = 0;
        fpsStart = now;
        if (fps < 26 && pixelRatio > 1) {
          pixelRatio = 1;
          renderer.setPixelRatio(1);
          composer.setPixelRatio(1);
        } else if (fps < 24 && useBloom) {
          useBloom = false;
        } else if (fps < 20 && pixelRatio > 0.75) {
          pixelRatio = 0.75;
          renderer.setPixelRatio(0.75);
        }
      }
      raf = requestAnimationFrame(frame);
    };
    frame(performance.now());

    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onMove);
      scene.traverse((obj) => (obj as THREE.Mesh).geometry?.dispose?.());
      [roseGold, sclera, iris, cornea, fleshMat, moteMat].forEach((m) => m.dispose());
      [irisTex, engrTex, roomEnv].forEach((t) => t.dispose());
      skyEnv?.dispose();
      pmrem.dispose();
      composer.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return (
    <div
      ref={hostRef}
      onClick={onClick}
      className="fixed inset-0 z-0 h-full w-full cursor-pointer"
      title={`Arcanjo · ${state}`}
    />
  );
}
