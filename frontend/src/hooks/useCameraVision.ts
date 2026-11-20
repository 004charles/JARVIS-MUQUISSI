import { useCallback, useEffect, useRef, useState } from "react";

const CAMERA_DISABLED_KEY = "muquissi.camera.disabled";

interface UseCameraVisionOptions {
  connected: boolean;
  sendCommand: (message: Record<string, unknown>) => void;
}

export interface UseCameraVisionResult {
  cameraEnabled: boolean;
  cameraReady: boolean;
  cameraError: string | null;
  stream: MediaStream | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  enableCamera: () => Promise<boolean>;
  disableCamera: () => void;
  toggleCamera: () => Promise<void>;
  captureFrameB64: () => string | null;
  respondToCaptureRequest: (requestId: string) => void;
}

export function useCameraVision({
  connected,
  sendCommand,
}: UseCameraVisionOptions): UseCameraVisionResult {
  const [cameraEnabled, setCameraEnabled] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stopTracks = useCallback((target: MediaStream | null) => {
    if (!target) return;
    for (const track of target.getTracks()) {
      track.stop();
    }
  }, []);

  const disableCamera = useCallback(() => {
    window.localStorage.setItem(CAMERA_DISABLED_KEY, "true");
    stopTracks(streamRef.current);
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setStream(null);
    setCameraReady(false);
    setCameraEnabled(false);
    setCameraError(null);
  }, [stopTracks]);

  const enableCamera = useCallback(async (): Promise<boolean> => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Este navegador não suporta acesso à câmara.");
      setCameraEnabled(false);
      setCameraReady(false);
      return false;
    }

    try {
      window.localStorage.removeItem(CAMERA_DISABLED_KEY);
      setCameraError(null);

      // Reuse active stream if live video track already exists
      if (
        streamRef.current &&
        streamRef.current.getVideoTracks().some((t) => t.readyState === "live")
      ) {
        setCameraEnabled(true);
        return true;
      }

      const media = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: "user",
        },
        audio: false,
      });

      streamRef.current = media;
      setStream(media);
      setCameraEnabled(true);

      // Listen for hardware disconnect / track end
      const [videoTrack] = media.getVideoTracks();
      if (videoTrack) {
        videoTrack.onended = () => {
          setCameraReady(false);
          setCameraEnabled(false);
          setStream(null);
          streamRef.current = null;
        };
      }
      return true;
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Permissão da câmara recusada pelo navegador."
          : err instanceof DOMException && err.name === "NotFoundError"
            ? "Nenhuma câmara encontrada neste dispositivo."
            : "Não foi possível ligar a câmara do dispositivo.";
      setCameraError(msg);
      setCameraEnabled(false);
      setCameraReady(false);
      return false;
    }
  }, []);

  const toggleCamera = useCallback(async () => {
    if (cameraEnabled) {
      disableCamera();
    } else {
      await enableCamera();
    }
  }, [cameraEnabled, disableCamera, enableCamera]);

  // Attach MediaStream to hidden background <video> element for frame capture
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (!stream) {
      video.srcObject = null;
      setCameraReady(false);
      return;
    }

    video.srcObject = stream;
    const handleLoaded = () => {
      if (video.videoWidth > 0 && video.videoHeight > 0) {
        setCameraReady(true);
      }
    };

    video.addEventListener("loadeddata", handleLoaded);
    video.addEventListener("canplay", handleLoaded);
    video.play().catch(() => undefined);

    if (video.readyState >= 2 && video.videoWidth > 0) {
      setCameraReady(true);
    }

    return () => {
      video.removeEventListener("loadeddata", handleLoaded);
      video.removeEventListener("canplay", handleLoaded);
    };
  }, [stream]);

  // Auto-start if camera permission was already granted and user didn't turn it off
  useEffect(() => {
    if (window.localStorage.getItem(CAMERA_DISABLED_KEY) === "true") {
      return;
    }
    if (!navigator.permissions?.query) {
      return;
    }
    let cancelled = false;
    navigator.permissions
      .query({ name: "camera" as PermissionName })
      .then((status) => {
        if (!cancelled && status.state === "granted") {
          void enableCamera();
        }
      })
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, [enableCamera]);

  // Notify backend over WebSocket whenever camera readiness or socket connection changes
  useEffect(() => {
    if (!connected) return;
    sendCommand({ type: "vision.register", available: cameraReady });
  }, [connected, cameraReady, sendCommand]);

  // Cleanup camera stream on unmount
  useEffect(() => {
    return () => {
      stopTracks(streamRef.current);
      streamRef.current = null;
    };
  }, [stopTracks]);

  const captureFrameB64 = useCallback((): string | null => {
    const video = videoRef.current;
    if (!video || video.readyState < 2 || video.videoWidth === 0 || video.videoHeight === 0) {
      return null;
    }

    const maxWidth = 640;
    const scale = Math.min(1, maxWidth / video.videoWidth);
    const width = Math.max(1, Math.round(video.videoWidth * scale));
    const height = Math.max(1, Math.round(video.videoHeight * scale));

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;

    ctx.drawImage(video, 0, 0, width, height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
    const prefix = "data:image/jpeg;base64,";
    return dataUrl.startsWith(prefix) ? dataUrl.slice(prefix.length) : dataUrl;
  }, []);

  const respondToCaptureRequest = useCallback(
    (requestId: string) => {
      const frame = captureFrameB64();
      sendCommand({
        type: "vision.capture_response",
        request_id: requestId,
        image_b64: frame ?? "",
      });
    },
    [captureFrameB64, sendCommand],
  );

  return {
    cameraEnabled,
    cameraReady,
    cameraError,
    stream,
    videoRef,
    enableCamera,
    disableCamera,
    toggleCamera,
    captureFrameB64,
    respondToCaptureRequest,
  };
}
