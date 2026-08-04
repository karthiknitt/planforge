"use client";

import {
  AlertTriangle,
  Lock,
  MessageSquare,
  Pencil,
  Redo2,
  RefreshCw,
  RotateCcw,
  Save,
  Settings2,
  Undo2,
  X,
} from "lucide-react";
import Link from "next/link";

import type { Annotation } from "@/components/floor-plan-svg";
import { FloorPlanSVG } from "@/components/floor-plan-svg";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { canRedo, canUndo, type History as EditHistory } from "@/lib/edit-history";
import type { FloorPlanData, RoomData } from "@/lib/layout-types";
import type { Locale } from "@/lib/locale-context";
import { tierAtLeast } from "@/lib/plan";
import { isPreliminaryStatus } from "@/lib/structural-status";

interface FloorEntry {
  label: string;
  index: number;
  plan: FloorPlanData;
}

export function PlanTab({
  structStatusStatus,
  availableFloors,
  floor,
  onFloorChange,
  vastuEnabled,
  showVastuZones,
  onToggleVastuZones,
  showFurniture,
  onToggleFurniture,
  showElectrical,
  onToggleElectrical,
  showPlumbing,
  onTogglePlumbing,
  annotationMode,
  onToggleAnnotationMode,
  annotationCount,
  planTier,
  editMode,
  onToggleEditMode,
  editHistory,
  onUndo,
  onRedo,
  canCheckCompliance,
  onCheckCompliance,
  onResetRooms,
  editSaving,
  editedRooms,
  onSaveEditedRooms,
  editSaveError,
  complianceIssues,
  floorPlan,
  plotWidth,
  plotLength,
  roadSide,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
  plotCorners,
  cutoutCorner,
  cutoutWidth,
  cutoutHeight,
  annotationList,
  onAnnotationClick,
  locale,
  onRoomsChange,
  presentTypes,
  typeLabels,
  swatch,
}: {
  structStatusStatus?: string;
  availableFloors: FloorEntry[];
  floor: number;
  onFloorChange: (floor: number) => void;
  vastuEnabled: boolean;
  showVastuZones: boolean;
  onToggleVastuZones: () => void;
  showFurniture: boolean;
  onToggleFurniture: () => void;
  showElectrical: boolean;
  onToggleElectrical: () => void;
  showPlumbing: boolean;
  onTogglePlumbing: () => void;
  annotationMode: boolean;
  onToggleAnnotationMode: () => void;
  annotationCount: number;
  planTier: string;
  editMode: boolean;
  onToggleEditMode: () => void;
  editHistory: EditHistory<RoomData[]> | null;
  onUndo: () => void;
  onRedo: () => void;
  canCheckCompliance: boolean;
  onCheckCompliance: () => void;
  onResetRooms: () => void;
  editSaving: boolean;
  editedRooms: RoomData[] | null;
  onSaveEditedRooms: (rooms: RoomData[]) => void;
  editSaveError: string;
  complianceIssues: Record<string, string[]>;
  floorPlan: FloorPlanData;
  plotWidth: number;
  plotLength: number;
  roadSide?: string;
  plotShape?: string;
  plotFrontWidth?: number;
  plotRearWidth?: number;
  plotCorners?: [number, number][];
  cutoutCorner?: string;
  cutoutWidth?: number;
  cutoutHeight?: number;
  annotationList: Annotation[];
  onAnnotationClick: (roomId: string, roomName: string, x: number, y: number) => void;
  locale: Locale;
  onRoomsChange: (rooms: RoomData[]) => void;
  presentTypes: string[];
  typeLabels: Record<string, string>;
  swatch: Record<string, string>;
}) {
  return (
    <div className="flex flex-col gap-3">
      {isPreliminaryStatus(structStatusStatus) && (
        <output className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-700 dark:text-amber-400">
          PRELIMINARY — for planning only, not for construction
        </output>
      )}
      {/* Dynamic floor toggle + mobile Options sheet trigger side-by-side */}
      <div className="flex items-center gap-2">
        {/* Floor toggle */}
        <Tabs
          value={String(floor)}
          onValueChange={(v) => onFloorChange(Number(v))}
          className="flex-1 min-w-0"
        >
          <TabsList
            variant="line"
            className="w-full overflow-x-auto scrollbar-none [mask-image:linear-gradient(to_right,black_90%,transparent_100%)]"
          >
            {availableFloors.map((f) => (
              <TabsTrigger
                key={f.index}
                value={String(f.index)}
                className="min-h-[40px] shrink-0 flex-none px-3"
              >
                {f.label}
                {f.plan.needs_mech_ventilation && (
                  <AlertTriangle
                    className="ml-1 h-3 w-3 text-amber-600 shrink-0"
                    aria-hidden="true"
                  />
                )}
                {f.plan.needs_mech_ventilation && (
                  <span className="sr-only">Mechanical ventilation required</span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {/* Mobile: Options Sheet trigger — visible on < md */}
        <Sheet>
          <SheetTrigger asChild>
            <button
              type="button"
              className="md:hidden flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border bg-muted/40 text-muted-foreground hover:bg-muted transition-colors"
              aria-label="View options"
            >
              <Settings2 className="h-4 w-4" />
            </button>
          </SheetTrigger>
          <SheetContent
            side="bottom"
            className="h-auto max-h-[70vh] overflow-y-auto rounded-t-2xl px-4 pt-4 pb-8"
          >
            <p className="text-sm font-semibold text-foreground mb-4">View Options</p>
            {/* Same toggles, listed vertically for mobile */}
            <div className="flex flex-col gap-2">
              {vastuEnabled && (
                <button
                  type="button"
                  onClick={onToggleVastuZones}
                  className={[
                    "flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-medium transition-colors min-h-[44px]",
                    showVastuZones
                      ? "border-orange-500/60 bg-orange-500/10 text-orange-700 dark:text-orange-400"
                      : "border-border bg-transparent text-muted-foreground",
                  ].join(" ")}
                >
                  {showVastuZones ? "Hide Vastu Zones" : "Show Vastu Zones"}
                </button>
              )}
              <button
                type="button"
                onClick={onToggleFurniture}
                className={[
                  "flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-medium transition-colors min-h-[44px]",
                  showFurniture
                    ? "border-blue-500/60 bg-blue-500/10 text-blue-700 dark:text-blue-400"
                    : "border-border bg-transparent text-muted-foreground",
                ].join(" ")}
              >
                {showFurniture ? "Hide Furniture" : "Show Furniture"}
              </button>
              <button
                type="button"
                onClick={onToggleElectrical}
                className={[
                  "flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-medium transition-colors min-h-[44px]",
                  showElectrical
                    ? "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400"
                    : "border-border bg-transparent text-muted-foreground",
                ].join(" ")}
              >
                {showElectrical ? "Hide Electrical" : "Show Electrical"}
              </button>
              <button
                type="button"
                onClick={onTogglePlumbing}
                className={[
                  "flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-medium transition-colors min-h-[44px]",
                  showPlumbing
                    ? "border-blue-500/60 bg-blue-500/10 text-blue-700 dark:text-blue-400"
                    : "border-border bg-transparent text-muted-foreground",
                ].join(" ")}
              >
                {showPlumbing ? "Hide Plumbing" : "Show Plumbing"}
              </button>
              <button
                type="button"
                onClick={onToggleAnnotationMode}
                className={[
                  "flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-medium transition-colors min-h-[44px]",
                  annotationMode
                    ? "border-yellow-500/60 bg-yellow-500/10 text-yellow-700 dark:text-yellow-400"
                    : "border-border bg-transparent text-muted-foreground",
                ].join(" ")}
              >
                <MessageSquare className="h-4 w-4" />
                {annotationMode ? "Exit Annotate" : "Annotate"}
                {annotationCount > 0 && (
                  <span className="ml-1 rounded-full bg-yellow-500 px-1.5 py-0.5 text-[10px] font-bold text-white leading-none">
                    {annotationCount}
                  </span>
                )}
              </button>
              {tierAtLeast(planTier, "pro") ? (
                <button
                  type="button"
                  onClick={onToggleEditMode}
                  className={[
                    "flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-medium transition-colors min-h-[44px]",
                    editMode
                      ? "border-blue-600/70 bg-blue-600/15 text-blue-700 dark:text-blue-400"
                      : "border-border bg-transparent text-muted-foreground",
                  ].join(" ")}
                >
                  {editMode ? <X className="h-4 w-4" /> : <Pencil className="h-4 w-4" />}
                  {editMode ? "Exit Edit Mode" : "Edit Rooms"}
                </button>
              ) : (
                <Button
                  asChild
                  variant="outline"
                  className="flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium min-h-[44px]"
                >
                  <Link href="/pricing">
                    <Lock className="h-4 w-4" />
                    Edit Rooms (Pro)
                  </Link>
                </Button>
              )}
            </div>
          </SheetContent>
        </Sheet>
      </div>

      {/* Floor plan toolbar: visible on desktop, hidden on mobile (moved to sheet above) */}
      <div className="hidden md:flex flex-wrap gap-2">
        {vastuEnabled && (
          <button
            type="button"
            onClick={onToggleVastuZones}
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
          onClick={onToggleFurniture}
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
          onClick={onToggleElectrical}
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
          onClick={onTogglePlumbing}
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
          onClick={onToggleAnnotationMode}
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
        {tierAtLeast(planTier, "pro") ? (
          <button
            type="button"
            onClick={onToggleEditMode}
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
          <Button
            asChild
            variant="outline"
            size="sm"
            className="w-fit gap-1.5 text-xs"
            title="Upgrade to Pro to enable manual room editing"
          >
            <Link href="/pricing">
              <Lock className="h-3 w-3" />
              Edit Rooms
            </Link>
          </Button>
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
              variant="ghost"
              className="gap-1.5 text-xs h-7 px-2.5"
              onClick={onUndo}
              disabled={!editHistory || !canUndo(editHistory)}
              title="Undo (Ctrl/Cmd+Z)"
            >
              <Undo2 className="h-3 w-3" />
              Undo
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="gap-1.5 text-xs h-7 px-2.5"
              onClick={onRedo}
              disabled={!editHistory || !canRedo(editHistory)}
              title="Redo (Ctrl/Cmd+Shift+Z)"
            >
              <Redo2 className="h-3 w-3" />
              Redo
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs h-7 px-2.5"
              onClick={onCheckCompliance}
              disabled={!canCheckCompliance}
              title="Check compliance for current room layout"
            >
              <RefreshCw className="h-3 w-3" />
              Check Compliance
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs h-7 px-2.5"
              onClick={onResetRooms}
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
                onSaveEditedRooms(roomsToSave);
              }}
              disabled={editSaving || !editedRooms}
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
              {Object.keys(complianceIssues).length !== 1 ? "s have" : " has"} compliance issues —
              highlighted in red.
            </p>
          )}
        </div>
      )}

      <FloorPlanSVG
        floorPlan={editMode ? { ...floorPlan, rooms: editedRooms ?? floorPlan.rooms } : floorPlan}
        plotWidth={plotWidth}
        plotLength={plotLength}
        roadSide={roadSide}
        className="w-full md:max-w-xl rounded-xl border"
        plotShape={plotShape}
        plotFrontWidth={plotFrontWidth}
        plotRearWidth={plotRearWidth}
        plotCorners={plotCorners}
        cutoutCorner={cutoutCorner}
        cutoutWidth={cutoutWidth}
        cutoutHeight={cutoutHeight}
        showVastuZones={showVastuZones}
        showFurniture={showFurniture}
        showElectrical={showElectrical}
        showPlumbing={showPlumbing}
        annotationMode={annotationMode}
        annotations={annotationList}
        onAnnotationClick={onAnnotationClick}
        locale={locale}
        editMode={editMode}
        onRoomsChange={onRoomsChange}
        complianceIssues={complianceIssues}
      />

      {/* Room legend */}
      <div className="flex flex-wrap gap-3">
        {presentTypes.map((type) => (
          <div key={type} className="flex items-center gap-1.5">
            <div
              className={["size-3 rounded-sm border", swatch[type] ?? swatch.utility].join(" ")}
            />
            <span className="text-xs text-muted-foreground">{typeLabels[type] ?? type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
