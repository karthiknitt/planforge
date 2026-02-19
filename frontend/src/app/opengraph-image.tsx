import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "PlanForge — G+1 Floor Plan Generator";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OGImage() {
  return new ImageResponse(
    <div
      style={{
        background: "#1e3a5f",
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "sans-serif",
      }}
    >
      {/* Orange accent bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 8,
          background: "#f97316",
        }}
      />

      {/* Logo row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 20,
          marginBottom: 32,
        }}
      >
        <div
          style={{
            width: 64,
            height: 64,
            background: "#f97316",
            borderRadius: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 36,
          }}
        >
          🏗
        </div>
        <span style={{ fontSize: 56, fontWeight: 800, color: "#ffffff" }}>PlanForge</span>
      </div>

      {/* Tagline */}
      <p
        style={{
          fontSize: 30,
          color: "#93c5fd",
          textAlign: "center",
          margin: 0,
          marginBottom: 24,
          maxWidth: 800,
        }}
      >
        G+1 Floor Plan Generator · NBC 2016 Compliant
      </p>

      {/* Badges row */}
      <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
        {["5 Layouts", "PDF & DXF Export", "City-Specific Rules"].map((label) => (
          <div
            key={label}
            style={{
              background: "rgba(249,115,22,0.15)",
              border: "1px solid rgba(249,115,22,0.4)",
              borderRadius: 8,
              padding: "8px 20px",
              color: "#fdba74",
              fontSize: 20,
              fontWeight: 600,
            }}
          >
            {label}
          </div>
        ))}
      </div>

      {/* Bottom bar */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 8,
          background: "#f97316",
        }}
      />
    </div>,
    { ...size }
  );
}
