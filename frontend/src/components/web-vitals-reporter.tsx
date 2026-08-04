"use client";

import { useReportWebVitals } from "next/web-vitals";

export function WebVitalsReporter() {
  useReportWebVitals((metric) => {
    if (process.env.NODE_ENV === "development") {
      console.log(`${metric.name}:`, {
        value: metric.value,
        id: metric.id,
        rating: metric.rating,
      });
    } else {
      // In production, this is where an analytics endpoint would be called.
      // Example: navigator.sendBeacon('/api/analytics', JSON.stringify(metric))
      // For now, metrics are collected but not sent anywhere.
    }
  });

  return null;
}
