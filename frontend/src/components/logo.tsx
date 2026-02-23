import type { SVGProps } from "react";

/**
 * PlanForgeIcon — custom SVG logo mark.
 * A stylised 2×2 floor plan grid with an accent-filled quadrant.
 * Uses currentColor so it adapts to any parent text/fill color.
 */
export function PlanForgeIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
      {...props}
    >
      {/* Outer walls */}
      <rect x="1.5" y="1.5" width="13" height="13" rx="1" stroke="currentColor" strokeWidth="1.5" />
      {/* Internal partition — vertical */}
      <line x1="8" y1="1.5" x2="8" y2="14.5" stroke="currentColor" strokeWidth="1" />
      {/* Internal partition — horizontal */}
      <line x1="1.5" y1="8" x2="14.5" y2="8" stroke="currentColor" strokeWidth="1" />
      {/* Accent quadrant fill (top-right = main living room) */}
      <rect x="8.75" y="2" width="5.75" height="5.5" fill="currentColor" opacity="0.4" rx="0.5" />
      {/* Door arc hint (bottom-left room) */}
      <path
        d="M 2.25 13.75 Q 4.75 13.75 4.75 11.25"
        stroke="currentColor"
        strokeWidth="0.8"
        opacity="0.55"
      />
    </svg>
  );
}
