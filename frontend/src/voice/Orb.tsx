import { useEffect, useRef, type ButtonHTMLAttributes } from "react";
import "./orb.css";

export type OrbMode = "idle" | "connecting" | "listening" | "speaking";
export type OrbPalette = "calm" | "warm" | "teal";

const PALETTES: Record<OrbPalette, { base: string; blobs: string[] }> = {
  calm: { base: "#8c9cf0", blobs: ["#f4f8ff", "#b9a6f5", "#7fc0f7", "#ffb48a", "#3d3f9f", "#c9e4ff"] },
  warm: { base: "#ec8a4f", blobs: ["#fff3e3", "#f7bb76", "#e2683a", "#ffd9a8", "#8f2f14", "#ffc89a"] },
  teal: { base: "#3fb08c", blobs: ["#f2fffa", "#9fe1cb", "#1d9e75", "#c9f2e4", "#04342c", "#7fd6c0"] },
};

// Each blob circles on its own loop. r = orbit radius and sz = diameter, both as a
// fraction of the orb; s = angular speed (negative spins the other way); ph = phase.
const BLOBS = [
  { r: 0.22, s: 0.9, ph: 0, sz: 0.95 },
  { r: 0.28, s: -0.7, ph: 1.7, sz: 1.05 },
  { r: 0.2, s: 1.15, ph: 3.1, sz: 0.85 },
  { r: 0.3, s: 0.55, ph: 4.4, sz: 0.9 },
  { r: 0.26, s: -1.0, ph: 5.5, sz: 1.1 },
  { r: 0.16, s: 0.8, ph: 2.3, sz: 0.7 },
];

const MOTION: Record<OrbMode, { speed: number; ring: number }> = {
  idle: { speed: 0.35, ring: 0 },
  connecting: { speed: 1.6, ring: 0 },
  listening: { speed: 0.7, ring: 1 },
  speaking: { speed: 1.25, ring: 0 },
};

type OrbProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  mode?: OrbMode;
  palette?: OrbPalette;
  /** Voice level from 0 to 1, read every frame while listening or speaking. */
  getLevel?: () => number;
};

export default function Orb({ mode = "idle", palette = "calm", getLevel, className, ...button }: OrbProps) {
  const bodyRef = useRef<HTMLSpanElement>(null);
  const ringRef = useRef<HTMLSpanElement>(null);
  const blobRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const latest = useRef({ mode, getLevel });

  useEffect(() => {
    latest.current = { mode, getLevel };
  });

  // One animation loop for the orb's lifetime. It reads the latest mode from a ref and
  // eases toward it, so switching states never makes the motion jump.
  useEffect(() => {
    const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let t = Math.random() * 10;
    let speed = MOTION.idle.speed;
    let scale = 1;
    let level = 0;
    let ring = 0;
    let last = performance.now();

    let frame = requestAnimationFrame(function tick(now) {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const { mode, getLevel } = latest.current;
      const heard = mode === "listening" || mode === "speaking" ? Math.min(1, (getLevel?.() ?? 0) * 2) : 0;

      level += (heard - level) * 0.2;
      speed += (MOTION[mode].speed - speed) * 0.04;
      ring += (MOTION[mode].ring - ring) * 0.08;
      t += dt * speed * (reduceMotion ? 0.3 : 1);

      BLOBS.forEach((b, i) => {
        const el = blobRefs.current[i];
        if (!el) return;
        const a = t * b.s + b.ph;
        // translate() percentages are relative to the blob, so divide by its size
        const x = ((Math.cos(a) * b.r) / b.sz) * 100;
        const y = ((Math.sin(a * 1.3 + b.ph) * b.r) / b.sz) * 100;
        const grow = 1 + 0.18 * Math.sin(a * 0.8 + b.ph);
        el.style.transform = `translate(${x.toFixed(2)}%, ${y.toFixed(2)}%) scale(${grow.toFixed(3)})`;
      });

      const target =
        mode === "speaking"
          ? 1.02 + 0.09 * level
          : mode === "listening"
            ? 1.015 + 0.05 * level
            : mode === "connecting"
              ? 0.96
              : 1 + 0.022 * Math.sin(now / 1100);
      scale += (target - scale) * 0.15;

      if (bodyRef.current) bodyRef.current.style.transform = `scale(${scale.toFixed(4)})`;
      if (ringRef.current) {
        ringRef.current.style.opacity = ring.toFixed(3);
        ringRef.current.style.transform = `scale(${(1 + 0.05 * level + 0.02 * Math.sin(now / 600)).toFixed(4)})`;
      }
      frame = requestAnimationFrame(tick);
    });

    return () => cancelAnimationFrame(frame);
  }, []);

  const colors = PALETTES[palette];

  return (
    <button type="button" className={className ? `orb ${className}` : "orb"} data-mode={mode} {...button}>
      <span ref={ringRef} className="orb-ring" />
      <span ref={bodyRef} className="orb-body" style={{ background: colors.base }}>
        {BLOBS.map((b, i) => {
          const color = colors.blobs[i % colors.blobs.length];
          return (
            <span
              key={i}
              ref={(el) => {
                blobRefs.current[i] = el;
              }}
              className="orb-blob"
              style={{
                width: `${b.sz * 100}%`,
                height: `${b.sz * 100}%`,
                left: `${((1 - b.sz) / 2) * 100}%`,
                top: `${((1 - b.sz) / 2) * 100}%`,
                background: `radial-gradient(circle, ${color} 0%, ${color}cc 22%, ${color}00 62%)`,
              }}
            />
          );
        })}
        <span className="orb-shade" />
      </span>
    </button>
  );
}
