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
  History,
  Link2,
  Lock,
  MessageSquare,
  Pencil,
  RefreshCw,
  RotateCcw,
  Save,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { BOQViewer } from "@/components/boq-viewer";
import { ChatPanel } from "@/components/chat-panel";
import type { Annotation } from "@/components/floor-plan-svg";
import { FloorPlanSVG } from "@/components/floor-plan-svg";
import { LayoutCompareView } from "@/components/layout-compare-view";
import { SectionViewSVG } from "@/components/section-view-svg";
import { ShareWhatsAppButton } from "@/components/share-whatsapp-button";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useSession } from "@/lib/auth-client";
import type {
  ComplianceData,
  FloorPlanData,
  GenerateResponse,
  LayoutData,
  RoomData,
} from "@/lib/layout-types";
import { useLocale } from "@/lib/locale-context";

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

// ── Vastu badge with popover for details ──────────────────────────────────────
function VastuBadge({ compliance }: { compliance: ComplianceData }) {
  const vastuViolations = compliance.violations.filter((v) => v.startsWith("[Vastu]"));
  const vastuWarnings = compliance.warnings.filter((w) => w.startsWith("[Vastu]"));
  const allIssues = [...vastuViolations, ...vastuWarnings];

  let badgeClass: string;
  let label: string;
  if (vastuViolations.length > 0) {
    badgeClass =
      "border-red-500/50 bg-red-500/10 text-red-700 dark:text-red-400 hover:bg-red-500/15";
    label = `${vastuViolations.length} Vastu Violation${vastuViolations.length !== 1 ? "s" : ""}`;
  } else if (vastuWarnings.length > 0) {
    badgeClass =
      "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400 hover:bg-amber-500/15";
    label = `${vastuWarnings.length} Vastu Warning${vastuWarnings.length !== 1 ? "s" : ""}`;
  } else {
    badgeClass =
      "border-green-500/50 bg-green-500/10 text-green-700 dark:text-green-400 hover:bg-green-500/15";
    label = "Vastu Compliant";
  }

  if (allIssues.length === 0) {
    return (
      <span
        className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold ${badgeClass}`}
      >
        {label}
      </span>
    );
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold transition-colors cursor-pointer ${badgeClass}`}
        >
          {label}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 text-sm" align="start">
        <p className="font-semibold mb-2 text-foreground">Vastu Issues</p>
        {vastuViolations.length > 0 && (
          <div className="mb-2">
            <p className="text-xs font-medium text-red-600 dark:text-red-400 mb-1">Violations</p>
            <ul className="space-y-1">
              {vastuViolations.map((v) => (
                <li key={v} className="text-xs text-muted-foreground">
                  {v.replace("[Vastu] ", "")}
                </li>
              ))}
            </ul>
          </div>
        )}
        {vastuWarnings.length > 0 && (
          <div>
            <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-1">Warnings</p>
            <ul className="space-y-1">
              {vastuWarnings.map((w) => (
                <li key={w} className="text-xs text-muted-foreground">
                  {w.replace("[Vastu] ", "")}
                </li>
              ))}
            </ul>
          </div>
        )}
      </PopoverContent>
    </Popover>
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
  numFloors?: number;
  vastuEnabled?: boolean;
  municipality?: string | null;
  shareToken?: string | null;
  initialApproval?: ApprovalInfo;
}

// ── Vastu badge helper ────────────────────────────────────────────────────────
function _VastuBadge({ compliance }: { compliance: ComplianceData }) {
  const vastuViolations = compliance.violations.filter((v) => v.startsWith("[Vastu]"));
  const vastuWarnings = compliance.warnings.filter((w) => w.startsWith("[Vastu]"));
  const allIssues = [...vastuViolations, ...vastuWarnings];

  let badgeClass: string;
  let label: string;
  if (vastuViolations.length > 0) {
    badgeClass =
      "border-red-500/50 bg-red-500/10 text-red-700 dark:text-red-400 hover:bg-red-500/15";
    label = `${vastuViolations.length} Vastu Violation${vastuViolations.length !== 1 ? "s" : ""}`;
  } else if (vastuWarnings.length > 0) {
    badgeClass =
      "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400 hover:bg-amber-500/15";
    label = `${vastuWarnings.length} Vastu Warning${vastuWarnings.length !== 1 ? "s" : ""}`;
  } else {
    badgeClass =
      "border-green-500/50 bg-green-500/10 text-green-700 dark:text-green-400 hover:bg-green-500/15";
    label = "Vastu Compliant";
  }

  if (allIssues.length === 0) {
    return (
      <span
        className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold ${badgeClass}`}
      >
        {label}
      </span>
    );
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold transition-colors cursor-pointer ${badgeClass}`}
        >
          {label}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 text-sm" align="start">
        <p className="font-semibold mb-2 text-foreground">Vastu Issues</p>
        {vastuViolations.length > 0 && (
          <div className="mb-2">
            <p className="text-xs font-medium text-red-600 dark:text-red-400 mb-1">Violations</p>
            <ul className="space-y-1">
              {vastuViolations.map((v) => (
                <li key={v} className="text-xs text-muted-foreground">
                  {v.replace("[Vastu] ", "")}
                </li>
              ))}
            </ul>
          </div>
        )}
        {vastuWarnings.length > 0 && (
          <div>
            <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-1">Warnings</p>
            <ul className="space-y-1">
              {vastuWarnings.map((w) => (
                <li key={w} className="text-xs text-muted-foreground">
                  {w.replace("[Vastu] ", "")}
                </li>
              ))}
            </ul>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
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
  numFloors: _numFloors = 1,
  vastuEnabled = false,
  municipality = null,
  shareToken = null,
  initialApproval,
}: LayoutViewerProps) {
  const { data: session } = useSession();
  const { locale } = useLocale();
  // Use the first layout's actual ID — IDs may be "S1","S2","D" etc, never assume "A"
  const [selectedId, setSelectedId] = useState(() => generateData?.layouts[0]?.id ?? "A");
  const [liveLayout, setLiveLayout] = useState<LayoutData | null>(null);
  const [floor, setFloor] = useState(0);
  const [activeTab, setActiveTab] = useState<"plan" | "section" | "boq" | "chat" | "compare">(
    "plan"
  );
  const [showVastuZones, setShowVastuZones] = useState(false);
  const [showFurniture, setShowFurniture] = useState(false);
  const [showElectrical, setShowElectrical] = useState(false);
  const [showPlumbing, setShowPlumbing] = useState(false);

  // ── Edit mode state ────────────────────────────────────────────────────────
  const [editMode, setEditMode] = useState(false);
  const [editedRooms, setEditedRooms] = useState<RoomData[] | null>(null);
  const [complianceIssues, setComplianceIssues] = useState<Record<string, string[]>>({});
  const [editSaving, setEditSaving] = useState(false);
  const [editSaveError, setEditSaveError] = useState("");
  const complianceDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
  const [downloadError, setDownloadError] = useState("");
  const [shareOpen, setShareOpen] = useState(false);
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
  const [sendForApprovalOpen, setSendForApprovalOpen] = useState(false);
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
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/approval-status`,
        { headers: { "X-User-Id": session.user.id } }
      );
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
          await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/annotations`, {
            method: "PUT",
            headers: { "X-User-Id": session.user.id, "Content-Type": "application/json" },
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
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/annotations`, {
      headers: { "X-User-Id": session.user.id },
    })
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
      setComplianceIssues({});
      setEditSaveError("");
    } else {
      setEditMode(true);
      setEditedRooms(null);
      setComplianceIssues({});
    }
  }

  function handleResetRooms() {
    setEditedRooms(null);
    setComplianceIssues({});
  }

  async function runComplianceCheck(rooms: RoomData[], floorLabel: string): Promise<void> {
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
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/layouts/${selectedId}/compliance-check`,
        {
          method: "POST",
          headers: {
            "X-User-Id": session.user.id,
            "X-Project-Id": projectId,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        }
      );
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
  }

  function handleRoomsChange(rooms: RoomData[], floorCode: string) {
    setEditedRooms(rooms);
    // Debounced compliance check: runs 800ms after last drag
    if (complianceDebounceRef.current) clearTimeout(complianceDebounceRef.current);
    complianceDebounceRef.current = setTimeout(() => {
      void runComplianceCheck(rooms, floorCode);
    }, 800);
  }

  async function handleSaveEditedRooms(rooms: RoomData[]) {
    if (!session) return;
    setEditSaving(true);
    setEditSaveError("");
    try {
      // Persist each modified room via the existing resize endpoint
      for (const room of rooms) {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/rooms/${room.id}/resize`,
          {
            method: "POST",
            headers: {
              "X-User-Id": session.user.id,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ new_width: room.width, new_depth: room.depth }),
          }
        );
        if (!res.ok) {
          const data = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(data?.detail ?? `Save failed (${res.status})`);
        }
      }
      setEditMode(false);
      setEditedRooms(null);
      setComplianceIssues({});
    } catch (err) {
      setEditSaveError(err instanceof Error ? err.message : "Could not save changes");
    } finally {
      setEditSaving(false);
    }
  }

  async function handleSendForApproval() {
    if (!session) return;
    setApprovalShareLoading(true);
    setApprovalShareError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/share`,
        { method: "POST", headers: { "X-User-Id": session.user.id } }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error((data as { detail?: string })?.detail ?? `Failed (${res.status})`);
      }
      const json = await res.json();
      const fullUrl = `${window.location.origin}${json.share_url}`;
      setApprovalShareUrl(fullUrl);
      setSendForApprovalOpen(true);
    } catch (err) {
      setApprovalShareError(err instanceof Error ? err.message : "Could not generate share link");
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
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/revisions`,
        { headers: { "X-User-Id": session.user.id } }
      );
      if (!res.ok) throw new Error(`Failed to load revisions (${res.status})`);
      const data = (await res.json()) as RevisionListItem[];
      setRevisions(data);
    } catch (err) {
      setRevisionsError(err instanceof Error ? err.message : "Could not load revision history");
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
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/revisions`,
        {
          method: "POST",
          headers: {
            "X-User-Id": session.user.id,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ label: snapshotLabel.trim() || null }),
        }
      );
      if (!res.ok) throw new Error(`Failed to save snapshot (${res.status})`);
      setSnapshotLabel("");
      setShowSnapshotInput(false);
      await fetchRevisions();
    } catch (err) {
      setRevisionsError(err instanceof Error ? err.message : "Could not save snapshot");
    } finally {
      setSavingSnapshot(false);
    }
  }

  async function handleRestore(version: number) {
    if (!session) return;
    setRestoringVersion(version);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/revisions/${version}`,
        { headers: { "X-User-Id": session.user.id } }
      );
      if (!res.ok) throw new Error(`Failed to load revision v${version} (${res.status})`);
      const detail = (await res.json()) as { snapshot: GenerateResponse };
      setRestoredData(detail.snapshot);
      setSelectedId(detail.snapshot.layouts[0]?.id ?? selectedId);
      setLiveLayout(null);
      setFloor(0);
    } catch (err) {
      setRevisionsError(err instanceof Error ? err.message : "Could not restore revision");
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
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/revisions/${version}`,
        { method: "DELETE", headers: { "X-User-Id": session.user.id } }
      );
      if (!res.ok) throw new Error(`Failed to delete revision (${res.status})`);
      await fetchRevisions();
    } catch (err) {
      setRevisionsError(err instanceof Error ? err.message : "Could not delete revision");
    }
  }

  async function handleShare() {
    if (!session) return;
    setShareLoading(true);
    setShareError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/share`,
        { method: "POST", headers: { "X-User-Id": session.user.id } }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? `Failed to generate share link (${res.status})`);
      }
      const json = await res.json();
      const fullUrl = `${window.location.origin}${json.share_url}`;
      setShareUrl(fullUrl);
      setShareOpen(true);
    } catch (err) {
      setShareError(err instanceof Error ? err.message : "Could not generate share link");
    } finally {
      setShareLoading(false);
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
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/export/approval-pdf?layout_id=${selectedId}`,
        {
          method: "POST",
          headers: {
            "X-User-Id": session.user.id,
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
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `planforge-approval-${projectId}-layout-${selectedId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setApprovalDialogOpen(false);
    } catch (err) {
      setApprovalPdfError(err instanceof Error ? err.message : "Approval PDF download failed");
    } finally {
      setDownloadingApprovalPdf(false);
    }
  }

  async function handleDownload(format: "pdf" | "dxf") {
    if (!session) return;
    const setter = format === "pdf" ? setDownloadingPdf : setDownloadingDxf;
    setter(true);
    setDownloadError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/export/${format}?layout_id=${selectedId}`,
        { headers: { "X-User-Id": session.user.id } }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? `Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `planforge-layout-${selectedId}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(
        err instanceof Error ? err.message : "Download failed — is the backend running?"
      );
    } finally {
      setter(false);
    }
  }

  if (!generateData) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">
        <p className="font-medium">Layout engine offline</p>
        <p className="mt-1 text-sm">Start the backend server and refresh to see floor plans.</p>
      </div>
    );
  }

  if (generateData.layouts.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">
        <p className="font-medium">No compliant layouts could be generated</p>
        <p className="mt-1 text-sm">
          The plot configuration does not produce any layouts that satisfy the building compliance
          rules. Try increasing the plot size or reducing the setbacks.
        </p>
      </div>
    );
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

  return (
    <div className="flex flex-col gap-6">
      {/* Layout selector + export buttons */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
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
                "rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
                selectedId === l.id
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-transparent hover:bg-muted",
              ].join(" ")}
            >
              Layout {l.id} — {l.name}
              {l.score && <ScoreBadge score={l.score.total} />}
              {vastuEnabled && (
                <span
                  className={[
                    "ml-1 rounded-sm border px-1 py-0.5 text-xs",
                    l.compliance.violations.some((v) => v.startsWith("[Vastu]"))
                      ? "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400"
                      : l.compliance.warnings.some((w) => w.startsWith("[Vastu]"))
                        ? "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                        : "border-green-500/40 bg-green-500/10 text-green-600 dark:text-green-400",
                  ].join(" ")}
                >
                  {l.compliance.violations.some((v) => v.startsWith("[Vastu]"))
                    ? "Vastu ✗"
                    : l.compliance.warnings.some((w) => w.startsWith("[Vastu]"))
                      ? "Vastu ⚠"
                      : "Vastu ✓"}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Export + share buttons */}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            className="border-border text-foreground hover:bg-muted"
            onClick={() => handleDownload("pdf")}
            disabled={downloadingPdf || !session}
          >
            {downloadingPdf ? "…" : "PDF"}
          </Button>
          {planTier === "free" ? (
            <Button
              variant="outline"
              size="sm"
              className="border-border text-foreground hover:bg-muted"
              asChild
              title="Upgrade to Basic for DXF export"
            >
              <Link href="/pricing">
                <Lock className="h-3 w-3 mr-1.5" />
                DXF
              </Link>
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="border-border text-foreground hover:bg-muted"
              onClick={() => handleDownload("dxf")}
              disabled={downloadingDxf || !session}
              title="DXF for AutoCAD / DraftSight"
            >
              {downloadingDxf ? "…" : "DXF"}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="border-border text-foreground hover:bg-muted"
            onClick={() => setApprovalDialogOpen(true)}
            disabled={!session}
            title="Download municipality approval drawing package (CMDA/BBMP/GHMC format)"
          >
            Approval PDF
          </Button>
          <ShareWhatsAppButton projectName={projectName} layoutId={selectedId} />
          <Button
            variant="outline"
            size="sm"
            className="border-border text-foreground hover:bg-muted"
            onClick={handleShare}
            disabled={shareLoading || !session}
            title="Get a read-only share link for your client"
          >
            <Link2 className="h-3 w-3 mr-1.5" />
            {shareLoading ? "…" : "Share"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="border-border text-foreground hover:bg-muted"
            onClick={handleSendForApproval}
            disabled={approvalShareLoading || !session}
            title="Send this plan to client for approval"
          >
            <MessageSquare className="h-3 w-3 mr-1.5" />
            {approvalShareLoading ? "…" : "Send for Approval"}
          </Button>
          {/* Refresh approval status button */}
          <Button
            variant="outline"
            size="sm"
            className="border-border text-muted-foreground hover:bg-muted"
            onClick={fetchApprovalStatus}
            disabled={approvalFetching || !session}
            title="Refresh client approval status"
          >
            {approvalFetching ? "…" : "↻"}
          </Button>
        </div>
      </div>

      {/* Share error */}
      {shareError && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {shareError}
        </p>
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

      {/* Share link dialog */}
      <Dialog open={shareOpen} onOpenChange={setShareOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Share floor plan with client</DialogTitle>
            <DialogDescription>
              Anyone with this link can view the floor plans in read-only mode — no login required.
            </DialogDescription>
          </DialogHeader>
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
              title="Copy link"
            >
              {copied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
          {copied && (
            <p className="text-xs text-green-600 dark:text-green-400">Copied to clipboard!</p>
          )}
          <p className="text-xs text-muted-foreground">
            The link shows all layout options with floor plans, section view, and compliance status.
          </p>
        </DialogContent>
      </Dialog>

      {/* Approval share error */}
      {approvalShareError && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {approvalShareError}
        </p>
      )}

      {/* Send for Approval dialog */}
      <Dialog open={sendForApprovalOpen} onOpenChange={setSendForApprovalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Send for client approval</DialogTitle>
            <DialogDescription>
              Share this link with your client. They can approve the plan or request changes — no
              login needed.
            </DialogDescription>
          </DialogHeader>
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
              title="Copy link"
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
            After sending the link, use the ↻ button in the toolbar to check if the client has
            responded.
          </p>
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
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="apr-owner">Owner Name</Label>
                <Input
                  id="apr-owner"
                  value={approvalForm.owner_name}
                  onChange={(e) => setApprovalForm((f) => ({ ...f, owner_name: e.target.value }))}
                  placeholder="e.g. Rajan Kumar"
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
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="apr-engineer">Engineer / Architect Name</Label>
                <Input
                  id="apr-engineer"
                  value={approvalForm.engineer_name}
                  onChange={(e) =>
                    setApprovalForm((f) => ({ ...f, engineer_name: e.target.value }))
                  }
                  placeholder="e.g. Er. S. Venkatesh"
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
              onClick={handleDownloadApprovalPdf}
              disabled={downloadingApprovalPdf || !session}
            >
              {downloadingApprovalPdf ? "Generating…" : "Download Approval PDF"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Download error */}
      {downloadError && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {downloadError}
        </p>
      )}

      {/* Score breakdown for selected layout */}
      {layout.score && (
        <div className="flex flex-wrap gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs">
          <span className="font-semibold text-foreground">
            Score {layout.score.total.toFixed(0)}/100
          </span>
          <span className="text-muted-foreground">
            Light {layout.score.natural_light.toFixed(0)}
          </span>
          <span className="text-muted-foreground">Adj {layout.score.adjacency.toFixed(0)}</span>
          <span className="text-muted-foreground">AR {layout.score.aspect_ratio.toFixed(0)}</span>
          <span className="text-muted-foreground">Fill {layout.score.circulation.toFixed(0)}</span>
          <span className="text-muted-foreground">Vastu {layout.score.vastu.toFixed(0)}</span>
        </div>
      )}

      {/* Vastu compliance summary (shown only when vastu_enabled) */}
      {vastuEnabled && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-muted/20 px-4 py-3">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Vastu
          </span>
          <VastuBadge compliance={layout.compliance} />
          {layout.score && (
            <span className="text-xs text-muted-foreground">
              Score: {layout.score.vastu.toFixed(0)}/100
            </span>
          )}
        </div>
      )}

      {/* Compliance badge */}
      <div
        className={[
          "flex flex-col gap-1.5 rounded-lg border p-3 text-sm",
          layout.compliance.passed
            ? "border-green-500/40 bg-green-500/8 text-green-700 dark:text-green-400"
            : "border-red-500/40 bg-red-500/8 text-red-700 dark:text-red-400",
        ].join(" ")}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold">
            {layout.compliance.passed ? "✓ Compliance passed" : "✗ Compliance failed"}
          </span>
          {municipality && (
            <span className="text-xs font-normal text-muted-foreground opacity-80">
              Validated against: {municipality}
            </span>
          )}
        </div>

        {layout.compliance.violations.length > 0 && (
          <ul className="list-inside list-disc space-y-0.5 text-red-600 dark:text-red-400">
            {layout.compliance.violations.map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        )}

        {layout.compliance.warnings.length > 0 && (
          <details className="mt-1">
            <summary className="cursor-pointer text-xs text-amber-700 dark:text-amber-400 font-medium">
              {layout.compliance.warnings.length} warning
              {layout.compliance.warnings.length !== 1 ? "s" : ""}
            </summary>
            <ul className="mt-1 list-inside list-disc space-y-0.5 text-amber-700 dark:text-amber-400 text-xs">
              {layout.compliance.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </details>
        )}
      </div>

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

      {/* Tabs: Floor Plan | Section | BOQ | Compare | Chat */}
      <div className="flex gap-1 rounded-xl border border-border bg-muted/40 p-1 w-fit">
        {(["plan", "section", "boq", "compare", "chat"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={[
              "rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
              activeTab === tab
                ? "bg-background text-foreground shadow-sm"
                : "hover:bg-background/50",
            ].join(" ")}
          >
            {tab === "plan"
              ? "Floor Plan"
              : tab === "section"
                ? "Section View"
                : tab === "boq"
                  ? "BOQ"
                  : tab === "compare"
                    ? "Compare"
                    : "Chat"}
          </button>
        ))}
      </div>

      {activeTab === "plan" && (
        <div className="flex flex-col gap-3">
          {/* Dynamic floor toggle */}
          <div className="flex w-fit items-center gap-1 rounded-xl border border-border bg-muted/40 p-1">
            {availableFloors.map((f) => (
              <button
                key={f.index}
                type="button"
                onClick={() => setFloor(f.index)}
                className={[
                  "rounded-lg px-3 py-1 text-sm font-medium transition-colors",
                  floor === f.index
                    ? "bg-background text-foreground shadow-sm"
                    : "hover:bg-background/50",
                ].join(" ")}
              >
                {f.label}
                {f.plan.needs_mech_ventilation && (
                  <span
                    className="ml-1 text-xs text-amber-600"
                    title="Mechanical ventilation required"
                  >
                    ⚠
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Floor plan toolbar: Vastu zones + Furnish + Annotate toggles */}
          <div className="flex flex-wrap gap-2">
            {vastuEnabled && (
              <button
                type="button"
                onClick={() => setShowVastuZones((v) => !v)}
                className={[
                  "flex w-fit items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                  showVastuZones
                    ? "border-orange-500/60 bg-orange-500/10 text-orange-700 dark:text-orange-400"
                    : "border-border bg-transparent text-muted-foreground hover:bg-muted",
                ].join(" ")}
              >
                {showVastuZones ? "Hide Vastu Zones" : "Show Vastu Zones"}
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowFurniture((v) => !v)}
              className={[
                "flex w-fit items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                showFurniture
                  ? "border-blue-500/60 bg-blue-500/10 text-blue-700 dark:text-blue-400"
                  : "border-border bg-transparent text-muted-foreground hover:bg-muted",
              ].join(" ")}
            >
              {showFurniture ? "Hide Furniture" : "Furnish"}
            </button>
            <button
              type="button"
              onClick={() => setShowElectrical((v) => !v)}
              className={[
                "flex w-fit items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                showElectrical
                  ? "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400"
                  : "border-border bg-transparent text-muted-foreground hover:bg-muted",
              ].join(" ")}
            >
              {showElectrical ? "Hide Electrical" : "Electrical"}
            </button>
            <button
              type="button"
              onClick={() => setShowPlumbing((v) => !v)}
              className={[
                "flex w-fit items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                showPlumbing
                  ? "border-blue-500/60 bg-blue-500/10 text-blue-700 dark:text-blue-400"
                  : "border-border bg-transparent text-muted-foreground hover:bg-muted",
              ].join(" ")}
            >
              {showPlumbing ? "Hide Plumbing" : "Plumbing"}
            </button>
            <button
              type="button"
              onClick={() => setAnnotationMode((v) => !v)}
              className={[
                "flex w-fit items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                annotationMode
                  ? "border-yellow-500/60 bg-yellow-500/10 text-yellow-700 dark:text-yellow-400"
                  : "border-border bg-transparent text-muted-foreground hover:bg-muted",
              ].join(" ")}
              title={
                annotationMode
                  ? "Click a room to add/edit a note. Click again to exit."
                  : "Enter annotation mode to attach notes to rooms"
              }
            >
              <MessageSquare className="h-3 w-3" />
              {annotationMode ? "Exit Annotate" : "Annotate"}
              {annotationCount > 0 && (
                <span className="ml-1 rounded-full bg-yellow-500 px-1.5 py-0.5 text-[10px] font-bold text-white leading-none">
                  {annotationCount}
                </span>
              )}
            </button>
            {planTier === "pro" ? (
              <button
                type="button"
                onClick={handleToggleEditMode}
                className={[
                  "flex w-fit items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                  editMode
                    ? "border-blue-600/70 bg-blue-600/15 text-blue-700 dark:text-blue-400"
                    : "border-border bg-transparent text-muted-foreground hover:bg-muted",
                ].join(" ")}
                title={
                  editMode
                    ? "Exit edit mode and discard changes"
                    : "Enter edit mode — drag shared walls to resize rooms"
                }
              >
                {editMode ? <X className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
                {editMode ? "Exit Edit" : "Edit Rooms"}
              </button>
            ) : (
              <Link
                href="/pricing"
                className="flex w-fit items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
                title="Upgrade to Pro to enable manual room editing"
              >
                <Lock className="h-3 w-3" />
                Edit Rooms
              </Link>
            )}
          </div>

          {annotationMode && (
            <p className="text-xs text-yellow-700 dark:text-yellow-400 rounded-lg border border-yellow-500/30 bg-yellow-500/8 px-3 py-1.5">
              Click any room to add or edit a note. Notes persist across sessions and appear in PDF
              exports.
            </p>
          )}

          {editMode && (
            <div className="flex flex-col gap-2">
              <p className="text-xs text-amber-700 dark:text-amber-400 rounded-lg border border-amber-500/30 bg-amber-500/8 px-3 py-1.5 flex items-center gap-1.5">
                <AlertTriangle className="h-3 w-3 shrink-0" />
                Drag shared walls (blue lines) to resize rooms. Changes are not saved automatically.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 text-xs h-7 px-2.5"
                  onClick={() => {
                    const roomsToCheck = editedRooms ?? floorPlan.rooms;
                    const currentFloorCode =
                      floor === 1 ? "ff" : floor === 2 ? "sf" : floor === -1 ? "basement" : "gf";
                    void runComplianceCheck(roomsToCheck, currentFloorCode);
                  }}
                  disabled={!session}
                  title="Check compliance for current room layout"
                >
                  <RefreshCw className="h-3 w-3" />
                  Check Compliance
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 text-xs h-7 px-2.5"
                  onClick={handleResetRooms}
                  title="Restore rooms to the original generated layout"
                >
                  <RotateCcw className="h-3 w-3" />
                  Reset
                </Button>
                <Button
                  size="sm"
                  className="gap-1.5 text-xs h-7 px-2.5 bg-blue-600 text-white hover:bg-blue-700"
                  onClick={() => {
                    const roomsToSave = editedRooms ?? floorPlan.rooms;
                    void handleSaveEditedRooms(roomsToSave);
                  }}
                  disabled={editSaving || !session || !editedRooms}
                  title="Save the edited room layout to the project"
                >
                  <Save className="h-3 w-3" />
                  {editSaving ? "Saving…" : "Save Changes"}
                </Button>
              </div>
              {editSaveError && (
                <p className="text-xs text-destructive rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1.5">
                  {editSaveError}
                </p>
              )}
              {Object.keys(complianceIssues).length > 0 && (
                <p className="text-xs text-red-700 dark:text-red-400 rounded-lg border border-red-500/30 bg-red-500/8 px-3 py-1.5 flex items-center gap-1.5">
                  <AlertTriangle className="h-3 w-3 shrink-0" />
                  {Object.keys(complianceIssues).length} room
                  {Object.keys(complianceIssues).length !== 1 ? "s have" : " has"} compliance issues
                  — highlighted in red.
                </p>
              )}
            </div>
          )}

          <FloorPlanSVG
            floorPlan={floorPlan}
            plotWidth={plotWidth}
            plotLength={plotLength}
            roadSide={roadSide}
            className="max-w-xl rounded-xl border"
            plotShape={plotShape}
            plotFrontWidth={plotFrontWidth}
            plotRearWidth={plotRearWidth}
            plotCorners={plotCorners}
            showVastuZones={showVastuZones}
            showFurniture={showFurniture}
            showElectrical={showElectrical}
            showPlumbing={showPlumbing}
            annotationMode={annotationMode}
            annotations={annotationList}
            onAnnotationClick={handleAnnotationClick}
            locale={locale}
            editMode={editMode}
            onRoomsChange={(rooms) => {
              const currentFloorCode =
                floor === 1 ? "ff" : floor === 2 ? "sf" : floor === -1 ? "basement" : "gf";
              handleRoomsChange(rooms, currentFloorCode);
            }}
            complianceIssues={complianceIssues}
          />

          {/* Room legend */}
          <div className="flex flex-wrap gap-3">
            {presentTypes.map((type) => (
              <div key={type} className="flex items-center gap-1.5">
                <div
                  className={["size-3 rounded-sm border", SWATCH[type] ?? SWATCH.utility].join(" ")}
                />
                <span className="text-xs text-muted-foreground">{TYPE_LABELS[type] ?? type}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === "section" && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            Parametric section through the building. Dimensions are standard for Indian residential
            construction.
          </p>
          <SectionViewSVG buildingWidth={plotWidth} className="max-w-xl rounded-xl border" />
          <div className="rounded-lg border bg-muted/40 px-4 py-3 text-xs text-muted-foreground grid grid-cols-2 gap-1 sm:grid-cols-3">
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
        />
      )}

      {activeTab === "chat" &&
        (planTier === "pro" ? (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Left: live floor plan preview */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">Live Layout Preview</p>
                {liveLayout && (
                  <span className="text-xs text-green-600 dark:text-green-400 font-medium">
                    ● AI updated
                  </span>
                )}
              </div>
              <FloorPlanSVG
                floorPlan={floor === 1 ? layout.first_floor : layout.ground_floor}
                plotWidth={plotWidth}
                plotLength={plotLength}
                roadSide={roadSide}
                className="rounded-xl border"
                plotShape={plotShape}
                plotFrontWidth={plotFrontWidth}
                plotRearWidth={plotRearWidth}
                plotCorners={plotCorners}
                locale={locale}
              />
              <p className="text-xs text-muted-foreground">
                Showing {floor === 1 ? "First" : "Ground"} Floor — switches in the Floor Plan tab
              </p>
            </div>
            {/* Right: chat panel */}
            <ChatPanel
              projectId={projectId}
              currentLayout={layout}
              onLayoutUpdate={(updated) => setLiveLayout(updated)}
            />
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-amber-500/40 bg-amber-500/5 p-8 text-center">
            <Lock className="mx-auto mb-3 h-6 w-6 text-amber-600" />
            <p className="font-semibold text-amber-700 dark:text-amber-400">Pro plan required</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Conversational layout editing with AI is a Pro feature.
            </p>
            <Button asChild className="mt-4" size="sm" variant="outline">
              <Link href="/pricing">Upgrade to Pro</Link>
            </Button>
          </div>
        ))}

      {/* ── Restored revision banner ─────────────────────────────────────── */}
      {restoredData && (
        <div className="flex items-center justify-between rounded-lg border border-amber-500/40 bg-amber-500/8 px-4 py-2.5 text-sm">
          <span className="text-amber-700 dark:text-amber-400 font-medium">
            Viewing a restored revision — this is a preview only, not the current saved state.
          </span>
          <button
            type="button"
            onClick={handleClearRestore}
            className="ml-4 shrink-0 rounded-md border border-amber-500/40 px-2 py-1 text-xs text-amber-700 dark:text-amber-400 hover:bg-amber-500/15 transition-colors"
          >
            Back to current
          </button>
        </div>
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
                  <div key={i} className="h-10 animate-pulse rounded-lg bg-muted" />
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
                      <button
                        type="button"
                        onClick={() => handleDeleteRevision(rev.version)}
                        className="h-7 w-7 flex items-center justify-center rounded-md border border-border text-muted-foreground hover:text-destructive hover:border-destructive/50 transition-colors text-xs"
                        title="Delete this revision"
                        aria-label={`Delete revision v${rev.version}`}
                      >
                        ×
                      </button>
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
