"use client";

import { OrbitControls } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from "react";
import type { FloorPlanData, Opening, RoomData, WallSegment } from "@/lib/layout-types";

export interface Plan3DHandle {
  /** Render the current 3D view to a PNG data URL, or null on failure. */
  capture: () => string | null;
}

interface Plan3DSceneProps {
  floorPlan: FloorPlanData;
  plotWidth: number;
  plotLength: number;
  roadSide?: string;
  floorHeight?: number;
  className?: string;
}

// Muted per-room floor tints (conditioning hint, not the final look).
const FLOOR_TINT: Record<string, string> = {
  living: "#d9c27a",
  bedroom: "#b9a4e0",
  master_bedroom: "#c9a8e8",
  kitchen: "#9bd1a6",
  toilet: "#8fc7e8",
  wc_only: "#8fc7e8",
  bathroom_master: "#8fb6e8",
  staircase: "#c2c8d0",
  parking: "#d3d6da",
  parking_4w: "#c2c6cc",
  parking_2w: "#cfcac4",
  utility: "#d3d6da",
  pooja: "#e6b98a",
  study: "#a9d8b4",
  balcony: "#a9d2e8",
  dining: "#d9c97a",
  servant_quarter: "#e6b98a",
  home_office: "#a9d8b4",
  gym: "#e6a9b4",
  store_room: "#d3d6da",
  garage: "#a9d2e8",
  passage: "#c2c8d0",
};

function floorTint(type: string): string {
  return FLOOR_TINT[type] ?? "#d3d6da";
}

interface Seg {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  thickness: number;
  kind: "external" | "internal";
}

/** Fallback wall set when a layout has no canonical drawing (demo data). */
function wallsFromRooms(rooms: RoomData[]): Seg[] {
  const out: Seg[] = [];
  for (const r of rooms) {
    const t = 0.115;
    out.push({ x1: r.x, y1: r.y, x2: r.x + r.width, y2: r.y, thickness: t, kind: "internal" });
    out.push({
      x1: r.x + r.width,
      y1: r.y,
      x2: r.x + r.width,
      y2: r.y + r.depth,
      thickness: t,
      kind: "internal",
    });
    out.push({
      x1: r.x + r.width,
      y1: r.y + r.depth,
      x2: r.x,
      y2: r.y + r.depth,
      thickness: t,
      kind: "internal",
    });
    out.push({ x1: r.x, y1: r.y + r.depth, x2: r.x, y2: r.y, thickness: t, kind: "internal" });
  }
  return out;
}

