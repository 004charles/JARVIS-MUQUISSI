import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../services/api";
import type { AssistantState } from "../types/api";
import { encodeWav16k } from "../utils/wavEncoder";

interface UseContinuousVoiceOptions {
  assistantState: AssistantState;
  autoStartAllowed: boolean;
  onTranscript: (text: string) => void;
  onStateHint?: (state: AssistantState) => void;
}

interface UseContinuousVoiceResult {
  micActive: boolean;
  transcribing: boolean;
  micLevel: number;
  micError: string | null;
  toggleMic: () => void;
  startMic: () => void;
}

const MIN_SPEECH_THRESHOLD = 0.009;
const NOISE_FLOOR_MULTIPLIER = 2.0;
const SILENCE_HANGOVER_MS = 700;
const MIN_SPEECH_MS = 280;
const MAX_UTTERANCE_MS = 15000;
const PRE_ROLL_FRAMES = 14;
const POST_SPEECH_ECHO_GUARD_MS = 1000;

export function useContinuousVoice({
  assistantState,
  autoStartAllowed,
  onTranscript,
  onStateHint,
}: UseContinuousVoiceOptions): UseContinuousVoiceResult {
  const [micActive, setMicActive] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [micError, setMicError] = useState<string | null>(null);
  const autoCheckedRef = useRef(false);

  useEffect(() => {
    if (!autoStartAllowed || autoCheckedRef.current) return;
    autoCheckedRef.current = true;
    if (localStorage.getItem("jarvis_browser_mic_disabled") === "1") return;
    // Try enabling microphone directly (navigator.permissions.query fails/stays 'prompt' in Firefox)
    setMicActive(true);
  }, [autoStartAllowed]);

  const assistantStateRef = useRef(assistantState);
  const echoGuardUntilRef = useRef(0);
  if (
    (assistantStateRef.current === "speaking" || assistantStateRef.current === "processing") &&
    assistantState !== "speaking" &&
    assistantState !== "processing"
  ) {
    echoGuardUntilRef.current = performance.now() + POST_SPEECH_ECHO_GUARD_MS;
  }
  assistantStateRef.current = assistantState;

  const transcribingRef = useRef(false);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;
  const onStateHintRef = useRef(onStateHint);
  onStateHintRef.current = onStateHint;

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const procRef = useRef<ScriptProcessorNode | null>(null);

  const stopCapture = useCallback(() => {
    if (procRef.current) {
      procRef.current.disconnect();
      procRef.current.onaudioprocess = null;
      procRef.current = null;
    }
    if (ctxRef.current) {
      void ctxRef.current.close();
      ctxRef.current = null;
    }
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }
    setMicLevel(0);
  }, []);

  useEffect(() => {
    if (!micActive) {
      stopCapture();
      return;
    }

    let cancelled = false;

    const startCapture = async () => {
      try {
        setMicError(null);
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("Microfone não suportado neste navegador.");
        }

        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        if (cancelled) {
          for (const track of stream.getTracks()) track.stop();
          return;
        }
        streamRef.current = stream;

        const audioCtx = new window.AudioContext();
        ctxRef.current = audioCtx;
        const source = audioCtx.createMediaStreamSource(stream);
        const processor = audioCtx.createScriptProcessor(2048, 1, 1);
        procRef.current = processor;

        const preRoll: Float32Array[] = [];
        let speechChunks: Float32Array[] = [];
        let speakingNow = false;
        let speechStartMs = 0;
        let lastVoiceMs = 0;
        let consecutiveLoud = 0;
        let noiseFloor = 0.006;

        const flushUtterance = async (sampleRate: number) => {
          const captured = speechChunks;
          speechChunks = [];
          speakingNow = false;
          consecutiveLoud = 0;

          const durationMs = performance.now() - speechStartMs;
          if (durationMs < MIN_SPEECH_MS || captured.length === 0) {
            onStateHintRef.current?.("idle");
            return;
          }

          transcribingRef.current = true;
          setTranscribing(true);
          onStateHintRef.current?.("processing");

          try {
            const wavBlob = encodeWav16k(captured, sampleRate);
            const result = await apiClient.transcribeAudio(wavBlob, "pt");
            const cleanText = result.text.trim();
            if (cleanText.length >= 2) {
              onTranscriptRef.current(cleanText);
            } else {
              onStateHintRef.current?.("idle");
            }
          } catch (err) {
            setMicError(
              err instanceof Error ? err.message : "Erro ao transcrever voz.",
            );
            onStateHintRef.current?.("idle");
          } finally {
            transcribingRef.current = false;
            setTranscribing(false);
          }
        };

        processor.onaudioprocess = (event) => {
          const currentState = assistantStateRef.current;
          const now = performance.now();
          // Pause mic capture while Arcanjo is processing, speaking, or within echo cooldown
          if (
            transcribingRef.current ||
            now < echoGuardUntilRef.current ||
            currentState === "processing" ||
            currentState === "speaking" ||
            currentState === "executing"
          ) {
            speechChunks = [];
            speakingNow = false;
            consecutiveLoud = 0;
            setMicLevel(0);
            return;
          }

          const inputData = event.inputBuffer.getChannelData(0);
          const frameCopy = new Float32Array(inputData);

          let sumSq = 0;
          for (let i = 0; i < frameCopy.length; i++) {
            sumSq += frameCopy[i] * frameCopy[i];
          }
          const rms = Math.sqrt(sumSq / frameCopy.length);

          // Track ambient noise floor continuously while nobody is talking
          if (!speakingNow) {
            const clampedRms = Math.min(0.03, rms);
            noiseFloor = Math.max(0.003, Math.min(0.025, noiseFloor * 0.96 + clampedRms * 0.04));
          }

          const triggerThreshold = Math.max(
            MIN_SPEECH_THRESHOLD,
            noiseFloor * NOISE_FLOOR_MULTIPLIER,
          );
          const sustainThreshold = triggerThreshold * 0.72;
          const activeThreshold = speakingNow ? sustainThreshold : triggerThreshold;

          setMicLevel(Math.min(1.2, Math.max(0, rms - noiseFloor) * 16));

          if (rms >= activeThreshold) {
            consecutiveLoud += 1;
            lastVoiceMs = now;
            if (!speakingNow && consecutiveLoud >= 2) {
              speakingNow = true;
              speechStartMs = now;
              speechChunks = [...preRoll];
              onStateHintRef.current?.("listening");
            }
          } else {
            consecutiveLoud = 0;
          }

          if (speakingNow) {
            speechChunks.push(frameCopy);
            const silenceElapsed = now - lastVoiceMs;
            const totalElapsed = now - speechStartMs;
            if (silenceElapsed >= SILENCE_HANGOVER_MS || totalElapsed >= MAX_UTTERANCE_MS) {
              void flushUtterance(audioCtx.sampleRate);
            }
          } else {
            preRoll.push(frameCopy);
            if (preRoll.length > PRE_ROLL_FRAMES) {
              preRoll.shift();
            }
          }
        };

        source.connect(processor);
        // Connect to a silent gain node so onaudioprocess fires without echoing mic to speakers
        const silentGain = audioCtx.createGain();
        silentGain.gain.value = 0;
        processor.connect(silentGain);
        silentGain.connect(audioCtx.destination);
        onStateHintRef.current?.("idle");
      } catch (err) {
        setMicError(
          err instanceof Error ? err.message : "Não foi possível aceder ao microfone.",
        );
        setMicActive(false);
      }
    };

    void startCapture();

    return () => {
      cancelled = true;
      stopCapture();
    };
  }, [micActive, stopCapture]);

  const startMic = useCallback(() => {
    localStorage.setItem("jarvis_browser_mic_disabled", "0");
    setMicError(null);
    setMicActive(true);
  }, []);

  const toggleMic = useCallback(() => {
    setMicActive((prev) => {
      const next = !prev;
      localStorage.setItem("jarvis_browser_mic_disabled", next ? "0" : "1");
      if (!next) {
        onStateHintRef.current?.("idle");
      }
      return next;
    });
  }, []);

  return { micActive, transcribing, micLevel, micError, toggleMic, startMic };
}
