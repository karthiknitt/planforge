"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useSession } from "@/lib/auth-client";
import { changelogCount } from "@/lib/structural-status";
import { showErrorToast, showToast } from "@/lib/toast";

export interface StructuralDesignInfo {
  id: string;
  status: string;
  iterations_used: number;
  created_at: string;
  changelog: string[] | null;
}

export interface StructuralStatusResponse {
  layout_id: string;
  status: string;
  geometry_hash: string;
  revision_id: string | null;
  design: StructuralDesignInfo | null;
}

interface StructuralViewerProps {
  projectId: string;
  layoutId: string;
  // Lifecycle status from GET /structural/status, owned by the parent layout
  // viewer (it also drives the header badge, so a single fetch feeds both).
  status: StructuralStatusResponse | null;
  approving: boolean;
  onApprove: () => Promise<void> | void;
  onDesignComplete: () => Promise<void> | void;
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
  revision_id: string;
  design_id: string;
  status: string;
  iterations_used: number;
  changelog: string[];
  layout_adjusted: boolean;
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

interface GateError {
  code: "not_approved" | "grid_needs_review" | null;
  message: string;
  notes?: string[];
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

export function StructuralViewer({
  projectId,
  layoutId,
  status,
  approving,
  onApprove,
  onDesignComplete,
}: StructuralViewerProps) {
  const { data: session } = useSession();
  const [result, setResult] = useState<StructuralResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [gateError, setGateError] = useState<GateError | null>(null);
  const [sbc, setSbc] = useState(200);

  // Reset any in-session run result when the viewed layout changes — a
  // stale result from a different layout must not linger in this tab.
  // biome-ignore lint/correctness/useExhaustiveDependencies: layoutId is an intentional reset trigger, not read in the body
  useEffect(() => {
    setResult(null);
    setGateError(null);
  }, [layoutId]);

  async function runDesign(allowUnconfidentGrid = false) {
    if (!session) return;
    setLoading(true);
    setGateError(null);
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/structural`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layout_id: layoutId,
          sbc_kpa: sbc,
          include_pdf: true,
          allow_unconfident_grid: allowUnconfidentGrid,
        }),
      });
      if (res.status === 409) {
        const detail = await res.json().catch(() => null);
        const code = detail?.detail?.code as GateError["code"] | undefined;
        if (code === "not_approved") {
          setGateError({
            code: "not_approved",
            message:
              detail?.detail?.help ??
              "Approve the architectural plan before running structural design.",
          });
        } else if (code === "grid_needs_review") {
          setGateError({
            code: "grid_needs_review",
            message: detail?.detail?.help ?? "The extracted column grid is irregular.",
            notes: detail?.detail?.notes ?? [],
          });
        } else {
          setGateError({ code: null, message: "Request rejected (409)." });
        }
        return;
      }
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === "string"
            ? detail.detail
            : (detail?.detail?.message ?? `Request failed (${res.status})`)
        );
      }
      setResult((await res.json()) as StructuralResponse);
      showToast(
        "success",
        "Structural design complete — the drawing set is ready to generate & download from the Export menu"
      );
      await onDesignComplete();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Structural design failed";
      setGateError({ code: null, message });
      showErrorToast(message);
    } finally {
      setLoading(false);
    }
  }

  async function handleApproveThenRetry() {
    await onApprove();
    setGateError(null);
    await runDesign();
  }

  const failedChecks = result?.checks.filter((c) => !c.ok) ?? [];
  const pdf = result?.artifacts.find((a) => a.content_type === "application/pdf");
  const q = result?.data.quantities;

  // Persisted design from a previous session (no in-session run result yet)
  // — surface its changelog summary without re-running, per spec.
  const persistedDesign = !result ? status?.design : null;

  // "draft" means no approved revision exists yet for this geometry (see
  // structural_store.layout_status). Surface this the moment the tab opens
  // rather than waiting for the user to click "Run" and hit the same 409
  // the backend would return anyway.
  const notApprovedYet =
    gateError?.code === "not_approved" ||
    (!gateError && !result && !persistedDesign && status?.status === "draft");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1 text-sm">
          <Label htmlFor="sbc" className="text-muted-foreground">
            Safe bearing capacity (kPa)
          </Label>
          <Input
            id="sbc"
            type="number"
            min={50}
            max={600}
            value={sbc}
            onChange={(e) => setSbc(Number(e.target.value))}
            className="w-36"
          />
        </div>
        <Button
          onClick={() => runDesign()}
          disabled={loading || notApprovedYet}
          title={notApprovedYet ? "Approve the architectural plan first" : undefined}
        >
          {loading ? "Designing… (can take up to a minute)" : "Run structural design"}
        </Button>
        {pdf && (
          <Button variant="outline" onClick={() => downloadArtifact(pdf)}>
            Download PDF report
          </Button>
        )}
      </div>

      {notApprovedYet && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          <p className="font-medium text-amber-700 dark:text-amber-400">
            Architectural plan not approved yet
          </p>
          <p className="mt-1 text-muted-foreground">
            {gateError?.message ??
              "Structural design isn't enabled until the architectural plan is approved. Approve it below to continue."}
          </p>
          <Button size="sm" className="mt-2" onClick={handleApproveThenRetry} disabled={approving}>
            {approving ? "Approving…" : "Approve plan and run design"}
          </Button>
        </div>
      )}

      {gateError?.code === "grid_needs_review" && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          <p className="font-medium text-amber-700 dark:text-amber-400">
            Structural grid needs review
          </p>
          <p className="mt-1 text-muted-foreground">{gateError.message}</p>
          {gateError.notes && gateError.notes.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-muted-foreground">
              {gateError.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
          <Button
            size="sm"
            variant="outline"
            className="mt-2"
            onClick={() => runDesign(true)}
            disabled={loading}
          >
            Proceed anyway
          </Button>
        </div>
      )}

      {gateError?.code === null && gateError.message && (
        <p className="text-sm text-destructive">{gateError.message}</p>
      )}

      {loading && !result && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

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
            <p className="mt-1 text-muted-foreground">
              {result.iterations_used} iteration{result.iterations_used === 1 ? "" : "s"} used
              {result.layout_adjusted && " · layout geometry was adjusted to satisfy checks"}
            </p>
            {!result.grid.confident && (
              <p className="mt-1 text-amber-600">
                ⚠ Structural grid needs review: {result.grid.notes.join("; ")}
              </p>
            )}
          </div>

          {result.changelog.length > 0 && (
            <div className="rounded-md border p-3 text-sm">
              <p className="mb-1 font-medium">Changes from approved plan</p>
              <ul className="list-disc pl-5 text-muted-foreground">
                {result.changelog.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          )}

          {q && (
            <div className="rounded-md border p-3 text-sm">
              <p className="mb-2 font-medium">Quantities ({q.grade})</p>
              <Table>
                <TableHeader>
                  <TableRow className="text-muted-foreground">
                    <TableHead>Element</TableHead>
                    <TableHead>Concrete (m³)</TableHead>
                    <TableHead>Steel (kg)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {["slabs", "beams", "columns", "footings", "total"].map((k) => (
                    <TableRow key={k} className={k === "total" ? "font-medium" : ""}>
                      <TableCell className="capitalize">{k}</TableCell>
                      <TableCell>{q.concrete_m3?.[k] ?? "—"}</TableCell>
                      <TableCell>{q.steel_kg?.[k] ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
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

      {!result && persistedDesign && (
        <div className="rounded-md border p-3 text-sm">
          <p className="font-medium">
            {persistedDesign.status === "designed" ? "✓ Design on file" : "⚠ Design on file"}
            <span className="ml-2 text-muted-foreground">
              {persistedDesign.iterations_used} iteration
              {persistedDesign.iterations_used === 1 ? "" : "s"} ·{" "}
              {new Date(persistedDesign.created_at).toLocaleString("en-IN")}
            </span>
          </p>
          {changelogCount(persistedDesign.changelog) > 0 && (
            <div className="mt-2">
              <p className="mb-1 font-medium">Changes from approved plan</p>
              <ul className="list-disc pl-5 text-muted-foreground">
                {(persistedDesign.changelog ?? []).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            Showing the last saved design for this approved revision. Run again to refresh artifacts
            (PDF, quantities).
          </p>
        </div>
      )}

      {!result && !loading && !gateError && !persistedDesign && !notApprovedYet && (
        <p className="text-sm text-muted-foreground">
          Runs an IS-code structural design (slabs, beams, columns, footings) for this layout&apos;s
          column grid via StructAgent — clause-referenced checks, quantities and a PDF report.
        </p>
      )}
    </div>
  );
}