function SceneContents({
  floorPlan,
  plotWidth,
  plotLength,
  floorHeight,
}: {
  floorPlan: FloorPlanData;
  plotWidth: number;
  plotLength: number;
  floorHeight: number;
}) {
  const cx = plotWidth / 2;
  const cy = plotLength / 2;
  const worldX = (x: number) => x - cx;
  const worldZ = (y: number) => cy - y;

  const walls: Seg[] = floorPlan.drawing?.walls?.length
    ? floorPlan.drawing.walls.map((w: WallSegment) => ({
        x1: w.x1,
        y1: w.y1,
        x2: w.x2,
        y2: w.y2,
        thickness: w.thickness,
        kind: w.kind,
      }))
    : wallsFromRooms(floorPlan.rooms);

  return (
    <group>
      <ambientLight intensity={0.75} />
      <hemisphereLight args={["#ffffff", "#b9bdc4", 0.6]} />
      <directionalLight position={[plotWidth, plotLength * 1.4, plotWidth * 0.8]} intensity={1.1} />

      {/* Plot ground slab */}
      <mesh position={[0, -0.05, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[plotWidth, plotLength]} />
        <meshStandardMaterial color="#e5e7eb" />
      </mesh>

      {/* Per-room floor pads */}
      {floorPlan.rooms.map((r: RoomData) => (
        <mesh
          key={r.id}
          position={[worldX(r.x + r.width / 2), 0.01, worldZ(r.y + r.depth / 2)]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[r.width - 0.02, r.depth - 0.02]} />
          <meshStandardMaterial color={floorTint(r.type)} />
        </mesh>
      ))}

      {/* Walls — extruded boxes aligned to each segment */}
      {walls.map((w) => {
        const dx = w.x2 - w.x1;
        const dy = w.y2 - w.y1;
        const len = Math.hypot(dx, dy);
        if (len < 1e-3) return null;
        const midX = worldX((w.x1 + w.x2) / 2);
        const midZ = worldZ((w.y1 + w.y2) / 2);
        const rotY = Math.atan2(dy, dx);
        const color = w.kind === "external" ? "#cfcfcf" : "#e2e2e2";
        const key = `w${w.x1.toFixed(2)}_${w.y1.toFixed(2)}_${w.x2.toFixed(2)}_${w.y2.toFixed(2)}`;
        return (
          <mesh key={key} position={[midX, floorHeight / 2, midZ]} rotation={[0, rotY, 0]}>
            <boxGeometry args={[len, floorHeight, w.thickness]} />
            <meshStandardMaterial color={color} />
          </mesh>
        );
      })}

      {/* Openings — coloured markers on the walls (door=wood, window=glass) */}
      {(floorPlan.drawing?.openings ?? []).map((o: Opening) => {
        const wood = o.kind === "door";
        const w = o.width;
        const h = floorHeight * 0.85;
        const t = o.wall_thickness || 0.12;
        const pos: [number, number, number] = [worldX(o.cx), h / 2, worldZ(o.cy)];
        const args: [number, number, number] = o.is_horizontal
          ? [w, h, t + 0.04]
          : [t + 0.04, h, w];
        const key = `o${o.cx.toFixed(2)}_${o.cy.toFixed(2)}_${o.kind}`;
        return (
          <mesh key={key} position={pos}>
            <boxGeometry args={args} />
            <meshStandardMaterial
              color={wood ? "#7c5a36" : "#9ec9e8"}
              transparent
              opacity={wood ? 0.95 : 0.7}
            />
          </mesh>
        );
      })}
    </group>
  );
}

function CaptureRegistrar({ register }: { register: (fn: () => string | null) => void }) {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const camera = useThree((s) => s.camera);
  useEffect(() => {
    register(() => {
      gl.render(scene, camera);
      return gl.domElement.toDataURL("image/png");
    });
  }, [gl, scene, camera, register]);
  return null;
}

export const Plan3DScene = forwardRef<Plan3DHandle, Plan3DSceneProps>(function Plan3DScene(
  { floorPlan, plotWidth, plotLength, roadSide: _roadSide, floorHeight = 3.0, className },
  ref
) {
  const captureImpl = useRef<() => string | null>(() => null);
  const register = useCallback((fn: () => string | null) => {
    captureImpl.current = fn;
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      capture: () => {
        try {
          return captureImpl.current();
        } catch {
          return null;
        }
      },
    }),
    []
  );

  const span = Math.max(plotWidth, plotLength);
  const camDist = span * 1.15;
  const camPos: [number, number, number] = [camDist, camDist * 0.85, camDist];

  return (
    <div className={className} style={{ width: "100%", height: "100%" }}>
      <Canvas
        gl={{ preserveDrawingBuffer: true, antialias: true }}
        camera={{ position: camPos, fov: 45, up: [0, 1, 0] }}
        dpr={[1, 2]}
        style={{ width: "100%", height: "100%" }}
      >
        <color attach="background" args={["#f3f4f6"]} />
        <SceneContents
          floorPlan={floorPlan}
          plotWidth={plotWidth}
          plotLength={plotLength}
          floorHeight={floorHeight}
        />
        <OrbitControls target={[0, 0, 0]} makeDefault enablePan={false} />
        <CaptureRegistrar register={register} />
      </Canvas>
    </div>
  );
});
