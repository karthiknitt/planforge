"use client";

import { type HTMLMotionProps, m, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

interface FadeInProps extends Omit<HTMLMotionProps<"div">, "children"> {
  children: ReactNode;
  delay?: number;
  duration?: number;
  direction?: "up" | "down" | "none";
  className?: string;
}

export function FadeIn({
  children,
  delay = 0,
  duration = 0.6,
  direction = "up",
  className,
  ...props
}: FadeInProps) {
  const shouldReduceMotion = useReducedMotion();

  const y = direction === "up" ? 24 : direction === "down" ? -24 : 0;

  return (
    <m.div
      // opacity stays 1 in the SSR'd/no-JS state — only the y offset animates,
      // so content never renders invisible if JS is delayed or disabled
      initial={{ opacity: 1, y: shouldReduceMotion ? 0 : y }}
      whileInView={{ opacity: 1, y: 0 }}
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
