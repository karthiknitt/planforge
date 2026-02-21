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

export interface FloorPlanData {
  floor: number;
  floor_type: string;
  rooms: RoomData[];
  columns: ColumnData[];
  needs_mech_ventilation: boolean;
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
}

export interface BOQResponse {
  project_name: string;
  layout_id: string;
  items: BOQItem[];
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
  { value: "pune", label: "Pune (PMC)" },
] as const;

export type CityValue = (typeof CITIES)[number]["value"];

// All known room types
export const ROOM_TYPES = [
  { value: "living", label: "Living Room" },
  { value: "bedroom", label: "Bedroom" },
  { value: "master_bedroom", label: "Master Bedroom" },
  { value: "kitchen", label: "Kitchen" },
  { value: "toilet", label: "Toilet / Bathroom" },
  { value: "dining", label: "Dining Room" },
  { value: "staircase", label: "Staircase" },
  { value: "parking", label: "Parking" },
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
