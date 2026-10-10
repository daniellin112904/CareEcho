import { useEffect, useId, useRef, type ButtonHTMLAttributes } from "react";
import "./orb.css";

export type OrbMode = "idle" | "connecting" | "listening" | "speaking";
export type OrbPalette = "calm" | "warm" | "teal";

// Wax colors: body, shaded side, and the light rim and drip on top
const PALETTES: Record<OrbPalette, { wax: string; shade: string; rim: string }> = {
  calm: { wax: "#6b74e0", shade: "#4c55c7", rim: "#a9b3f5" },
  warm: { wax: "#f0a56b", shade: "#e2683a", rim: "#ffd9a8" },
  teal: { wax: "#3fb08c", shade: "#1d9e75", rim: "#9fe1cb" },
};

// Flame size in each mode, before the voice level is added
const FLAME: Record<OrbMode, number> = { idle: 1, connecting: 0.6, listening: 1.08, speaking: 1.1 };

const INK = "#1c1f4a";

type OrbProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  mode?: OrbMode;
  palette?: OrbPalette;
  /** Voice level from 0 to 1, read every frame while listening or speaking. */
  getLevel?: () => number;
};

/** Vela's face on screen: a little candle whose flame and mouth follow the voice. */
export default function Orb({ mode = "idle", palette = "calm", getLevel, className, ...button }: OrbProps) {
  // useId has colons, which break url(#...)
  const clipId = `wax${useId().replace(/\W/g, "")}`;
  const bodyRef = useRef<SVGGElement>(null);
  const flameRef = useRef<SVGGElement>(null);
  const glowRef = useRef<SVGCircleElement>(null);
  const mouthRef = useRef<SVGEllipseElement>(null);
  const smileRef = useRef<SVGPathElement>(null);
  const latest = useRef({ mode, getLevel });

  useEffect(() => {
    latest.current = { mode, getLevel };
  });

  // One animation loop for the candle's lifetime. It reads the latest mode from a ref and
  // eases toward it, so switching states never makes the motion jump.
  useEffect(() => {
    const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const wiggle = reduceMotion ? 0 : 1;
    let flame = FLAME.idle;
    let level = 0;
    let talk = 0;
    let glow = 0;

    let frame = requestAnimationFrame(function tick(now) {
      const { mode, getLevel } = latest.current;
      const heard = mode === "listening" || mode === "speaking" ? Math.min(1, (getLevel?.() ?? 0) * 2) : 0;
      // While connecting the small flame sputters, like a candle being lit
      const sputter = mode === "connecting" ? 0.12 * Math.sin(now / 180) * wiggle : 0;

      level += (heard - level) * 0.2;
      flame += (FLAME[mode] + sputter - flame) * 0.1;
      talk += ((mode === "speaking" ? 1 : 0) - talk) * 0.15;
      glow += ((mode === "listening" ? 1 : 0) - glow) * 0.08;

      const sway = 3 * Math.sin(now / 650) * wiggle;
      const grow = flame * (1 + 0.35 * level) * (1 + 0.04 * Math.sin(now / 400) * wiggle);
      if (flameRef.current) flameRef.current.style.transform = `rotate(${sway.toFixed(2)}deg) scale(${grow.toFixed(4)})`;
      if (glowRef.current) {
        glowRef.current.style.opacity = (glow * (0.45 + 0.4 * level)).toFixed(3);
        glowRef.current.style.transform = `scale(${(1 + 0.3 * level).toFixed(4)})`;
      }
      if (bodyRef.current) bodyRef.current.style.transform = `translateY(${(1.2 * Math.sin(now / 1100) * wiggle).toFixed(3)}px)`;
      mouthRef.current?.setAttribute("ry", (talk * (1.5 + 5 * level)).toFixed(2));
      smileRef.current?.setAttribute("opacity", (1 - talk).toFixed(3));

      frame = requestAnimationFrame(tick);
    });

    return () => cancelAnimationFrame(frame);
  }, []);

  const { wax, shade, rim } = PALETTES[palette];

  return (
    <button type="button" className={className ? `orb ${className}` : "orb"} data-mode={mode} {...button}>
      <svg viewBox="-10 0 140 140" aria-hidden="true">
        <defs>
          <clipPath id={clipId}>
            <rect x="30" y="54" width="60" height="68" rx="18" />
          </clipPath>
        </defs>
        <circle ref={glowRef} className="orb-glow" cx="60" cy="36" r="26" fill="#ffd9a8" opacity="0" />
        <g ref={bodyRef}>
          <g ref={flameRef} className="orb-flame">
            <path d="M60 12 C71 27 74 38 67 47 C64 51 56 51 53 47 C46 38 50 26 60 12 Z" fill="#ec8a4f" />
            <path d="M60 27 C65 35 66 41 63 45 C61 47.5 59 47.5 57 45 C54 41 56 34 60 27 Z" fill="#ffd9a8" />
          </g>
          <rect x="58.5" y="48" width="3" height="8" rx="1.5" fill={INK} />
          <rect x="22" y="80" width="12" height="20" rx="6" fill={wax} />
          <rect x="86" y="80" width="12" height="20" rx="6" fill={shade} />
          <rect x="40" y="114" width="12" height="14" rx="6" fill={shade} />
          <rect x="68" y="114" width="12" height="14" rx="6" fill={shade} />
          <g clipPath={`url(#${clipId})`}>
            <rect x="30" y="54" width="60" height="68" fill={wax} />
            <rect x="80" y="54" width="10" height="68" fill={shade} />
            <rect x="30" y="54" width="60" height="9" fill={rim} />
            <rect x="38" y="58" width="7" height="16" rx="3.5" fill={rim} />
            <rect x="30" y="114" width="60" height="8" fill={shade} />
          </g>
          <ellipse cx="45" cy="94" rx="5" ry="3" fill="#f0997b" opacity="0.55" />
          <ellipse cx="75" cy="94" rx="5" ry="3" fill="#f0997b" opacity="0.55" />
          <g className="orb-eyes">
            <ellipse cx="50" cy="85" rx="3.2" ry="5" fill={INK} />
            <ellipse cx="70" cy="85" rx="3.2" ry="5" fill={INK} />
          </g>
          <path ref={smileRef} d="M55 96 Q60 100 65 96" stroke={INK} strokeWidth="2.4" fill="none" strokeLinecap="round" />
          <ellipse ref={mouthRef} cx="60" cy="98" rx="4" ry="0" fill={INK} />
        </g>
      </svg>
    </button>
  );
}
