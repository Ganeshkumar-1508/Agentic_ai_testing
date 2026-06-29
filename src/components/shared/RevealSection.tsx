"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface RevealSectionProps {
  children: ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "section";
}

export function RevealSection({ children, className, delay = 0, as = "div" }: RevealSectionProps) {
  const Comp = motion[as as "div" | "section"];

  return (
    <Comp
      initial={{ opacity: 0, y: 32, filter: "blur(4px)" }}
      whileInView="visible"
      viewport={{ once: true, margin: "-60px" }}
      variants={{
        visible: {
          opacity: 1,
          y: 0,
          filter: "blur(0px)",
          transition: {
            delay,
            duration: 0.6,
            ease: [0.16, 1, 0.3, 1] as const,
          },
        },
      }}
      className={cn(className)}
    >
      {children}
    </Comp>
  );
}
