export interface RoomData {
  id: string;
  name: string;
  type: string;
  x: number;
  y: number;
  width: number;
  depth: number;
  area: number;
}

export interface ColumnData {
  x: number;
  y: number;
}

// ── Canonical drawing model (mirrors backend app/engine/cad_elements.py) ───
// Same FloorDrawing.to_dict() payload the PDF/DXF renderers project — see
// app/engine/plan_geometry.py::build_floor_drawing().

export interface WallSegment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  thickness: number;
  kind: "external" | "internal";
}

export interface WallJunction {
  x: number;
  y: number;
  degree: number;
}

export interface Opening {
  kind: "door" | "window" | "ventilator";
  cx: number;
  cy: number;
  width: number;
  is_horizontal: boolean;
  wall_thickness: number;
  hinge_x: number;
  hinge_y: number;
  swing_into_room_id: string;
  swing_cw: boolean;
  is_main?: boolean;
}

export interface LabelBox {
  room_id: string;
  cx: number;
  cy: number;
  lines: string[];
  font_pt: number;
  leader: [number, number] | null;
  rotated: boolean;
}

export interface DimChainEntry {
  start: number;
  end: number;
  text: string;
}

export interface DimChain {
  side: "bottom" | "top" | "left" | "right";
  level: number;
  coord: number;
  entries: DimChainEntry[];
}

export interface StairGeometry {
  room_id: string;
  treads: [number, number, number, number][];
  break_line: [number, number, number, number];
  arrow: [number, number, number, number];
  up_label_xy: [number, number];
  tread_count: number;
}

export interface ColumnMarker {
  cx: number;
  cy: number;
  size: number;
}

export interface FloorDrawing {
  floor: number;
  walls: WallSegment[];
  openings: Opening[];
  columns: ColumnMarker[];
  junctions: WallJunction[];
  dim_chains: DimChain[];
  labels: LabelBox[];
  stair: StairGeometry | null;
  bounds: [number, number, number, number];
  version: number;
}

export interface FloorPlanData {
  floor: number;
  floor_type: string;
  rooms: RoomData[];
  columns: ColumnData[];
  needs_mech_ventilation: boolean;
  // Absent for statically-authored demo data (e.g. the marketing gallery)
  // that never goes through the backend /generate endpoint.
  drawing?: FloorDrawing | null;
}

export interface ComplianceData {
  passed: boolean;
  violations: string[];
  warnings: string[];
}

export interface LayoutScoreData {
  total: number;
  natural_light: number;
  adjacency: number;
  aspect_ratio: number;
  circulation: number;
  vastu: number;
}

export interface LayoutData {
  id: string;
  name: string;
  compliance: ComplianceData;
  ground_floor: FloorPlanData;
  first_floor: FloorPlanData;
  second_floor: FloorPlanData | null;
  basement_floor: FloorPlanData | null;
  score: LayoutScoreData | null;
  space_notes: string[];
}

export interface GenerateResponse {
  project_id: string;
  layouts: LayoutData[];
}

export interface BOQItem {
  item: string;
  description: string;
  quantity: number;
  unit: string;
  rate: number;
  amount: number;
  // Stage 2 provenance — "designed" once backed by an IS-code structural
  // design, "estimated" otherwise. Optional: older/pre-Stage-2 backend
  // responses won't send it, so callers must treat absence as "estimated".
  basis?: "designed" | "estimated" | null;
}

export interface BOQResponse {
  project_name: string;
  layout_id: string;
  city: string;
  rates_note: string;
  total_cost: number;
  generic_total_cost: number | null;
  cost_difference: number | null;
  items: BOQItem[];
  // Stage 2 provenance — optional, see BOQItem.basis.
  preliminary?: boolean | null;
  basis_summary?: string | null;
}

export interface CustomRoomSpec {
  type: string;
  name?: string;
  min_area_sqm?: number;
  floor_preference?: "basement" | "stilt" | "gf" | "ff" | "sf" | "either";
  mandatory?: boolean;
}

export const CITIES = [
  { value: "other", label: "Other / NBC Defaults" },
  { value: "bangalore", label: "Bangalore (BBMP)" },
  { value: "chennai", label: "Chennai (CMDA)" },
  { value: "delhi", label: "Delhi (DDA/MCD)" },
  { value: "hyderabad", label: "Hyderabad (GHMC)" },
  { value: "mumbai", label: "Mumbai (MCGM)" },
  { value: "pune", label: "Pune (PMC)" },
] as const;

export type CityValue = (typeof CITIES)[number]["value"];

// Municipality options that map to per-city JSON rule files in the backend
export const MUNICIPALITIES = [
  { value: "", label: "Generic (NBC)" },
  { value: "Chennai (CMDA)", label: "Chennai (CMDA)" },
  { value: "Bangalore (BBMP)", label: "Bangalore (BBMP)" },
  { value: "Hyderabad (GHMC)", label: "Hyderabad (GHMC)" },
  { value: "Pune (PMC)", label: "Pune (PMC)" },
  { value: "Mumbai (MCGM)", label: "Mumbai (MCGM)" },
  { value: "Other", label: "Other (specify below)" },
] as const;

export type MunicipalityValue = (typeof MUNICIPALITIES)[number]["value"];

// All known room types
export const ROOM_TYPES = [
  { value: "living", label: "Living Room" },
  { value: "bedroom", label: "Bedroom" },
  { value: "master_bedroom", label: "Master Bedroom" },
  { value: "kitchen", label: "Kitchen" },
  { value: "toilet", label: "Bathroom (WC + Shower)" },
  { value: "wc_only", label: "WC Only (No Shower)" },
  { value: "bathroom_master", label: "Master Bathroom (En-suite)" },
  { value: "dining", label: "Dining Room" },
  { value: "staircase", label: "Staircase" },
  { value: "parking", label: "Parking (Generic)" },
  { value: "parking_4w", label: "Car Parking (4-Wheeler)" },
  { value: "parking_2w", label: "2-Wheeler Parking" },
  { value: "servant_quarter", label: "Servant Quarter" },
  { value: "gym", label: "Home Gym" },
  { value: "home_office", label: "Home Office" },
  { value: "store_room", label: "Store Room" },
  { value: "garage", label: "Garage" },
  { value: "utility", label: "Utility" },
  { value: "passage", label: "Passage / Corridor" },
  { value: "pooja", label: "Pooja Room" },
  { value: "study", label: "Study" },
  { value: "balcony", label: "Balcony" },
] as const;

export type RoomTypeValue = (typeof ROOM_TYPES)[number]["value"];
