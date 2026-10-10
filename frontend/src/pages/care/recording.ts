import { useEffect, useRef, useState } from "react";

const MAX_SECONDS = 60;

export function useRecorder() {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [audio, setAudio] = useState<Blob | null>(null);
  const [error, setError] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);

  useEffect(() => {
    if (!recording) return;
    const startedAt = Date.now();
    const id = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      setSeconds(elapsed);
      if (elapsed >= MAX_SECONDS) recorderRef.current?.stop();
    }, 250);
    return () => clearInterval(id);
  }, [recording]);

  useEffect(() => () => recorderRef.current?.stop(), []);

  async function start() {
    setError("");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone access is blocked. Allow it in the browser's address bar, then try again.");
      return;
    }
    const recorder = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      setAudio(new Blob(chunks, { type: recorder.mimeType }));
      setRecording(false);
    };
    recorderRef.current = recorder;
    setAudio(null);
    setSeconds(0);
    recorder.start();
    setRecording(true);
  }

  function stop() {
    recorderRef.current?.stop();
  }

  return { recording, seconds, audio, error, start, stop, clear: () => setAudio(null) };
}

const WAV_SAMPLE_RATE = 24_000;
const WAV_MAX_SECONDS = 120;

/**
 * Converts any audio the browser can decode into 24 kHz 16-bit mono WAV, trimmed to 2 minutes
 * (about 5.8 MB at most). Voice cloning rejects some browser formats like WebM, but always takes WAV.
 * `seconds` is the length of the original audio.
 */
export async function toWav(blob: Blob): Promise<{ wav: Blob; seconds: number }> {
  const context = new AudioContext();
  const decoded = await context.decodeAudioData(await blob.arrayBuffer()).finally(() => context.close());

  const length = Math.ceil(Math.min(decoded.duration, WAV_MAX_SECONDS) * WAV_SAMPLE_RATE);
  const offline = new OfflineAudioContext(1, length, WAV_SAMPLE_RATE);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const buffer = await offline.startRendering();

  const samples = buffer.getChannelData(0);
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const text = (offset: number, s: string) => [...s].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));

  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, buffer.sampleRate, true);
  view.setUint32(28, buffer.sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));

  return { wav: new Blob([view], { type: "audio/wav" }), seconds: decoded.duration };
}
