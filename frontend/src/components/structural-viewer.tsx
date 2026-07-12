"use client";

import { useState } from "react";
import { useSession } from "@/lib/auth-client";

interface StructuralViewerProps {
  projectId: string;
  layoutId: string;
}

interface StructuralCheck {
  name: string;
  ok: boolean;
}

interface StructuralArtifact {
  name: string;
  content_type: string;
  encoding: string;
  content: string;
}

interface StructuralResponse {
  ok: boolean;
  grid: {
    x_spacings_m: number[];
    y_spacings_m: number[];
    confident: boolean;
    notes: string[];
  };
  checks: StructuralCheck[];
  data: {
    quantities?: {
      concrete_m3?: Record<string, number>;
      steel_kg?: Record<string, number>;
      grade?: string;
    };
    assumptions?: string[];
    lateral?: Record<string, unknown>;
  };
  artifacts: StructuralArtifact[];
  disclaimer: string;
}

function downloadArtifact(artifact: StructuralArtifact) {
  const bytes = Uint8Array.from(atob(artifact.content), (c) => c.charCodeAt(0));
  const blob = new Blob([bytes], { type: artifact.content_type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = artifact.name;
  a.click();
  URL.revokeObjectURL(url);
}

export function StructuralViewer({ projectId, layoutId }: StructuralViewerProps) {
  const { data: session } = useSession();
  const [result, setResult] = useState<StructuralResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sbc, setSbc] = useState(200);

  async function runDesign() {
    if (!session) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/structural`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ layout_id: layoutId, sbc_kpa: sbc, include_pdf: true }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === "string"
            ? detail.detail
            : (detail?.detail?.message ?? `Request failed (${res.status})`)
        );
      }
      setResult((await res.json()) as StructuralResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Structural design failed");
    } finally {
      setLoading(false);
    }
  }

  const failedChecks = result?.checks.filter((c) => !c.ok) ?? [];
  const pdf = result?.artifacts.find((a) => a.content_type === "application/pdf");
  const q = result?.data.quantities;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground">Safe bearing capacity (kPa)</span>
          <input
            type="number"
            min={50}
            max={600}
            value={sbc}
            onChange={(e) => setSbc(Number(e.target.value))}
            className="w-36 rounded-md border bg-background px-3 py-2"
          />
        </label>
        <button
          type="button"
          onClick={runDesign}
          disabled={loading}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {loading ? "Designing…" : "Run structural design"}
        </button>
        {pdf && (
          <button
            type="button"
            onClick={() => downloadArtifact(pdf)}
            className="rounded-md border px-4 py-2 text-sm"
          >
            Download PDF report
          </button>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {result && (
        <div className="flex flex-col gap-4">
          <div className="rounded-md border p-3 text-sm">
            <p className="font-medium">
              {result.ok ? "✓ All code checks pass" : `✗ ${failedChecks.length} check(s) failed`}
              <span className="ml-2 text-muted-foreground">
                (IS 456:2000 LSM · grid {result.grid.x_spacings_m.join(" / ")} m ×{" "}
                {result.grid.y_spacings_m.join(" / ")} m)
              </span>
            </p>
            {!result.grid.confident && (
              <p className="mt-1 text-amber-600">
                ⚠ Structural grid needs review: {result.grid.notes.join("; ")}
              </p>
            )}
          </div>

          {q && (
            <div className="rounded-md border p-3 text-sm">
              <p className="mb-2 font-medium">Quantities ({q.grade})</p>
              <table className="w-full text-left">
                <thead>
                  <tr className="text-muted-foreground">
                    <th className="py-1">Element</th>
                    <th className="py-1">Concrete (m³)</th>
                    <th className="py-1">Steel (kg)</th>
                  </tr>
                </thead>
                <tbody>
                  {["slabs", "beams", "columns", "footings", "total"].map((k) => (
                    <tr key={k} className={k === "total" ? "font-medium" : ""}>
                      <td className="py-1 capitalize">{k}</td>
                      <td className="py-1">{q.concrete_m3?.[k] ?? "—"}</td>
                      <td className="py-1">{q.steel_kg?.[k] ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {failedChecks.length > 0 && (
            <div className="rounded-md border border-destructive/40 p-3 text-sm">
              <p className="mb-1 font-medium">Failed checks</p>
              <ul className="list-disc pl-5">
                {failedChecks.map((c) => (
                  <li key={c.name}>{c.name}</li>
                ))}
              </ul>
            </div>
          )}

          {result.data.assumptions && (
            <details className="rounded-md border p-3 text-sm">
              <summary className="cursor-pointer font-medium">
                Assumptions ({result.data.assumptions.length})
              </summary>
              <ul className="mt-2 list-disc pl-5 text-muted-foreground">
                {result.data.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </details>
          )}

          <p className="text-xs text-muted-foreground">{result.disclaimer}</p>
        </div>
      )}

      {!result && !loading && !error && (
        <p className="text-sm text-muted-foreground">
          Runs an IS-code structural design (slabs, beams, columns, footings) for this layout&apos;s
          column grid via StructAgent — clause-referenced checks, quantities and a PDF report.
        </p>
      )}
    </div>
  );
}
