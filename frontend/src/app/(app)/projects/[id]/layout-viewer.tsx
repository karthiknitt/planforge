"use client";

import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDot,
  Clock,
  Copy,
  Download,
  FileStack,
  History,
  Link2,
  Lock,
  MessageSquare,
  RefreshCw,
  RotateCcw,
  Save,
  X,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { DxfPreviewDialog } from "@/components/dxf-preview-dialog";
import type { Annotation } from "@/components/floor-plan-svg";
import { PdfPreviewDialog } from "@/components/pdf-preview-dialog";
import type { Plan3DHandle, Plan3DView } from "@/components/plan-3d-scene";
import { SectionViewSVG } from "@/components/section-view-svg";
import { ShareWhatsAppButton } from "@/components/share-whatsapp-button";
import { StatusRail } from "@/components/status-rail";
import type { StructuralStatusResponse } from "@/components/structural-viewer";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/lib/auth-client";
import { type CadQuality, cadQualityLabel, cadQualityTone } from "@/lib/cad-quality";
import {
  canRedo,
  canUndo,
  type History as EditHistory,
  initHistory,
  pushHistory,
  redoHistory,
  undoHistory,
} from "@/lib/edit-history";
import type { FloorPlanData, GenerateResponse, LayoutData, RoomData } from "@/lib/layout-types";
import { useLocale } from "@/lib/locale-context";
import { floorKeyFromIndex } from "@/lib/render-tab";
import { buildShareUrl } from "@/lib/share-url";
import type { RenderSourceFallbackReason } from "@/lib/structural-status";
import { type TabId, visibleTabs } from "@/lib/tabs";
import { showErrorToast, showToast } from "@/lib/toast";
import { GenerationPanel } from "./tabs/generation-panel";
import { PlanTab } from "./tabs/plan-tab";
import { R3fTab } from "./tabs/r3f-tab";

const BOQViewer = dynamic(() => import("@/components/boq-viewer").then((m) => m.BOQViewer));
const StructuralViewer = dynamic(() =>
  import("@/components/structural-viewer").then((m) => m.StructuralViewer)
);
const LayoutCompareView = dynamic(() =>
  import("@/components/layout-compare-view").then((m) => m.LayoutCompareView)
);
const RenderTab = dynamic(() => import("./tabs/render-tab").then((m) => m.RenderTab));
const ChatTab = dynamic(() => import("./tabs/chat-tab").then((m) => m.ChatTab));
// ssr:false — R3F/three.js touches WebGL/canvas APIs that don't exist server-side.
const Plan3DScene = dynamic(() => import("@/components/plan-3d-scene").then((m) => m.Plan3DScene), {
  ssr: false,
});

interface RevisionListItem {
  id: number;
  project_id: string;
  version: number;
  label: string | null;
  created_at: string;
}

const TYPE_LABELS: Record<string, string> = {
  living: "Living / Hall",
  bedroom: "Bedroom",
  master_bedroom: "Master Bedroom",
  kitchen: "Kitchen",
  toilet: "Toilet",
  staircase: "Staircase",
  parking: "Parking",
  utility: "Utility / Other",
  pooja: "Pooja Room",
  study: "Study",
  balcony: "Balcony",
  dining: "Dining",
  servant_quarter: "Servant Quarter",
  home_office: "Home Office",
  gym: "Gym",
  store_room: "Store Room",
  garage: "Garage",
  passage: "Passage",
};

const SWATCH: Record<string, string> = {
  living: "bg-yellow-100 border-yellow-400",
  bedroom: "bg-violet-100 border-violet-500",
  master_bedroom: "bg-purple-100 border-purple-500",
  kitchen: "bg-green-100 border-green-600",
  toilet: "bg-sky-100 border-sky-500",
  staircase: "bg-slate-100 border-slate-400",
  parking: "bg-slate-50 border-slate-300",
  utility: "bg-slate-50 border-slate-300",
  pooja: "bg-orange-50 border-orange-400",
  study: "bg-emerald-50 border-emerald-500",
  balcony: "bg-blue-50 border-blue-400",
  dining: "bg-yellow-50 border-yellow-500",
  servant_quarter: "bg-orange-50 border-orange-500",
  home_office: "bg-green-50 border-green-500",
  gym: "bg-red-50 border-red-400",
  store_room: "bg-slate-50 border-slate-400",
  garage: "bg-blue-50 border-blue-500",
  passage: "bg-slate-100 border-slate-400",
};

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 75
      ? "bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/40"
      : score >= 55
        ? "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/40"
        : "bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/40";
  return (
    <span className={`ml-1.5 rounded-md border px-1.5 py-0.5 text-xs font-semibold ${color}`}>
      {score.toFixed(0)}
    </span>
  );
}

