"use client";
import { useEffect, useState } from "react";

export function AnimatedNumber({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const duration = 250;
    const start = performance.now();
    const from = display;

    function tick(now: number) {
      const progress = Math.min((now - start) / duration, 1);
      setDisplay(from + (value - from) * progress);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return <span>{display.toFixed(decimals)}</span>;
}