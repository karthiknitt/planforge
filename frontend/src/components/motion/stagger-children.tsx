"use client";

import { m, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

interface StaggerChildrenProps {
  children: ReactNode;
  staggerDelay?: number;
  className?: string;
}

export function StaggerChildren({
  children,
  staggerDelay = 0.08,
  className,
}: StaggerChildrenProps) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <m.div
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-50px" }}
      variants={{
        hidden: {},
        visible: {
          transition: {
            staggerChildren: shouldReduceMotion ? 0 : staggerDelay,
          },
        },
      }}
      className={className}
    >
      {children}
    </m.div>
  );
}

export function StaggerItem({ children, className }: { children: ReactNode; className?: string }) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <m.div
      // opacity stays 1 in the "hidden" variant — only the y offset animates,
      // so content never renders invisible if JS is delayed or disabled
      variants={{
        hidden: { opacity: 1, y: shouldReduceMotion ? 0 : 20 },
        visible: {
          opacity: 1,
          y: 0,
          transition: {
            duration: 0.5,
            ease: [0.16, 1, 0.3, 1],
          },
        },
      }}
      className={className}
    >
      {children}
    </m.div>
  );
}
