"use client";

import { type HTMLMotionProps, m, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

interface ScaleInProps extends Omit<HTMLMotionProps<"div">, "children"> {
  children: ReactNode;
  delay?: number;
  duration?: number;
  className?: string;
}

export function ScaleIn({
  children,
  delay = 0,
  duration = 0.6,
  className,
  ...props
}: ScaleInProps) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <m.div
      // opacity stays 1 in the SSR'd/no-JS state — only the scale animates,
      // so content never renders invisible if JS is delayed or disabled
      initial={{ opacity: 1, scale: shouldReduceMotion ? 1 : 0.94 }}
      whileInView={{ opacity: 1, scale: 1 }}
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
