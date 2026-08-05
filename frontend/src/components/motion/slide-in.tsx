"use client";

import { type HTMLMotionProps, m, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

interface SlideInProps extends Omit<HTMLMotionProps<"div">, "children"> {
  children: ReactNode;
  delay?: number;
  duration?: number;
  from?: "left" | "right" | "bottom";
  distance?: number;
  className?: string;
}

export function SlideIn({
  children,
  delay = 0,
  duration = 0.7,
  from = "left",
  distance = 60,
  className,
  ...props
}: SlideInProps) {
  const shouldReduceMotion = useReducedMotion();

  const initial = {
    // opacity stays 1 in the SSR'd/no-JS state — only x/y offset animates,
    // so content never renders invisible if JS is delayed or disabled
    opacity: 1,
    x: shouldReduceMotion ? 0 : from === "left" ? -distance : from === "right" ? distance : 0,
    y: shouldReduceMotion ? 0 : from === "bottom" ? distance : 0,
  };

  return (
    <m.div
      initial={initial}
      whileInView={{ opacity: 1, x: 0, y: 0 }}
      viewport={{ once: true, margin: "-50px" }}
      transition={{
        duration: shouldReduceMotion ? 0 : duration,
        delay: shouldReduceMotion ? 0 : delay,
        ease: [0.16, 1, 0.3, 1],
      }}
      className={className}
      {...props}
    >
      {children}
    </m.div>
  );
}
