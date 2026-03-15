"use client";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100dvh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#070D1E",
          color: "#E2E8F8",
          fontFamily: "system-ui, sans-serif",
          gap: "1rem",
        }}
      >
        <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>Something went wrong</h2>
        <button
          type="button"
          onClick={() => reset()}
          style={{
            padding: "0.5rem 1.25rem",
            borderRadius: "0.5rem",
            border: "none",
            background: "#f97316",
            color: "#fff",
            fontWeight: 600,
            cursor: "pointer",
            fontSize: "0.875rem",
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
