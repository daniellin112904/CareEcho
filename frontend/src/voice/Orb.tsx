import { useEffect, useRef, type ButtonHTMLAttributes } from "react";
import "./orb.css";

export type OrbMode = "idle" | "connecting" | "listening" | "speaking";

type OrbProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  mode?: OrbMode;
  /** Voice level from 0 to 1, read every frame while listening or speaking. */
  getLevel?: () => number;
};

const INK = "#0b0b0b";
// Pivots in the 160x160 drawing: the bottom of the flame, and the middle of the eyes
const BASE = { x: 80, y: 126 };
const EYES = { x: 80, y: 88 };

const about = (p: { x: number; y: number }, inner: string) => `translate(${p.x} ${p.y}) ${inner} translate(${-p.x} ${-p.y})`;

/** Vela's face on screen: Ember, the flame from the logo, sitting in its V. Tapping it makes it hop. */
export default function Orb({ mode = "idle", getLevel, className, onPointerDown, ...button }: OrbProps) {
  const bodyRef = useRef<SVGGElement>(null);
  const eyesRef = useRef<SVGGElement>(null);
  const smileRef = useRef<SVGPathElement>(null);
  const mouthRef = useRef<SVGEllipseElement>(null);
  const hop = useRef(0);
  const latest = useRef({ mode, getLevel });

  useEffect(() => {
    latest.current = { mode, getLevel };
  });

  // One animation loop for Ember's lifetime. It reads the latest mode from a ref and
  // eases toward it, so switching states never makes the motion jump.
  useEffect(() => {
    const motion = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0.3 : 1;
    const phase = Math.random() * 10;
    let level = 0;
    let talk = 0;
    let listen = 0;
    let wake = 0;
    let look = 0;
    let blinkAt = performance.now() + 1500;
    let blinkStart = -Infinity;
    let last = performance.now();

    let frame = requestAnimationFrame(function tick(now) {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = now / 1000 + phase;
      const { mode, getLevel } = latest.current;

      // A recorded message has no live level, so fake a speaking rhythm for it
      const heard =
        mode !== "listening" && mode !== "speaking"
          ? 0
          : getLevel
            ? Math.min(1, getLevel() * 2)
            : mode === "speaking"
              ? Math.max(0, Math.min(1, 0.4 + 0.35 * Math.sin(t * 13) + 0.3 * Math.sin(t * 5.3) * Math.sin(t * 2.1)))
              : 0;
      level += (heard - level) * 0.2;
      talk += ((mode === "speaking" ? 1 : 0) - talk) * 0.12;
      listen += ((mode === "listening" ? 1 : 0) - listen) * 0.08;
      wake += ((mode === "connecting" ? 1 : 0) - wake) * 0.1;
      hop.current = Math.max(0, hop.current - dt * 1.6);
      const arc = Math.sin(Math.PI * hop.current) * motion;

      // Breathes, bounces while talking, stretches with the voice, and huddles small while waking up
      const breathe = Math.sin(t * 2.2);
      const y = (2 * breathe - 6 * talk * level * Math.abs(Math.sin(t * 7))) * motion - 22 * arc;
      const sy = 1 + (0.025 * breathe + 0.07 * level * (talk + listen)) * motion + 0.08 * arc - 0.12 * wake;
      const sx = 1 - (sy - 1) * 0.8;
      // Flickers like a flame, leans in to listen, and shivers while waking up
      const sway =
        (3 * Math.sin(t * 2.7) + Math.sin(t * 6.1) + listen * (7 + 2 * Math.sin(t * 3)) + 4 * wake * Math.sin(t * 11)) * motion;
      bodyRef.current?.setAttribute(
        "transform",
        `translate(0 ${y.toFixed(2)}) ${about(BASE, `rotate(${sway.toFixed(2)}) scale(${sx.toFixed(4)} ${sy.toFixed(4)})`)}`,
      );

      // Blinks every few seconds, sometimes twice; glances around when idle and toward you when listening
      if (now > blinkAt) {
        blinkStart = now;
        blinkAt = now + (Math.random() < 0.25 ? 260 : 2200 + Math.random() * 3200);
      }
      const open = now - blinkStart < 130 ? 0.1 : 1 - 0.6 * wake;
      const glance =
        mode === "listening" ? 3 : mode === "idle" && Math.sin(t * 0.23) > 0.35 ? 3 * Math.sign(Math.sin(t * 0.6)) : 0;
      look += (glance * motion - look) * 0.08;
      const wide = 1 + 0.12 * listen + 0.12 * arc;
      eyesRef.current?.setAttribute(
        "transform",
        `translate(${look.toFixed(2)} ${(-listen).toFixed(2)}) ${about(EYES, `scale(${wide.toFixed(3)} ${(wide * open).toFixed(3)})`)}`,
      );

      mouthRef.current?.setAttribute("ry", (talk * (1.5 + 6 * level) + 4 * arc).toFixed(2));
      smileRef.current?.setAttribute("opacity", (1 - Math.min(1, talk + 3 * arc)).toFixed(2));

      frame = requestAnimationFrame(tick);
    });

    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <button
      type="button"
      className={className ? `orb ${className}` : "orb"}
      data-mode={mode}
      onPointerDown={(event) => {
        hop.current = 1;
        onPointerDown?.(event);
      }}
      {...button}
    >
      <svg viewBox="0 0 160 160" aria-hidden="true">
        <g ref={bodyRef}>
          <path d="M80 30 C96 52 108 72 108 96 C108 114 95 126 80 126 C65 126 52 114 52 96 C52 72 64 52 80 30 Z" fill="#ec8a4f" />
          <ellipse cx="80" cy="111" rx="17" ry="11" fill="#ffd9a8" />
          <ellipse cx="62" cy="98" rx="6" ry="3.5" fill="#d9532a" opacity="0.45" />
          <ellipse cx="98" cy="98" rx="6" ry="3.5" fill="#d9532a" opacity="0.45" />
          <g ref={eyesRef}>
            <ellipse cx="70" cy="88" rx="5" ry="7" fill={INK} />
            <ellipse cx="90" cy="88" rx="5" ry="7" fill={INK} />
            <circle cx="71.7" cy="85.2" r="1.9" fill="#fff" />
            <circle cx="91.7" cy="85.2" r="1.9" fill="#fff" />
          </g>
          <path ref={smileRef} d="M75 99 Q80 103.5 85 99" stroke={INK} strokeWidth="2.6" fill="none" strokeLinecap="round" />
          <ellipse ref={mouthRef} cx="80" cy="101" rx="4.5" ry="0" fill="#5a1d0c" />
        </g>
        <path d="M48 110 L80 146 L112 110" fill="none" stroke={INK} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}
