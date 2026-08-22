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
  /** Deterministic topology-derived id (payload v2; absent in stored v1). */
  id?: string;
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
  /** Instance identity: "<host wall id>#<offset along it>" (payload v2). */
  id?: string;
  /** IS 962 schedule mark — class label shared by same-size openings (payload v2). */
  mark?: string;
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

/** Room-relative drawn primitive of a furniture fixture (payload v2, T33). */
export interface FixtureShape {
  kind: "rect" | "circle" | "arc" | "line";
  x: number;
  y: number;
  width: number;
  depth: number;
  radius: number;
  start_deg: number;
  end_deg: number;
  x2: number;
  y2: number;
  dashed: boolean;
}

/** One furniture item in a room — room-relative shapes (payload v2, T33). */
export interface Fixture {
  kind: string;
  room_id: string;
  shapes: FixtureShape[];
}

/** Closed, possibly holed polygon of site ground (payload v2, T32). */
export interface SitePolygon {
  exterior: [number, number][];
  holes: [number, number][][];
}

/** Compound wall/gate/ground hatches shared by every renderer (payload v2, T32). */
export interface SiteContext {
  compound_wall_segments: [number, number, number, number][];
  gate_posts: [number, number][];
  gate_cx: number | null;
  setback_margin: SitePolygon[];
  open_terrace: SitePolygon[];
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
  /** Site entities — absent in payloads from before Task 32. */
  site?: SiteContext | null;
  /** Canonical furniture fixtures — absent in payloads from before Task 33. */
  fixtures?: Fixture[];
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
  { value: "wardrobe", label: "Wardrobe" },
  { value: "garage", label: "Garage" },
  { value: "utility", label: "Utility" },
  { value: "passage", label: "Passage / Corridor" },
  { value: "foyer", label: "Foyer" },
  { value: "pooja", label: "Pooja Room" },
  { value: "study", label: "Study" },
  { value: "balcony", label: "Balcony" },
  { value: "courtyard", label: "Courtyard" },
  { value: "terrace", label: "Terrace" },
  { value: "garden", label: "Garden" },
  { value: "verandah", label: "Verandah" },
  { value: "seating", label: "Seating" },
  { value: "open_to_sky", label: "Open to Sky" },
  { value: "duct", label: "Duct" },
  { value: "washbasin_nook", label: "Wash Basin" },
] as const;

export type RoomTypeValue = (typeof ROOM_TYPES)[number]["value"];
