let audio: AudioContext | null = null;

const NOTES = {
  // A slow rising pair before a reminder, so it never startles
  gentle: [523, 659],
  alert: [660, 880],
  urgent: [880, 660, 880, 660],
};

/** A soft chime, generated in the browser so there's no sound file to load. */
export function chime(kind: keyof typeof NOTES) {
  try {
    audio ??= new AudioContext();
    void audio.resume();
    const gap = kind === "gentle" ? 0.35 : 0.18;
    NOTES[kind].forEach((frequency, i) => {
      const start = audio!.currentTime + i * gap;
      const tone = audio!.createOscillator();
      const volume = audio!.createGain();
      tone.frequency.value = frequency;
      volume.gain.setValueAtTime(0, start);
      volume.gain.linearRampToValueAtTime(0.15, start + 0.02);
      volume.gain.exponentialRampToValueAtTime(0.001, start + (kind === "gentle" ? 0.9 : 0.5));
      tone.connect(volume).connect(audio!.destination);
      tone.start(start);
      tone.stop(start + 1);
    });
  } catch {
    // No sound is fine: what's on screen still shows
  }
}