// ── CAD drawing-quality badge — lazily fetched per layout, progressive enhancement ──
function CadQualityBadge({ projectId, layoutKey }: { projectId: string; layoutKey: string }) {
  const [quality, setQuality] = useState<CadQuality | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/backend/projects/${projectId}/layouts/${layoutKey}/quality`)
      .then((r) => (r.ok ? r.json() : null))
      .then((q) => {
        if (!cancelled && q) setQuality(q);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [projectId, layoutKey]);

  if (!quality) return null;

  const tone = cadQualityTone(quality);
  const color =
    tone === "good"
      ? "bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/40"
      : tone === "ok"
        ? "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/40"
        : "bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/40";
  return (
    <span
      className={`ml-1.5 rounded-md border px-1.5 py-0.5 text-xs font-semibold ${color}`}
      title="Deterministic CAD drawing quality (monochrome, dimensions, labels, completeness)"
    >
      {cadQualityLabel(quality)}
    </span>
  );
}

type ApprovalStatus = "approved" | "changes_requested" | "pending" | null;

interface ApprovalInfo {
  status: ApprovalStatus;
  note: string | null;
  updatedAt: string | null;
}

interface LayoutViewerProps {
  generateData: GenerateResponse | null;
  plotWidth: number;
  plotLength: number;
  roadSide: string;
  northDirection: string;
  projectId: string;
  projectName: string;
  planTier: string;
  plotShape?: string;
  plotFrontWidth?: number;
  plotRearWidth?: number;
  plotCorners?: [number, number][];
  cutoutCorner?: string;
  cutoutWidth?: number;
  cutoutHeight?: number;
  numFloors?: number;
  vastuEnabled?: boolean;
  municipality?: string | null;
  shareToken?: string | null;
  initialApproval?: ApprovalInfo;
}

export function LayoutViewer({
  generateData,
  plotWidth,
  plotLength,
  roadSide,
  projectId,
  projectName,
  planTier,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
  plotCorners,
  cutoutCorner,
  cutoutWidth,
  cutoutHeight,
  numFloors: _numFloors = 1,
  vastuEnabled = false,
  municipality = null,
  shareToken = null,
  initialApproval,
}: LayoutViewerProps) {
  const { data: session } = useSession();
  const { locale } = useLocale();
  const router = useRouter();
  const [regenerating, setRegenerating] = useState(false);
  // Use the first layout's actual ID — IDs may be "S1","S2","D" etc, never assume "A"
  const [selectedId, setSelectedId] = useState(() => generateData?.layouts[0]?.id ?? "A");
  const [liveLayout, setLiveLayout] = useState<LayoutData | null>(null);

  // ── Stage 2 structural lifecycle (approve → design) ───────────────────────
  // Single fetch feeds both the header badge and the Structural tab, so
  // approve/design/edit all refresh from one place.
  const [structStatus, setStructStatus] = useState<StructuralStatusResponse | null>(null);
  const [approvingStructural, setApprovingStructural] = useState(false);
  // Transient notice when a re-approve is a no-op (backend returns
  // created: false) — the geometry was already frozen as a revision.
  const [alreadyApprovedNotice, setAlreadyApprovedNotice] = useState(false);
  // Render-source toggle (deliverable 6) — swaps the geometry fed to the R3F
  // preview / AI render conditioning image between the stored architectural
  // layout and the structural design's adjusted geometry (final_geometry
  // from GET .../structural/design), when one exists.
  const [renderSource, setRenderSource] = useState<"architectural" | "structural">("architectural");
  const [structuralGeometry, setStructuralGeometry] = useState<LayoutData | null>(null);
  const [structuralGeometryLoading, setStructuralGeometryLoading] = useState(false);
  const [structuralGeometryFallback, setStructuralGeometryFallback] =
    useState<RenderSourceFallbackReason | null>(null);

  const fetchStructuralStatus = useCallback(async () => {
    if (!session) return;
    try {
      const res = await fetch(
        `/api/backend/projects/${projectId}/structural/status?layout_id=${selectedId}`
      );
      if (!res.ok) {
        setStructStatus(null);
        return;
      }
      setStructStatus((await res.json()) as StructuralStatusResponse);
    } catch {
      setStructStatus(null);
    }
  }, [session, projectId, selectedId]);

  const fetchStructuralGeometry = useCallback(async () => {
    if (!session) return;
    setStructuralGeometryLoading(true);
    setStructuralGeometryFallback(null);
    try {
      const res = await fetch(
        `/api/backend/projects/${projectId}/structural/design?layout_id=${selectedId}`
      );
      if (!res.ok) {
        const code = await res
          .json()
          .then((body) => body?.detail?.code as string | undefined)
          .catch(() => undefined);
        setStructuralGeometry(null);
        setStructuralGeometryFallback(
          res.status === 409 || code === "not_approved" ? "not_approved" : "no_design"
        );
        return;
      }
      const data = (await res.json()) as { final_geometry: LayoutData | null };
      if (!data.final_geometry) {
        setStructuralGeometry(null);
        setStructuralGeometryFallback("no_adjustment");
        return;
      }
      setStructuralGeometry(data.final_geometry);
    } catch {
      setStructuralGeometry(null);
      setStructuralGeometryFallback("no_design");
    } finally {
      setStructuralGeometryLoading(false);
    }
  }, [session, projectId, selectedId]);

  function handleRenderSourceChange(source: "architectural" | "structural") {
    setRenderSource(source);
    if (source === "structural" && !structuralGeometry && !structuralGeometryLoading) {
      void fetchStructuralGeometry();
    }
  }

  useEffect(() => {
    setRenderSource("architectural");
    setStructuralGeometry(null);
    setStructuralGeometryFallback(null);
    setAlreadyApprovedNotice(false);
    setStructDrawingsBlob(null);
    void fetchStructuralStatus();
  }, [fetchStructuralStatus]);

  async function handleApproveStructural() {
    if (!session) return;
    setApprovingStructural(true);
    setAlreadyApprovedNotice(false);
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/structural/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ layout_id: selectedId }),
      });
      if (res.ok) {
        // created === false means the current geometry was already frozen
        // as an approved revision — surface it so the click isn't a silent
        // no-op, but still refetch status to stay consistent.
        const body = (await res.json().catch(() => null)) as { created?: boolean } | null;
        if (body?.created === false) setAlreadyApprovedNotice(true);
        await fetchStructuralStatus();
      }
    } catch {
      // silent — the lifecycle header/tab surface stale-status states gracefully
    } finally {
      setApprovingStructural(false);
    }
  }

  // ── R3F 3D engine (geometric conditioning image for the AI render) ───────
  const plan3dApiRef = useRef<Plan3DHandle | null>(null);
  // One captured snapshot per floor index — each floor gets its own render.
  const [r3fPngs, setR3fPngs] = useState<Record<number, string | null>>({});
  const [r3fView, setR3fView] = useState<Plan3DView>("top");
  const renderTriggerRef = useRef<(floorIndex: number, png?: string | null) => void>(() => {});
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  // Plan3DScene ships ~150KB of three.js — deferred via next/dynamic and only
  // mounted the first time it's actually needed (visiting the r3f/"Render" or
  // render/"AI Render" tab). Once mounted it stays mounted for the rest of the
  // session (never gated back off on tab-switch) so its offscreen PNG capture
  // keeps working from any tab — see the capture-trigger call sites below.
  const [plan3dMounted, setPlan3dMounted] = useState(false);
  const [floor, setFloor] = useState(0);
  // Snapshots are per layout AND per render source — drop them when the
  // viewed layout changes, or when the architectural/structural toggle
  // flips (a cached architectural PNG must not linger under "structural").
  // biome-ignore lint/correctness/useExhaustiveDependencies: selectedId/renderSource are intentional reset triggers, not read in the body
  useEffect(() => {
    setR3fPngs({});
  }, [selectedId, renderSource]);
  const captureR3f = useCallback(() => {
    // Defensive fallback: a capture requested before the scene has ever been
    // mounted (no current call site does this, but a future one might) can't
    // return a PNG synchronously — arm the mount for next render instead of
    // reading from a null ref.
    if (!plan3dMounted) {
      setPlan3dMounted(true);
      return null;
    }
    const png = plan3dApiRef.current?.capture() ?? null;
    if (png) setR3fPngs((prev) => ({ ...prev, [floor]: png }));
    return png;
  }, [floor, plan3dMounted]);

  // Single invalidation routine for every geometry-mutating action (manual
  // room edit, AI chat edit). The backend reverts Approved→Draft and marks
  // designs stale on any geometry change; the UI must drop every derived
  // artifact with it — lifecycle status, cached structural geometry, the
  // render-source selection, captured R3F reference snapshots — and bust
  // the server-side layout cache so a reload agrees with the edit. Each
  // edit path previously did a different subset (the AI-chat path did
  // none), leaving a stale "DESIGNED" badge and pre-edit conditioning
  // images after edits.
  const invalidateAfterGeometryEdit = useCallback(() => {
    setRenderSource("architectural");
    setStructuralGeometry(null);
    setStructuralGeometryFallback(null);
    setR3fPngs({});
    void fetchStructuralStatus();
    void fetch(`/api/projects/${projectId}/revalidate`, { method: "POST" }).catch(() => {});
  }, [fetchStructuralStatus, projectId]);

  // After a design run completes the architectural layout is untouched, but
  // the structural artifacts are new: refresh status and re-fetch the
  // designed geometry if the render source is showing it (a re-run with,
  // e.g., a different SBC previously kept serving the OLD design's
  // final_geometry to the R3F preview and AI-render conditioning image).
  const handleDesignComplete = useCallback(() => {
    setStructuralGeometry(null);
    setStructuralGeometryFallback(null);
    setR3fPngs({});
    void fetchStructuralStatus();
    if (renderSource === "structural") void fetchStructuralGeometry();
  }, [fetchStructuralStatus, fetchStructuralGeometry, renderSource]);
  const agentChatEnabled = process.env.NEXT_PUBLIC_AGENT_CHAT === "1";
  const tabs = visibleTabs(agentChatEnabled);
  const [activeTab, setActiveTab] = useState<TabId>("plan");
  // First-mount trigger: visiting either the "r3f" (3D "Render") tab or the
  // "render" ("AI Render") tab mounts the offscreen Plan3DScene if it hasn't
  // been already. It then stays mounted, so a later capture triggered from
  // any other tab (e.g. Structural) keeps working without needing to revisit
  // either tab.
  useEffect(() => {
    if ((activeTab === "r3f" || activeTab === "render") && mounted) {
      setPlan3dMounted(true);
    }
  }, [activeTab, mounted]);
  // Auto-capture the offscreen R3F view when the Render tab opens, the
  // viewed floor / camera view changes, or the architectural/structural
  // geometry source toggle flips (structuralGeometry is read via the
  // offscreen Plan3DScene's floorPlan prop, not directly in this body).
  // biome-ignore lint/correctness/useExhaustiveDependencies: r3fView/renderSource/structuralGeometry are intentional re-capture triggers, not read in the body
  useEffect(() => {
    if (activeTab === "r3f" && plan3dMounted) {
      const t = setTimeout(() => captureR3f(), 500);
      return () => clearTimeout(t);
    }
  }, [activeTab, plan3dMounted, captureR3f, r3fView, renderSource, structuralGeometry]);
  const [showVastuZones, setShowVastuZones] = useState(false);
  const [showFurniture, setShowFurniture] = useState(false);
  const [showElectrical, setShowElectrical] = useState(false);
  const [showPlumbing, setShowPlumbing] = useState(false);

  // ── Edit mode state ────────────────────────────────────────────────────────
  const [editMode, setEditMode] = useState(false);
  const [editedRooms, setEditedRooms] = useState<RoomData[] | null>(null);
  const [editHistory, setEditHistory] = useState<EditHistory<RoomData[]> | null>(null);
  const [complianceIssues, setComplianceIssues] = useState<Record<string, string[]>>({});
  const [editSaving, setEditSaving] = useState(false);
  const [editSaveError, setEditSaveError] = useState("");
  const complianceDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const editedFloorRef = useRef<string | null>(null);

  // ── Annotation state ───────────────────────────────────────────────────────
  const [annotationMode, setAnnotationMode] = useState(false);
  // annotations keyed by room_id
  const [annotations, setAnnotations] = useState<Record<string, Annotation>>({});
  const [annotationsLoaded, setAnnotationsLoaded] = useState(false);
  // Annotation dialog state
  const [annDialogOpen, setAnnDialogOpen] = useState(false);
  const [annEditRoomId, setAnnEditRoomId] = useState("");
  const [annEditRoomName, setAnnEditRoomName] = useState("");
  const [annEditNote, setAnnEditNote] = useState("");
  const [annSaving, setAnnSaving] = useState(false);
  // Debounce timer ref for PUT
  const annDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [downloadingDxf, setDownloadingDxf] = useState(false);
  const [generatingStructDrawings, setGeneratingStructDrawings] = useState(false);
  const [structDrawingsBlob, setStructDrawingsBlob] = useState<Blob | null>(null);
  const [downloadError, setDownloadError] = useState("");
  const [pdfPreviewOpen, setPdfPreviewOpen] = useState(false);
  const [approvalPdfPreviewOpen, setApprovalPdfPreviewOpen] = useState(false);
  const [dxfPreviewOpen, setDxfPreviewOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareTab, setShareTab] = useState<"link" | "approval">("link");
  const [shareUrl, setShareUrl] = useState("");
  const [shareLoading, setShareLoading] = useState(false);
  const [shareError, setShareError] = useState("");
  const [copied, setCopied] = useState(false);

  // ── Client Approval state ─────────────────────────────────────────────────
  const [approval, setApproval] = useState<ApprovalInfo>({
    status: initialApproval?.status ?? null,
    note: initialApproval?.note ?? null,
    updatedAt: initialApproval?.updatedAt ?? null,
  });
  const [approvalFetching, setApprovalFetching] = useState(false);
  const [approvalShareUrl, setApprovalShareUrl] = useState(
    shareToken
      ? `${typeof window !== "undefined" ? window.location.origin : ""}/share/${shareToken}`
      : ""
  );
  const [approvalShareCopied, setApprovalShareCopied] = useState(false);
  const [approvalShareLoading, setApprovalShareLoading] = useState(false);
  const [approvalShareError, setApprovalShareError] = useState("");

  async function fetchApprovalStatus() {
    if (!session) return;
    setApprovalFetching(true);
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/approval-status`);
      if (!res.ok) return;
      const data = await res.json();
      setApproval({
        status: data.approval_status as ApprovalStatus,
        note: data.approval_note ?? null,
        updatedAt: data.approval_updated_at ?? null,
      });
    } catch {
      // silent — approval status is non-critical
    } finally {
      setApprovalFetching(false);
    }
  }

  // ── Annotation helpers ─────────────────────────────────────────────────────

  const saveAnnotationsToBackend = useCallback(
    (updated: Record<string, Annotation>) => {
      if (!session) return;
      if (annDebounceRef.current) clearTimeout(annDebounceRef.current);
      annDebounceRef.current = setTimeout(async () => {
        try {
          await fetch(`/api/backend/projects/${projectId}/annotations`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(updated),
          });
        } catch {
          // silent — annotations are non-critical, will retry on next save
        }
      }, 500);
    },
    [session, projectId]
  );

  useEffect(() => {
    if (!session || annotationsLoaded) return;
    setAnnotationsLoaded(true);
    fetch(`/api/backend/projects/${projectId}/annotations`)
      .then((r) => (r.ok ? r.json() : {}))
      .then((data: Record<string, Annotation>) => setAnnotations(data))
      .catch(() => {});
  }, [session, projectId, annotationsLoaded]);

  function handleAnnotationClick(roomId: string, roomName: string, _x: number, _y: number) {
    const existing = annotations[roomId];
    setAnnEditRoomId(roomId);
    setAnnEditRoomName(roomName);
    setAnnEditNote(existing?.note ?? "");
    setAnnDialogOpen(true);
  }

  function handleAnnotationSave() {
    if (!annEditRoomId) return;
    setAnnSaving(true);
    const updated = { ...annotations };
    if (annEditNote.trim()) {
      updated[annEditRoomId] = {
        room_id: annEditRoomId,
        room_name: annEditRoomName,
        note: annEditNote.trim(),
        x: 0,
        y: 0,
      };
    } else {
      delete updated[annEditRoomId];
    }
    setAnnotations(updated);
    saveAnnotationsToBackend(updated);
    setAnnDialogOpen(false);
    setAnnEditNote("");
    setAnnSaving(false);
  }

  function handleAnnotationDelete() {
    if (!annEditRoomId) return;
    const updated = { ...annotations };
    delete updated[annEditRoomId];
    setAnnotations(updated);
    saveAnnotationsToBackend(updated);
    setAnnDialogOpen(false);
    setAnnEditNote("");
  }

  const annotationCount = Object.keys(annotations).filter((k) => annotations[k]?.note).length;
  const annotationList = Object.values(annotations);

  // ── Edit mode handlers ─────────────────────────────────────────────────────

  function handleToggleEditMode() {
    if (editMode) {
      // Exit edit mode — discard unsaved changes
      setEditMode(false);
      setEditedRooms(null);
      setEditHistory(null);
      setComplianceIssues({});
      setEditSaveError("");
    } else {
      setEditMode(true);
      setEditedRooms(null);
      setEditHistory(initHistory(floorPlan.rooms));
      setComplianceIssues({});
    }
  }

  function handleResetRooms() {
    setEditedRooms(null);
    setEditHistory(initHistory(floorPlan.rooms));
    setComplianceIssues({});
  }

  const runComplianceCheck = useCallback(
    async (rooms: RoomData[], floorLabel: string): Promise<void> => {
      if (!session) return;
      const floorCode =
        floorLabel === "ff"
          ? "ff"
          : floorLabel === "sf"
            ? "sf"
            : floorLabel === "basement"
              ? "basement"
              : "gf";
      try {
        const body = {
          rooms: rooms.map((r) => ({
            id: r.id,
            type: r.type,
            name: r.name,
            x: r.x,
            y: r.y,
            width: r.width,
            height: r.depth,
            floor: floorCode,
          })),
        };
        const res = await fetch(`/api/backend/layouts/${selectedId}/compliance-check`, {
          method: "POST",
          headers: {
            "X-Project-Id": projectId,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        });
        if (!res.ok) return;
        const data = (await res.json()) as {
          passed: boolean;
          violations: string[];
          warnings: string[];
          room_issues: Record<string, string[]>;
        };
        setComplianceIssues(data.room_issues);
      } catch {
        // silent — compliance check is non-critical
      }
    },
    [session, selectedId, projectId]
  );

  function handleRoomsChange(rooms: RoomData[], floorCode: string) {
    setEditedRooms(rooms);
    setEditHistory((h) => (h ? pushHistory(h, rooms) : h));
    editedFloorRef.current = floorCode;
    // Debounced compliance check: runs 800ms after last drag
    if (complianceDebounceRef.current) clearTimeout(complianceDebounceRef.current);
    complianceDebounceRef.current = setTimeout(() => {
      void runComplianceCheck(rooms, floorCode);
    }, 800);
  }

  const handleUndo = useCallback(() => {
    setEditHistory((h) => {
      if (!h || !canUndo(h)) return h;
      const next = undoHistory(h);
      setEditedRooms(next.present);
      const floorCode =
        editedFloorRef.current ??
        (floor === 1 ? "ff" : floor === 2 ? "sf" : floor === -1 ? "basement" : "gf");
      void runComplianceCheck(next.present, floorCode);
      return next;
    });
  }, [floor, runComplianceCheck]);

  const handleRedo = useCallback(() => {
    setEditHistory((h) => {
      if (!h || !canRedo(h)) return h;
      const next = redoHistory(h);
      setEditedRooms(next.present);
      const floorCode =
        editedFloorRef.current ??
        (floor === 1 ? "ff" : floor === 2 ? "sf" : floor === -1 ? "basement" : "gf");
      void runComplianceCheck(next.present, floorCode);
      return next;
    });
  }, [floor, runComplianceCheck]);

  useEffect(() => {
    if (!editMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) handleRedo();
      else handleUndo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editMode, handleUndo, handleRedo]);

  async function handleSaveEditedRooms(rooms: RoomData[]) {
    if (!session) return;
    setEditSaving(true);
    setEditSaveError("");
    try {
      // One PATCH with the full room list — positions AND sizes. The old
      // per-room resize loop silently dropped x/y (wall-drag moves were
      // never persisted).
      const floorCode = editedFloorRef.current ?? "gf";
      const res = await fetch(`/api/backend/projects/${projectId}/layouts/${selectedId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          rooms: rooms.map((r) => ({
            id: r.id,
            type: r.type,
            name: r.name,
            x: r.x,
            y: r.y,
            width: r.width,
            height: r.depth,
            floor: floorCode,
          })),
        }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        detail?: string;
        layout?: LayoutData;
      };
      if (!res.ok) {
        throw new Error(data?.detail ?? `Save failed (${res.status})`);
      }
      // Show the persisted geometry immediately instead of reverting to the
      // stale pre-edit prop, and bust the server-side layout cache so a
      // reload agrees with what was just saved.
      if (data.layout) setLiveLayout(data.layout);
      invalidateAfterGeometryEdit();
      setEditMode(false);
      setEditedRooms(null);
      setComplianceIssues({});
      showToast("success", "Changes saved");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not save changes";
      setEditSaveError(message);
      showErrorToast(message);
    } finally {
      setEditSaving(false);
    }
  }

  async function handleSendForApproval() {
    if (!session) return;
    setApprovalShareLoading(true);
    setApprovalShareError("");
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/share`, { method: "POST" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error((data as { detail?: string })?.detail ?? `Failed (${res.status})`);
      }
      const json = await res.json();
      const fullUrl = `${window.location.origin}${json.share_url}`;
      setApprovalShareUrl(fullUrl);
      setShareTab("approval");
      setShareOpen(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not generate share link";
      setApprovalShareError(message);
      showErrorToast(message);
    } finally {
      setApprovalShareLoading(false);
    }
  }

  async function handleCopyApprovalLink() {
    try {
      await navigator.clipboard.writeText(approvalShareUrl);
      setApprovalShareCopied(true);
      setTimeout(() => setApprovalShareCopied(false), 2000);
    } catch {
      // fallback
    }
  }

  function formatApprovalDate(iso: string): string {
    return new Date(iso).toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }

  // ── Approval PDF state ────────────────────────────────────────────────────
  const [approvalDialogOpen, setApprovalDialogOpen] = useState(false);
  const [approvalForm, setApprovalForm] = useState({
    owner_name: "",
    survey_number: "",
    locality: "",
    engineer_name: "",
    license_number: "",
    municipality: municipality ?? "",
  });
  const [downloadingApprovalPdf, setDownloadingApprovalPdf] = useState(false);
  const [approvalPdfError, setApprovalPdfError] = useState("");

  // ── Version History state ──────────────────────────────────────────────────
  const [historyOpen, setHistoryOpen] = useState(false);
  const [revisions, setRevisions] = useState<RevisionListItem[]>([]);
  const [revisionsLoading, setRevisionsLoading] = useState(false);
  const [revisionsError, setRevisionsError] = useState("");
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [snapshotLabel, setSnapshotLabel] = useState("");
  const [showSnapshotInput, setShowSnapshotInput] = useState(false);
  const [restoredData, setRestoredData] = useState<GenerateResponse | null>(null);
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null);

  async function fetchRevisions() {
    if (!session) return;
    setRevisionsLoading(true);
    setRevisionsError("");
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/revisions`);
      if (!res.ok) throw new Error(`Failed to load revisions (${res.status})`);
      const data = (await res.json()) as RevisionListItem[];
      setRevisions(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not load revision history";
      setRevisionsError(message);
      showErrorToast(message);
    } finally {
      setRevisionsLoading(false);
    }
  }

  function handleHistoryToggle() {
    setHistoryOpen((prev) => {
      if (!prev) fetchRevisions();
      return !prev;
    });
  }

  async function handleSaveSnapshot() {
    if (!session) return;
    setSavingSnapshot(true);
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/revisions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ label: snapshotLabel.trim() || null }),
      });
      if (!res.ok) throw new Error(`Failed to save snapshot (${res.status})`);
      setSnapshotLabel("");
      setShowSnapshotInput(false);
      await fetchRevisions();
      showToast("success", "Snapshot saved");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not save snapshot";
      setRevisionsError(message);
      showErrorToast(message);
    } finally {
      setSavingSnapshot(false);
    }
  }

  async function handleRestore(version: number) {
    if (!session) return;
    setRestoringVersion(version);
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/revisions/${version}`);
      if (!res.ok) throw new Error(`Failed to load revision v${version} (${res.status})`);
      const detail = (await res.json()) as { snapshot: GenerateResponse };
      setRestoredData(detail.snapshot);
      setSelectedId(detail.snapshot.layouts[0]?.id ?? selectedId);
      setLiveLayout(null);
      setFloor(0);
      showToast("success", `Restored version ${version}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not restore revision";
      setRevisionsError(message);
      showErrorToast(message);
    } finally {
      setRestoringVersion(null);
    }
  }

  function handleClearRestore() {
    setRestoredData(null);
    setSelectedId(generateData?.layouts[0]?.id ?? "A");
    setLiveLayout(null);
    setFloor(0);
  }

  async function handleDeleteRevision(version: number) {
    if (!session) return;
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/revisions/${version}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`Failed to delete revision (${res.status})`);
      await fetchRevisions();
      showToast("success", `Deleted version ${version}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not delete revision";
      setRevisionsError(message);
      showErrorToast(message);
    }
  }

  // Fetch-or-create the public share URL for this project. The backend is
  // idempotent (POST /share returns the existing token if one was already
  // minted), so it's safe to call this from multiple entry points — the
  // Share dialog, "Send for approval", and the WhatsApp share button — and
  // reuse the cached `shareUrl` once created.
  async function ensureShareUrl(): Promise<string> {
    if (shareUrl) return shareUrl;
    const res = await fetch(`/api/backend/projects/${projectId}/share`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data?.detail ?? `Failed to generate share link (${res.status})`);
    }
    const json = await res.json();
    const fullUrl = buildShareUrl(window.location.origin, json.share_url);
    setShareUrl(fullUrl);
    return fullUrl;
  }

  async function handleShare() {
    if (!session) return;
    setShareLoading(true);
    setShareError("");
    try {
      await ensureShareUrl();
      setShareTab("link");
      setShareOpen(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not generate share link";
      setShareError(message);
      showErrorToast(message);
    } finally {
      setShareLoading(false);
    }
  }

  // Lazily fetch each tab's link the first time it's viewed — avoids firing
  // both `ensureShareUrl()` and `handleSendForApproval()` on every dialog open.
  function handleShareTabChange(tab: string) {
    setShareTab(tab as "link" | "approval");
    if (tab === "link" && !shareUrl) {
      handleShare();
    } else if (tab === "approval" && !approvalShareUrl) {
      handleSendForApproval();
    }
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback: select the input text
    }
  }

  async function handleDownloadApprovalPdf() {
    if (!session) return;
    setDownloadingApprovalPdf(true);
    setApprovalPdfError("");
    try {
      const blob = await fetchApprovalPdfBlob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `planforge-approval-${projectId}-layout-${selectedId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setApprovalDialogOpen(false);
      showToast("success", "Approval PDF downloaded");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Approval PDF download failed";
      setApprovalPdfError(message);
      showErrorToast(message);
    } finally {
      setDownloadingApprovalPdf(false);
    }
  }

  // Fetch-only helper (no download side effect) shared by the download
  // button and the inline preview dialog.
  async function fetchApprovalPdfBlob(): Promise<Blob> {
    const res = await fetch(
      `/api/backend/projects/${projectId}/export/approval-pdf?layout_id=${selectedId}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(approvalForm),
      }
    );
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(
        (data as { detail?: string })?.detail ?? `Approval PDF export failed (${res.status})`
      );
    }
    return res.blob();
  }

  // Fetch-only helper (no download side effect) shared by the download
  // button and the inline preview dialog.
  async function fetchExportBlob(format: "pdf" | "dxf"): Promise<Blob> {
    const res = await fetch(
      `/api/backend/projects/${projectId}/export/${format}?layout_id=${selectedId}`
    );
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data?.detail ?? `Export failed (${res.status})`);
    }
    return res.blob();
  }

  async function handleDownload(format: "pdf" | "dxf") {
    if (!session) return;
    const setter = format === "pdf" ? setDownloadingPdf : setDownloadingDxf;
    setter(true);
    setDownloadError("");
    try {
      const blob = await fetchExportBlob(format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `planforge-layout-${selectedId}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("success", `${format.toUpperCase()} downloaded`);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Download failed — is the backend running?";
      setDownloadError(message);
      showErrorToast(message);
    } finally {
      setter(false);
    }
  }

  function saveStructDrawings(blob: Blob) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `planforge-structural-drawings-${projectId}-layout-${selectedId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleGenerateStructDrawings() {
    if (!session) return;
    setGeneratingStructDrawings(true);
    try {
      const res = await fetch(
        `/api/backend/projects/${projectId}/export/structural-drawing-set?layout_id=${selectedId}`
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = (data as { detail?: unknown })?.detail;
        let message = `Structural drawings export failed (${res.status})`;
        if (typeof detail === "string") {
          message = detail;
        } else if (detail && typeof detail === "object") {
          const { code, help } = detail as { code?: string; help?: string };
          if (code === "not_approved") message = "Approve the architectural plan first.";
          else if (code === "not_designed") message = "Run structural design first.";
          else message = help ?? message;
        }
        throw new Error(message);
      }
      const blob = await res.blob();
      setStructDrawingsBlob(blob);
      saveStructDrawings(blob);
      showToast("success", "Structural drawings generated");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Structural drawings export failed";
      showErrorToast(message);
    } finally {
      setGeneratingStructDrawings(false);
    }
  }

  if (!generateData) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">
        <div>
          <p className="font-medium">Couldn&apos;t load layouts</p>
          <p className="mt-1 text-sm">
            The layout service didn&apos;t respond — this is usually temporary.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => router.refresh()}>
          Retry
        </Button>
      </div>
    );
  }

  if (generateData.layouts.length === 0) {
    return <GenerationPanel projectId={projectId} autoStart />;
  }

  // Use restoredData for display when a revision is active, else live data
  const activeData = restoredData ?? generateData;

  const baseLayout = activeData.layouts.find((l) => l.id === selectedId) ?? activeData.layouts[0];
  const layout = liveLayout ?? baseLayout;

  // Build the ordered list of available floors for this layout
  const availableFloors: { label: string; index: number; plan: FloorPlanData }[] = [];
  if (layout.basement_floor)
    availableFloors.push({ label: "Basement", index: -1, plan: layout.basement_floor });
  availableFloors.push({
    label: layout.ground_floor.floor_type === "stilt" ? "Stilt Floor" : "Ground Floor",
    index: 0,
    plan: layout.ground_floor,
  });
  availableFloors.push({ label: "First Floor", index: 1, plan: layout.first_floor });
  if (layout.second_floor)
    availableFloors.push({ label: "Second Floor", index: 2, plan: layout.second_floor });

  const currentFloorEntry = availableFloors.find((f) => f.index === floor) ?? availableFloors[1];
  const floorPlan = currentFloorEntry.plan;
  const presentTypes = [...new Set(floorPlan.rooms.map((r) => r.type))];

  // R3F / AI render geometry source — the Floor Plan / BOQ / Structural
  // tabs always show the stored architectural layout above; only the R3F
  // preview and the AI render conditioning image (fed from the same
  // offscreen Plan3DScene) swap to the structural design's final_geometry
  // when the toggle is set and a design with an adjustment is loaded.
  const r3fSourceLayout =
    renderSource === "structural" && structuralGeometry ? structuralGeometry : layout;
  const r3fFloorPlan: FloorPlanData = r3fSourceLayout[floorKeyFromIndex(floor)] ?? floorPlan;

  return (
    <div className="flex flex-col gap-4 md:gap-6">
      {/* Layout selector + export buttons */}
      <div className="flex flex-col gap-3">
        {/* Layout buttons — horizontal scroll on mobile */}
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none -mx-4 px-4 [mask-image:linear-gradient(to_right,black_92%,transparent_100%)] md:mx-0 md:px-0 md:flex-wrap md:[mask-image:none]">
          {activeData.layouts.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => {
                setSelectedId(l.id);
                setFloor(0);
                setLiveLayout(null);
              }}
              className={[
                "rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors shrink-0 min-h-[44px]",
                selectedId === l.id
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-transparent hover:bg-muted",
              ].join(" ")}
            >
              Layout {l.id} — {l.name}
              {l.score && <ScoreBadge score={l.score.total} />}
              <CadQualityBadge layoutKey={l.id} projectId={projectId} />
              {vastuEnabled && (
                <span
                  className={[
                    "ml-1 rounded-sm border px-1 py-0.5 text-xs flex items-center gap-1",
                    l.compliance.violations.some((v) => v.startsWith("[Vastu]"))
                      ? "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400"
                      : l.compliance.warnings.some((w) => w.startsWith("[Vastu]"))
                        ? "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                        : "border-green-500/40 bg-green-500/10 text-green-600 dark:text-green-400",
                  ].join(" ")}
                >
                  <span>Vastu</span>
                  {l.compliance.violations.some((v) => v.startsWith("[Vastu]")) ? (
                    <>
                      <X className="h-3 w-3 shrink-0" aria-hidden="true" />
                      <span className="sr-only">Vastu violation</span>
                    </>
                  ) : l.compliance.warnings.some((w) => w.startsWith("[Vastu]")) ? (
                    <>
                      <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
                      <span className="sr-only">Vastu warning</span>
                    </>
                  ) : (
                    <>
                      <Check className="h-3 w-3 shrink-0" aria-hidden="true" />
                      <span className="sr-only">Vastu passed</span>
                    </>
                  )}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Primary actions + Export/Share — horizontal scroll on mobile */}
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none -mx-4 px-4 [mask-image:linear-gradient(to_right,black_92%,transparent_100%)] md:mx-0 md:px-0 md:flex-wrap md:items-center md:[mask-image:none]">
          {/* PDF — primary action, prominent on mobile */}
          <Button
            size="sm"
            className="shrink-0 min-h-[40px] md:min-h-0 bg-primary text-primary-foreground hover:bg-primary/90 md:bg-transparent md:text-foreground md:border md:border-border md:hover:bg-muted md:shadow-none shadow-md"
            onClick={() => handleDownload("pdf")}
            disabled={downloadingPdf || !session}
          >
            {downloadingPdf ? "…" : "⬇ PDF"}
          </Button>

          {/* Export — everything else export-related, tucked behind one dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 min-h-[40px] md:min-h-0 border-border text-foreground hover:bg-muted"
                disabled={!session}
              >
                Export
                <ChevronDown className="h-3 w-3 ml-1.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-64">
              <DropdownMenuItem onClick={() => setPdfPreviewOpen(true)}>
                Preview PDF
              </DropdownMenuItem>
              {planTier === "free" ? (
                <DropdownMenuItem asChild title="Upgrade to Basic for DXF export">
                  <Link href="/pricing">
                    <Lock className="h-3 w-3" />
                    DXF (upgrade required)
                  </Link>
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem
                  onClick={() => handleDownload("dxf")}
                  disabled={downloadingDxf}
                  title="DXF for AutoCAD / DraftSight"
                >
                  {downloadingDxf ? "Downloading DXF…" : "DXF"}
                </DropdownMenuItem>
              )}
              {planTier !== "free" && (
                <DropdownMenuItem onClick={() => setDxfPreviewOpen(true)}>
                  Preview DXF
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => setApprovalDialogOpen(true)}
                title="Download municipality approval drawing package (CMDA/BBMP/GHMC format)"
              >
                Approval Package
              </DropdownMenuItem>
              {(structStatus?.design?.status === "designed" || structDrawingsBlob) && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuLabel>Structural drawings</DropdownMenuLabel>
                  {structStatus?.design?.status === "designed" && (
                    <DropdownMenuItem
                      onClick={handleGenerateStructDrawings}
                      disabled={generatingStructDrawings}
                      title="Generate the 6-sheet structural drawing set (column & footing, plinth beam, roof beam & slab)"
                    >
                      <FileStack className="h-3 w-3" />
                      {generatingStructDrawings ? "Generating…" : "Generate set"}
                    </DropdownMenuItem>
                  )}
                  {structDrawingsBlob && (
                    <DropdownMenuItem
                      onClick={() => saveStructDrawings(structDrawingsBlob)}
                      title="Download the generated structural drawing set PDF"
                    >
                      <Download className="h-3 w-3" />
                      Download set
                    </DropdownMenuItem>
                  )}
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          <ShareWhatsAppButton
            projectName={projectName}
            layoutId={selectedId}
            getShareUrl={ensureShareUrl}
            disabled={!session}
          />
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 min-h-[40px] md:min-h-0 border-border text-foreground hover:bg-muted"
            onClick={handleShare}
            disabled={shareLoading || approvalShareLoading || !session}
            title="Get a read-only share link, or send this plan for client approval"
          >
            <Link2 className="h-3 w-3 mr-1.5" />
            {shareLoading || approvalShareLoading ? "…" : "Share"}
          </Button>
          {/* Refresh approval status button */}
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 min-h-[40px] md:min-h-0 border-border text-muted-foreground hover:bg-muted"
            onClick={fetchApprovalStatus}
            disabled={approvalFetching || !session}
            title="Refresh client approval status"
          >
            {approvalFetching ? "…" : "↻"}
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 min-h-[40px] md:min-h-0 border-border text-foreground hover:bg-muted"
                disabled={regenerating}
                title="Re-run the layout engine for this project"
              >
                <RefreshCw className="h-3 w-3 mr-1.5" />
                Regenerate layouts
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Regenerate layouts?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will run the layout engine again and replace your current layouts.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => setRegenerating(true)}>
                  Regenerate
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {regenerating && (
        <GenerationPanel projectId={projectId} autoStart onDone={() => setRegenerating(false)} />
      )}

      {/* Annotation dialog */}
      <Dialog
        open={annDialogOpen}
        onOpenChange={(open) => {
          if (!open) {
            setAnnDialogOpen(false);
            setAnnEditNote("");
          }
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-yellow-600" />
              {annEditRoomName}
            </DialogTitle>
            <DialogDescription>
              Add an engineer note for this room. Notes appear as sticky icons on the floor plan and
              in PDF exports.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3 py-2">
            <Textarea
              value={annEditNote}
              onChange={(e) => setAnnEditNote(e.target.value)}
              placeholder="e.g. Client wants wardrobe here, Confirm column clearance with structural engineer…"
              className="min-h-[90px] resize-none text-sm"
              autoFocus
            />
          </div>
          <DialogFooter className="flex items-center gap-2">
            {annotations[annEditRoomId] && (
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive mr-auto"
                onClick={handleAnnotationDelete}
              >
                Delete note
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setAnnDialogOpen(false);
                setAnnEditNote("");
              }}
            >
              Cancel
            </Button>
            <Button size="sm" onClick={handleAnnotationSave} disabled={annSaving}>
              Save note
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Unified Share dialog — read-only link vs. send-for-approval, one trigger two tabs */}
      <Dialog open={shareOpen} onOpenChange={setShareOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Share with client</DialogTitle>
            <DialogDescription>
              Get a read-only link, or send this plan for client approval — no login needed on their
              end either way.
            </DialogDescription>
          </DialogHeader>
          <Tabs value={shareTab} onValueChange={handleShareTabChange}>
            <TabsList className="w-full">
              <TabsTrigger value="link">Share link</TabsTrigger>
              <TabsTrigger value="approval">Send for Approval</TabsTrigger>
            </TabsList>
            <TabsContent value="link" className="flex flex-col gap-2">
              {shareError && (
                <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  {shareError}
                </p>
              )}
              <div className="flex items-center gap-2 mt-2">
                <input
                  readOnly
                  value={shareUrl}
                  className="flex-1 rounded-lg border border-border bg-muted px-3 py-2 text-sm font-mono text-foreground"
                  onFocus={(e) => e.target.select()}
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCopy}
                  className="shrink-0"
                  aria-label={copied ? "Copied to clipboard" : "Copy link"}
                >
                  {copied ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
              {copied && (
                <p className="text-xs text-green-600 dark:text-green-400">Copied to clipboard!</p>
              )}
              <p className="text-xs text-muted-foreground">
                Anyone with this link can view the floor plans in read-only mode — layout options,
                floor plans, section view, and compliance status.
              </p>
            </TabsContent>
            <TabsContent value="approval" className="flex flex-col gap-2">
              {approvalShareError && (
                <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  {approvalShareError}
                </p>
              )}
              <div className="flex items-center gap-2 mt-2">
                <input
                  readOnly
                  value={approvalShareUrl}
                  className="flex-1 rounded-lg border border-border bg-muted px-3 py-2 text-sm font-mono text-foreground"
                  onFocus={(e) => e.target.select()}
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCopyApprovalLink}
                  className="shrink-0"
                  aria-label={approvalShareCopied ? "Copied to clipboard" : "Copy approval link"}
                >
                  {approvalShareCopied ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
              {approvalShareCopied && (
                <p className="text-xs text-green-600 dark:text-green-400">Copied to clipboard!</p>
              )}
              <p className="text-xs text-muted-foreground">
                Share this link with your client — they can approve the plan or request changes.
                After sending, use the ↻ button in the toolbar to check if they've responded.
              </p>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      {/* Approval status indicator */}
      {(approval.status || shareToken) && (
        <div
          className={[
            "flex items-center gap-3 rounded-lg border px-4 py-2.5 text-sm",
            approval.status === "approved"
              ? "border-green-500/40 bg-green-500/8 text-green-700 dark:text-green-400"
              : approval.status === "changes_requested"
                ? "border-amber-500/40 bg-amber-500/8 text-amber-700 dark:text-amber-400"
                : "border-border bg-muted/30 text-muted-foreground",
          ].join(" ")}
        >
          {approval.status === "approved" ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" />
          ) : approval.status === "changes_requested" ? (
            <MessageSquare className="h-4 w-4 shrink-0" />
          ) : shareToken ? (
            <Clock className="h-4 w-4 shrink-0" />
          ) : (
            <CircleDot className="h-4 w-4 shrink-0" />
          )}
          <div className="flex flex-col gap-0.5 flex-1 min-w-0">
            <span className="font-medium">
              {approval.status === "approved"
                ? "Client Approved"
                : approval.status === "changes_requested"
                  ? "Changes Requested"
                  : shareToken
                    ? "Pending client review"
                    : "Not sent for review"}
            </span>
            {approval.updatedAt && (
              <span className="text-xs opacity-80">{formatApprovalDate(approval.updatedAt)}</span>
            )}
            {approval.status === "changes_requested" && approval.note && (
              <Popover>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    className="text-left text-xs underline underline-offset-2 opacity-80 hover:opacity-100 w-fit"
                  >
                    View note
                  </button>
                </PopoverTrigger>
                <PopoverContent className="w-80 text-sm" align="start">
                  <p className="font-semibold mb-2 text-foreground">Client note</p>
                  <p className="text-muted-foreground">{approval.note}</p>
                </PopoverContent>
              </Popover>
            )}
          </div>
        </div>
      )}

      {/* Approval PDF dialog */}
      <Dialog open={approvalDialogOpen} onOpenChange={setApprovalDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Municipality Approval Drawing Package</DialogTitle>
            <DialogDescription>
              Generates a 4-page PDF formatted for CMDA / BBMP / GHMC submission. Fill in the
              project details required by the municipality.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="apr-owner">Owner Name</Label>
                <Input
                  id="apr-owner"
                  value={approvalForm.owner_name}
                  onChange={(e) => setApprovalForm((f) => ({ ...f, owner_name: e.target.value }))}
                  placeholder="e.g. Rajan Kumar"
                  className="text-base"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="apr-survey">Survey / Plot No.</Label>
                <Input
                  id="apr-survey"
                  value={approvalForm.survey_number}
                  onChange={(e) =>
                    setApprovalForm((f) => ({ ...f, survey_number: e.target.value }))
                  }
                  placeholder="e.g. 42/A"
                  className="text-base"
                />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="apr-locality">Locality / Area</Label>
              <Input
                id="apr-locality"
                value={approvalForm.locality}
                onChange={(e) => setApprovalForm((f) => ({ ...f, locality: e.target.value }))}
                placeholder="e.g. Anna Nagar, Chennai"
                className="text-base"
              />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="apr-engineer">Engineer / Architect Name</Label>
                <Input
                  id="apr-engineer"
                  value={approvalForm.engineer_name}
                  onChange={(e) =>
                    setApprovalForm((f) => ({ ...f, engineer_name: e.target.value }))
                  }
                  placeholder="e.g. Er. S. Venkatesh"
                  className="text-base"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="apr-license">License No.</Label>
                <Input
                  id="apr-license"
                  value={approvalForm.license_number}
                  onChange={(e) =>
                    setApprovalForm((f) => ({ ...f, license_number: e.target.value }))
                  }
                  placeholder="e.g. TN/2024/1234"
                  className="text-base"
                />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="apr-municipality">Municipality / Authority</Label>
              <Input
                id="apr-municipality"
                value={approvalForm.municipality}
                onChange={(e) => setApprovalForm((f) => ({ ...f, municipality: e.target.value }))}
                placeholder="e.g. Chennai (CMDA)"
              />
            </div>
            {approvalPdfError && (
              <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                {approvalPdfError}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApprovalDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="outline"
              onClick={() => setApprovalPdfPreviewOpen(true)}
              disabled={!session}
            >
              Preview
            </Button>
            <Button
              onClick={handleDownloadApprovalPdf}
              disabled={downloadingApprovalPdf || !session}
            >
              {downloadingApprovalPdf ? "Generating…" : "Download Approval PDF"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PdfPreviewDialog
        open={pdfPreviewOpen}
        onOpenChange={setPdfPreviewOpen}
        title="Standard PDF preview"
        fetchPdf={() => fetchExportBlob("pdf")}
        onDownload={() => handleDownload("pdf")}
        downloading={downloadingPdf}
      />
      <PdfPreviewDialog
        open={approvalPdfPreviewOpen}
        onOpenChange={setApprovalPdfPreviewOpen}
        title="Approval PDF preview"
        fetchPdf={fetchApprovalPdfBlob}
        onDownload={handleDownloadApprovalPdf}
        downloading={downloadingApprovalPdf}
      />
      <DxfPreviewDialog
        open={dxfPreviewOpen}
        onOpenChange={setDxfPreviewOpen}
        fetchDxf={() => fetchExportBlob("dxf")}
        onDownload={() => handleDownload("dxf")}
        downloading={downloadingDxf}
      />

      {/* Download error */}
      {downloadError && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {downloadError}
        </p>
      )}

      {/* Status rail: score breakdown, Vastu, compliance, structural lifecycle,
          approval notice, restored-revision banner — consolidated into one
          collapsible rail so the floor plan tab stays above the fold. */}
      <StatusRail
        score={layout.score}
        vastuEnabled={vastuEnabled}
        compliance={layout.compliance}
        municipality={municipality}
        structStatus={structStatus?.status}
        structChangelog={structStatus?.design?.changelog ?? []}
        approvingStructural={approvingStructural}
        onApproveStructural={handleApproveStructural}
        onRunStructuralDesign={() => setActiveTab("structural")}
        alreadyApprovedNotice={alreadyApprovedNotice}
        restoredRevisionActive={Boolean(restoredData)}
        onClearRestore={handleClearRestore}
      />

      {/* Space utilisation notes */}
      {layout.space_notes && layout.space_notes.length > 0 && (
        <details className="rounded-lg border border-blue-400/30 bg-blue-500/8 p-3 text-sm">
          <summary className="cursor-pointer font-medium text-blue-700 dark:text-blue-400">
            ℹ️ {layout.space_notes.length} space optimisation
            {layout.space_notes.length !== 1 ? "s" : ""} applied
          </summary>
          <ul className="mt-2 list-inside list-disc space-y-1 text-blue-700/80 dark:text-blue-400/80 text-xs">
            {layout.space_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </details>
      )}

      {/* ── Offscreen R3F engine ──────────────────────────────────────────── */}
      {/* Geometric truth that conditions the AI render. Mounted once — the
          FIRST time the user visits the r3f ("Render") or render ("AI
          Render") tab, see plan3dMounted above — then kept mounted offscreen
          for the rest of the session so its PNG can still be captured from
          any other tab. Code-split via next/dynamic so the ~150KB three.js
          bundle never loads for users who never touch either tab.
          Top-down captures are label-annotated (room names + dims, north
          arrow, plot dimensions) so the conditioning image is self-describing
          — this is what gets sent as reference_png; if capture ever fails
          (e.g. font load), reference_png is omitted and the backend falls
          back to a rasterised PDF page (existing behaviour). */}
      <div
        aria-hidden
        style={{
          position: "fixed",
          left: -10000,
          top: 0,
          width: 1280,
          height: 800,
          pointerEvents: "none",
        }}
      >
        {mounted && plan3dMounted && (
          <Plan3DScene
            ref={plan3dApiRef}
            floorPlan={r3fFloorPlan}
            plotWidth={plotWidth}
            plotLength={plotLength}
            roadSide={roadSide}
            view={r3fView}
            annotate={r3fView === "top"}
          />
        )}
      </div>

      {/* Tabs: Floor Plan | Section | BOQ | Compare | Chat | Render | AI Render */}
      {/* Mobile: full-width scrollable tab row; Desktop: w-fit pill group */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TabId)}>
        <TabsList
          variant="line"
          className="w-full justify-start overflow-x-auto scrollbar-none [mask-image:linear-gradient(to_right,black_90%,transparent_100%)] md:w-fit md:[mask-image:none]"
        >
          {tabs.map((tab) => (
            <TabsTrigger key={tab} value={tab} className="min-h-[40px] shrink-0 flex-none px-4">
              {tab === "plan"
                ? "Floor Plan"
                : tab === "section"
                  ? "Section"
                  : tab === "boq"
                    ? "BOQ"
                    : tab === "structural"
                      ? "Structural"
                      : tab === "compare"
                        ? "Compare"
                        : tab === "chat"
                          ? "Chat"
                          : tab === "r3f"
                            ? "Render"
                            : "AI Render"}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {activeTab === "plan" && (
        <PlanTab
          structStatusStatus={structStatus?.status}
          availableFloors={availableFloors}
          floor={floor}
          onFloorChange={setFloor}
          vastuEnabled={vastuEnabled}
          showVastuZones={showVastuZones}
          onToggleVastuZones={() => setShowVastuZones((v) => !v)}
          showFurniture={showFurniture}
          onToggleFurniture={() => setShowFurniture((v) => !v)}
          showElectrical={showElectrical}
          onToggleElectrical={() => setShowElectrical((v) => !v)}
          showPlumbing={showPlumbing}
          onTogglePlumbing={() => setShowPlumbing((v) => !v)}
          annotationMode={annotationMode}
          onToggleAnnotationMode={() => setAnnotationMode((v) => !v)}
          annotationCount={annotationCount}
          planTier={planTier}
          editMode={editMode}
          onToggleEditMode={handleToggleEditMode}
          editHistory={editHistory}
          onUndo={handleUndo}
          onRedo={handleRedo}
          canCheckCompliance={!!session}
          onCheckCompliance={() => {
            const roomsToCheck = editedRooms ?? floorPlan.rooms;
            const currentFloorCode =
              floor === 1 ? "ff" : floor === 2 ? "sf" : floor === -1 ? "basement" : "gf";
            void runComplianceCheck(roomsToCheck, currentFloorCode);
          }}
          onResetRooms={handleResetRooms}
          editSaving={editSaving}
          editedRooms={editedRooms}
          onSaveEditedRooms={(rooms) => void handleSaveEditedRooms(rooms)}
          editSaveError={editSaveError}
          complianceIssues={complianceIssues}
          floorPlan={floorPlan}
          plotWidth={plotWidth}
          plotLength={plotLength}
          roadSide={roadSide}
          plotShape={plotShape}
          plotFrontWidth={plotFrontWidth}
          plotRearWidth={plotRearWidth}
          plotCorners={plotCorners}
          cutoutCorner={cutoutCorner}
          cutoutWidth={cutoutWidth}
          cutoutHeight={cutoutHeight}
          annotationList={annotationList}
          onAnnotationClick={handleAnnotationClick}
          locale={locale}
          onRoomsChange={(rooms) => {
            const currentFloorCode =
              floor === 1 ? "ff" : floor === 2 ? "sf" : floor === -1 ? "basement" : "gf";
            handleRoomsChange(rooms, currentFloorCode);
          }}
          presentTypes={presentTypes}
          typeLabels={TYPE_LABELS}
          swatch={SWATCH}
        />
      )}

      {activeTab === "section" && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            Parametric section through the building. Dimensions are standard for Indian residential
            construction.
          </p>
          <SectionViewSVG
            buildingWidth={plotWidth}
            className="w-full md:max-w-xl rounded-xl border"
            stairTreadCount={layout.ground_floor.drawing?.stair?.tread_count}
          />
          <div className="rounded-lg border bg-muted/40 px-4 py-3 text-xs text-muted-foreground grid grid-cols-1 gap-1 sm:grid-cols-2 md:grid-cols-3">
            <span>Floor height: 3.0 m (each floor)</span>
            <span>Slab thickness: 150 mm (RCC)</span>
            <span>Parapet: 1.0 m above roof</span>
            <span>External wall: 230 mm brick</span>
            <span>Foundation: 600 mm below GL</span>
            <span>Stair: 17R x 175 mm riser</span>
          </div>
        </div>
      )}

      {activeTab === "boq" && (
        <BOQViewer projectId={projectId} layoutId={selectedId} planTier={planTier} />
      )}

      {activeTab === "structural" && (
        <StructuralViewer
          projectId={projectId}
          layoutId={selectedId}
          status={structStatus}
          approving={approvingStructural}
          onApprove={handleApproveStructural}
          onDesignComplete={handleDesignComplete}
        />
      )}

      {activeTab === "compare" && (
        <LayoutCompareView
          layouts={activeData.layouts}
          plotWidth={plotWidth}
          plotLength={plotLength}
          roadSide={roadSide}
          plotShape={plotShape}
          plotFrontWidth={plotFrontWidth}
          plotRearWidth={plotRearWidth}
          plotCorners={plotCorners}
          cutoutCorner={cutoutCorner}
          cutoutWidth={cutoutWidth}
          cutoutHeight={cutoutHeight}
        />
      )}

      {activeTab === "chat" && agentChatEnabled && (
        <ChatTab
          projectId={projectId}
          planTier={planTier}
          layout={layout}
          floor={floor}
          liveLayout={liveLayout}
          plotWidth={plotWidth}
          plotLength={plotLength}
          roadSide={roadSide}
          plotShape={plotShape}
          plotFrontWidth={plotFrontWidth}
          plotRearWidth={plotRearWidth}
          plotCorners={plotCorners}
          cutoutCorner={cutoutCorner}
          cutoutWidth={cutoutWidth}
          cutoutHeight={cutoutHeight}
          locale={locale}
          onLayoutUpdate={(updated) => {
            setLiveLayout(updated);
            invalidateAfterGeometryEdit();
          }}
        />
      )}

      {activeTab === "render" && (
        <RenderTab
          projectId={projectId}
          layoutKey={selectedId}
          planTier={planTier}
          floors={availableFloors.map((f) => ({ label: f.label, index: f.index }))}
          r3fPngs={r3fPngs}
          registerTrigger={(fn) => {
            renderTriggerRef.current = fn;
          }}
        />
      )}

      {activeTab === "r3f" && (
        <R3fTab
          structuralDesigned={
            structStatus?.status === "designed" || structStatus?.status === "designed_with_warnings"
          }
          renderSource={renderSource}
          onRenderSourceChange={handleRenderSourceChange}
          structuralGeometryLoading={structuralGeometryLoading}
          structuralGeometry={structuralGeometry}
          structuralGeometryFallback={structuralGeometryFallback}
          availableFloors={availableFloors}
          floor={floor}
          onFloorChange={setFloor}
          r3fView={r3fView}
          onR3fViewChange={setR3fView}
          r3fPng={r3fPngs[floor]}
          currentFloorLabel={currentFloorEntry.label}
          onRefreshCapture={() => captureR3f()}
          onGenerateAiRender={() => {
            const png = captureR3f();
            setActiveTab("render");
            renderTriggerRef.current(floor, png);
          }}
        />
      )}

      {/* ── Version History panel ────────────────────────────────────────── */}
      <div className="rounded-xl border border-border">
        <button
          type="button"
          onClick={handleHistoryToggle}
          className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/40 transition-colors rounded-xl"
        >
          <span className="flex items-center gap-2">
            <History className="h-4 w-4 text-muted-foreground" />
            Version History
          </span>
          {historyOpen ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </button>

        {historyOpen && (
          <div className="border-t border-border px-4 pb-4 pt-3 flex flex-col gap-3">
            {/* Save snapshot row */}
            <div className="flex items-center gap-2">
              {showSnapshotInput ? (
                <>
                  <input
                    type="text"
                    value={snapshotLabel}
                    onChange={(e) => setSnapshotLabel(e.target.value)}
                    placeholder="Label (optional, e.g. Before plot resize)"
                    className="flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSaveSnapshot();
                      if (e.key === "Escape") setShowSnapshotInput(false);
                    }}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleSaveSnapshot}
                    disabled={savingSnapshot}
                  >
                    {savingSnapshot ? "Saving…" : "Save"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowSnapshotInput(false)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5"
                  onClick={() => setShowSnapshotInput(true)}
                  disabled={!session}
                >
                  <Save className="h-3.5 w-3.5" />
                  Save Snapshot
                </Button>
              )}
            </div>

            {/* Error message */}
            {revisionsError && (
              <p className="text-xs text-destructive rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1.5">
                {revisionsError}
              </p>
            )}

            {/* Revisions list */}
            {revisionsLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-10 rounded-lg" />
                ))}
              </div>
            ) : revisions.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">
                No saved revisions yet. Click "Save Snapshot" to create one, or revisions are
                auto-created when you regenerate layouts.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {revisions.map((rev) => (
                  <li key={rev.id} className="flex items-center justify-between py-2.5 gap-3">
                    <div className="flex flex-col gap-0.5 min-w-0">
                      <span className="text-sm font-medium text-foreground truncate">
                        v{rev.version}
                        {rev.label ? ` — ${rev.label}` : ""}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(rev.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5 h-7 px-2 text-xs"
                        onClick={() => handleRestore(rev.version)}
                        disabled={restoringVersion === rev.version}
                        title="Preview this revision without overwriting current state"
                      >
                        <RotateCcw className="h-3 w-3" />
                        {restoringVersion === rev.version ? "Loading…" : "Restore"}
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <button
                            type="button"
                            className="h-7 w-7 flex items-center justify-center rounded-md border border-border text-muted-foreground hover:text-destructive hover:border-destructive/50 transition-colors text-xs"
                            title="Delete this revision"
                            aria-label={`Delete revision v${rev.version}`}
                          >
                            ×
                          </button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Delete revision v{rev.version}?</AlertDialogTitle>
                            <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={() => void handleDeleteRevision(rev.version)}
                            >
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
