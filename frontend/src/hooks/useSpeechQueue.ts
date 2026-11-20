import { useCallback, useRef, useState } from "react";
import { apiClient } from "../services/api";

interface UseSpeechQueueOptions {
  voiceEnabled: boolean;
  ttsAvailable: boolean;
  voiceName: string;
  onSpeakingStart: () => void;
  onSpeakingEnd: () => void;
}

interface UseSpeechQueueResult {
  speechEnergy: number;
  unlockAudio: () => Promise<void>;
  pushStreamDelta: (delta: string) => void;
  flushStreamEnd: (fullText: string) => void;
  speakImmediate: (text: string) => void;
  stopAll: () => void;
}

function findSentenceBreak(text: string): number {
  for (let i = 0; i < text.length - 1; i++) {
    const ch = text[i];
    const next = text[i + 1];
    if ((ch === "." || ch === "!" || ch === "?") && /\s/.test(next)) {
      const candidate = text.slice(0, i + 1).trim();
      // Avoid splitting acronyms like "J.A.R.V.I.S." or single-letter abbreviations
      if (candidate.length >= 16 && !/\b[A-Z]\.$/.test(candidate)) {
        return i + 1;
      }
    } else if (ch === "\n" && i >= 16) {
      return i + 1;
    }
  }
  return -1;
}

