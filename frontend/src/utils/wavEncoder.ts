/** Downsample Float32 PCM chunks to 16 kHz mono 16-bit WAV Blob. */
export function encodeWav16k(
  chunks: Float32Array[],
  sourceSampleRate: number,
): Blob {
  let totalLength = 0;
  for (const chunk of chunks) {
    totalLength += chunk.length;
  }
  const merged = new Float32Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }

  const targetRate = 16000;
  const ratio = sourceSampleRate / targetRate;
  const outputLength = Math.max(1, Math.floor(merged.length / ratio));
  const buffer = new ArrayBuffer(44 + outputLength * 2);
  const view = new DataView(buffer);

  const writeStr = (pos: number, text: string) => {
    for (let i = 0; i < text.length; i++) {
      view.setUint8(pos + i, text.charCodeAt(i));
    }
  };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + outputLength * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // Mono
  view.setUint32(24, targetRate, true);
  view.setUint32(28, targetRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, outputLength * 2, true);

  let writePos = 44;
  for (let i = 0; i < outputLength; i++) {
    const srcIdx = Math.min(merged.length - 1, Math.floor(i * ratio));
    const sample = Math.max(-1, Math.min(1, merged[srcIdx]));
    view.setInt16(writePos, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    writePos += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}
