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
  rooms: RoomData[];
  columns: ColumnData[];
}

export interface ComplianceData {
  passed: boolean;
  violations: string[];
  warnings: string[];
}

export interface LayoutData {
  id: string;
  name: string;
  compliance: ComplianceData;
  ground_floor: FloorPlanData;
  first_floor: FloorPlanData;
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

export const CITIES = [
  { value: "other", label: "Other / NBC Defaults" },
  { value: "bangalore", label: "Bangalore (BBMP)" },
  { value: "chennai", label: "Chennai (CMDA)" },
  { value: "delhi", label: "Delhi (DDA/MCD)" },
  { value: "hyderabad", label: "Hyderabad (GHMC)" },
  { value: "pune", label: "Pune (PMC)" },
] as const;

export type CityValue = (typeof CITIES)[number]["value"];