export function useSpeechQueue({
  voiceEnabled,
  ttsAvailable,
  voiceName,
  onSpeakingStart,
  onSpeakingEnd,
}: UseSpeechQueueOptions): UseSpeechQueueResult {
  const [speechEnergy, setSpeechEnergy] = useState(0);

  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const meterFrameRef = useRef<number | null>(null);
  const silentTimerRef = useRef<number | null>(null);

  const sessionSeqRef = useRef(0);
  const streamBufferRef = useRef("");
  const queuedCharsRef = useRef(0);
  const playbackQueueRef = useRef<Array<Promise<Blob | null>>>([]);
  const isPlayingLoopRef = useRef(false);
  const streamFinishedRef = useRef(true);

  const voiceEnabledRef = useRef(voiceEnabled);
  voiceEnabledRef.current = voiceEnabled;
  const ttsAvailableRef = useRef(ttsAvailable);
  ttsAvailableRef.current = ttsAvailable;
  const voiceNameRef = useRef(voiceName);
  voiceNameRef.current = voiceName;

  const audioUnlockedRef = useRef(false);

  const unlockAudio = useCallback(async () => {
    if (!audioCtxRef.current && window.AudioContext) {
      audioCtxRef.current = new window.AudioContext();
    }
    if (audioCtxRef.current?.state === "suspended") {
      try {
        await audioCtxRef.current.resume();
      } catch {
        // Ignore resume errors
      }
    }
    if (!audioUnlockedRef.current) {
      audioUnlockedRef.current = true;
      try {
        const silent = new Audio(
          "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA",
        );
        silent.volume = 0.0;
        await silent.play().catch(() => undefined);
      } catch {
        // Ignore autoplay unlock errors
      }
    }
  }, []);

  const cleanupCurrentAudio = useCallback(() => {
    if (silentTimerRef.current) {
      window.clearTimeout(silentTimerRef.current);
      silentTimerRef.current = null;
    }
    if (meterFrameRef.current) {
      window.cancelAnimationFrame(meterFrameRef.current);
      meterFrameRef.current = null;
    }
    if (audioElRef.current) {
      audioElRef.current.onplay = null;
      audioElRef.current.onended = null;
      audioElRef.current.onerror = null;
      audioElRef.current.pause();
      audioElRef.current.removeAttribute("src");
      audioElRef.current.load();
      audioElRef.current = null;
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
    setSpeechEnergy(0);
  }, []);

  const stopAll = useCallback(() => {
    sessionSeqRef.current += 1;
    streamBufferRef.current = "";
    queuedCharsRef.current = 0;
    playbackQueueRef.current = [];
    isPlayingLoopRef.current = false;
    streamFinishedRef.current = true;
    cleanupCurrentAudio();
  }, [cleanupCurrentAudio]);

  const playBlob = useCallback(
    async (blob: Blob, seq: number): Promise<void> => {
      if (seq !== sessionSeqRef.current) return;
      cleanupCurrentAudio();

      const objectUrl = URL.createObjectURL(blob);
      audioUrlRef.current = objectUrl;
      const audio = new Audio(objectUrl);
      audioElRef.current = audio;

      await new Promise<void>((resolve) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          cleanupCurrentAudio();
          resolve();
        };

        audio.onended = finish;
        audio.onerror = finish;

        const startMeter = async () => {
          onSpeakingStart();
          const AudioCtx = window.AudioContext;
          if (AudioCtx) {
            if (!audioCtxRef.current) {
              audioCtxRef.current = new AudioCtx();
            }
            const ctx = audioCtxRef.current;
            if (ctx.state === "suspended") {
              await ctx.resume().catch(() => undefined);
            }
            try {
              const source = ctx.createMediaElementSource(audio);
              const analyser = ctx.createAnalyser();
              analyser.fftSize = 128;
              source.connect(analyser);
              analyser.connect(ctx.destination);

              const dataArray = new Uint8Array(analyser.frequencyBinCount);
              const tick = () => {
                if (seq !== sessionSeqRef.current || audio.paused || audio.ended) return;
                analyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                const avg = sum / (dataArray.length * 255);
                setSpeechEnergy(Math.min(1.4, avg * 2.9));
                meterFrameRef.current = window.requestAnimationFrame(tick);
              };
              meterFrameRef.current = window.requestAnimationFrame(tick);
            } catch {
              setSpeechEnergy(0.8);
            }
          } else {
            setSpeechEnergy(0.8);
          }
        };

        audio.onplay = () => {
          void startMeter();
        };

        audio.play().catch(finish);
      });
    },
    [cleanupCurrentAudio, onSpeakingStart],
  );

  const drainPlaybackQueue = useCallback(
    async (seq: number) => {
      if (isPlayingLoopRef.current) return;
      isPlayingLoopRef.current = true;

      try {
        while (seq === sessionSeqRef.current) {
          const nextJob = playbackQueueRef.current.shift();
          if (!nextJob) {
            if (streamFinishedRef.current) {
              break;
            }
            await new Promise((r) => window.setTimeout(r, 40));
            continue;
          }
          const blob = await nextJob;
          if (seq !== sessionSeqRef.current) return;
          if (blob) {
            await playBlob(blob, seq);
          }
        }
      } finally {
        if (seq === sessionSeqRef.current) {
          isPlayingLoopRef.current = false;
          setSpeechEnergy(0);
          onSpeakingEnd();
        }
      }
    },
    [onSpeakingEnd, playBlob],
  );

  const enqueueSentence = useCallback(
    (sentence: string) => {
      const clean = sentence.trim();
      if (!clean) return;

      const seq = sessionSeqRef.current;
      if (!voiceEnabledRef.current || !ttsAvailableRef.current) {
        playbackQueueRef.current.push(Promise.resolve(null));
        void drainPlaybackQueue(seq);
        return;
      }

      // Immediately start synthesizing this sentence while LLM streams the rest
      const synthPromise = apiClient
        .synthesizeSpeech(clean, voiceNameRef.current)
        .catch(() => null);
      playbackQueueRef.current.push(synthPromise);
      void drainPlaybackQueue(seq);
    },
    [drainPlaybackQueue],
  );

  const pushStreamDelta = useCallback(
    (delta: string) => {
      if (streamFinishedRef.current) {
        sessionSeqRef.current += 1;
        streamBufferRef.current = "";
        queuedCharsRef.current = 0;
        playbackQueueRef.current = [];
        isPlayingLoopRef.current = false;
        streamFinishedRef.current = false;
      }

      streamBufferRef.current += delta;

      let breakIdx = findSentenceBreak(streamBufferRef.current);
      while (breakIdx !== -1) {
        const sentence = streamBufferRef.current.slice(0, breakIdx).trim();
        streamBufferRef.current = streamBufferRef.current.slice(breakIdx).trimStart();
        queuedCharsRef.current += sentence.length;
        enqueueSentence(sentence);
        breakIdx = findSentenceBreak(streamBufferRef.current);
      }
    },
    [enqueueSentence],
  );

  const flushStreamEnd = useCallback(
    (fullText: string) => {
      // Handle non-streamed responses (like assistant.greet) where pushStreamDelta wasn't called
      if (streamFinishedRef.current && playbackQueueRef.current.length === 0) {
        sessionSeqRef.current += 1;
        streamBufferRef.current = fullText;
        queuedCharsRef.current = 0;
      }

      streamFinishedRef.current = true;
      const tail = streamBufferRef.current.trim();
      streamBufferRef.current = "";

      if (tail) {
        enqueueSentence(tail);
      } else if (playbackQueueRef.current.length === 0 && !isPlayingLoopRef.current) {
        onSpeakingEnd();
      }
    },
    [enqueueSentence, onSpeakingEnd],
  );

  const speakImmediate = useCallback(
    (text: string) => {
      stopAll();
      sessionSeqRef.current += 1;
      streamFinishedRef.current = true;
      enqueueSentence(text);
    },
    [enqueueSentence, stopAll],
  );

  return {
    speechEnergy,
    unlockAudio,
    pushStreamDelta,
    flushStreamEnd,
    speakImmediate,
    stopAll,
  };
}
