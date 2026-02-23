"use client";

import { type HTMLMotionProps, motion, useReducedMotion } from "framer-motion";
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
    opacity: 0,
    x: from === "left" ? -distance : from === "right" ? distance : 0,
    y: from === "bottom" ? distance : 0,
  };

  return (
    <motion.div
      initial={shouldReduceMotion ? { opacity: 1 } : initial}
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
    </motion.div>
  );
}
