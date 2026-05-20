/**
 * TypeScript mirror of the floorspace.js geometry schema (v0.7.0).
 * See presto_geometry/schemas/floorspace_geometry_schema.json for source.
 */

export type HexColor = string | null;

export interface ProjectConfig {
  units: "ip" | "si" | null;
  language: string | null;
}

export interface ProjectGround {
  floor_offset: number | null;
  azimuth_angle: number | null;
  tilt_slope: number | null;
}

export interface ProjectGrid {
  visible: boolean | null;
  spacing: number | null;
}

export interface ProjectView {
  min_x: number | null;
  min_y: number | null;
  max_x: number | null;
  max_y: number | null;
}

export interface ProjectMap {
  visible: boolean | null;
  latitude: number | null;
  longitude: number | null;
  zoom: number | null;
  elevation: number | null;
  enabled: boolean | null;
  initialized: boolean | null;
  rotation: number | null;
}

export interface Project {
  config: ProjectConfig;
  north_axis: number | null;
  ground: ProjectGround;
  grid: ProjectGrid;
  view: ProjectView;
  map: ProjectMap;
  previous_story: { visible: boolean | null };
  show_import_export: boolean | null;
}

export interface Vertex {
  id: string;
  x: number;
  y: number;
  edge_ids: string[];
}

export interface Edge {
  id: string;
  vertex_ids: [string, string];
  face_ids: string[];
}

export interface Face {
  id: string;
  edge_ids: string[];
  edge_order: (0 | 1)[];
}

export interface Geometry {
  id: string;
  vertices: Vertex[];
  edges: Edge[];
  faces: Face[];
}

export interface DaylightingControlRef {
  daylighting_control_definition_id: string;
  vertex_id: string;
}

export interface Space {
  id: string;
  handle: string | null;
  name: string | null;
  face_id: string | null;
  building_unit_id: string | null;
  thermal_zone_id: string | null;
  space_type_id: string | null;
  construction_set_id: string | null;
  pitched_roof_id: string | null;
  daylighting_controls: DaylightingControlRef[];
  below_floor_plenum_height: number | null;
  floor_to_ceiling_height: number | null;
  above_ceiling_plenum_height: number | null;
  floor_offset: number | null;
  open_to_below: boolean | null;
  building_type_id: string | null;
  template: string | null;
}

export interface Shading {
  id: string;
  handle: string | null;
  name: string | null;
  face_id: string | null;
}

export interface WindowPlacement {
  window_definition_id: string;
  edge_id: string;
  alpha: number | number[] | null;
}

export interface DoorPlacement {
  door_definition_id: string;
  edge_id: string;
  alpha: number;
}

export interface Story {
  id: string;
  handle: string | null;
  name: string | null;
  image_visible: boolean | null;
  below_floor_plenum_height: number | null;
  floor_to_ceiling_height: number | null;
  above_ceiling_plenum_height: number | null;
  multiplier: number | null;
  color: HexColor;
  geometry: Geometry;
  images: unknown[];
  spaces: Space[];
  shading: Shading[];
  windows: WindowPlacement[];
  doors: DoorPlacement[];
}

export interface ThermalZone {
  id: string;
  handle: string | null;
  name: string | null;
  color: HexColor;
}

export interface SpaceType {
  id: string;
  handle: string | null;
  name: string | null;
  color: HexColor;
}

export interface BuildingUnit {
  id: string;
  handle: string | null;
  name: string | null;
  color: HexColor;
}

export interface ConstructionSet {
  id: string;
  handle: string | null;
  name: string | null;
}

export type WindowDefinitionMode =
  | "Single Window"
  | "Repeating Windows"
  | "Window to Wall Ratio";

export interface WindowDefinition {
  id: string;
  name: string | null;
  window_definition_mode: WindowDefinitionMode;
  wwr: number | null;
  sill_height: number | null;
  window_spacing: number | null;
  height: number | null;
  width: number | null;
  window_type: "Fixed" | "Operable";
  overhang_projection_factor: number | null;
  fin_projection_factor: number | null;
  texture?: string | null;
}

export interface DoorDefinition {
  id: string;
  name: string | null;
  height: number;
  width: number;
  door_type: "Door" | "Glass Door" | "Overhead Door";
}

export interface DaylightingControlDefinition {
  id: string;
  name: string | null;
  illuminance_setpoint: number;
  height: number;
}

export interface PitchedRoof {
  id: string;
  name: string | null;
  pitched_roof_type: "Gable" | "Hip" | "Shed";
  pitch: number;
  shed_direction: number | null;
  color: HexColor;
}

export interface Floorplan {
  version: string;
  application: Record<string, unknown>;
  project: Project;
  stories: Story[];
  building_units: BuildingUnit[];
  thermal_zones: ThermalZone[];
  space_types: SpaceType[];
  construction_sets: ConstructionSet[];
  window_definitions: WindowDefinition[];
  door_definitions: DoorDefinition[];
  daylighting_control_definitions: DaylightingControlDefinition[];
  pitched_roofs: PitchedRoof[];
}

export function emptyFloorplan(): Floorplan {
  return {
    version: "0.7.0",
    application: {},
    project: {
      config: { units: "si", language: "EN-US" },
      north_axis: 0,
      ground: { floor_offset: 0, azimuth_angle: 0, tilt_slope: 0 },
      grid: { visible: true, spacing: 0.5 },
      view: { min_x: -25, min_y: -25, max_x: 25, max_y: 25 },
      map: {
        visible: false,
        latitude: 39.7653,
        longitude: -104.9863,
        zoom: 4.5,
        elevation: 0,
        enabled: false,
        initialized: false,
        rotation: 0,
      },
      previous_story: { visible: true },
      show_import_export: true,
    },
    stories: [],
    building_units: [],
    thermal_zones: [],
    space_types: [],
    construction_sets: [],
    window_definitions: [],
    door_definitions: [],
    daylighting_control_definitions: [],
    pitched_roofs: [],
  };
}
