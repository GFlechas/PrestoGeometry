import * as THREE from "three";
import type {
  DoorDefinition,
  Edge,
  Floorplan,
  Story,
  Vertex,
  WindowDefinition,
} from "../schema/types";
import { faceRing } from "../drawing/geometryOps";
import { buildWallShape, type Hole } from "./wallShape";

const FLOOR_THICKNESS = 0.05;
const WALL_THICKNESS = 0.1;

export interface SceneStoryInstance {
  storyId: string;
  baseZ: number;
  color: string;
  height: number;
  /** Floor slab geometries (one per Face). */
  slabs: { geometry: THREE.BufferGeometry; faceId: string }[];
  /** Wall meshes (one per unique Edge that belongs to at least one Face). */
  walls: {
    edgeId: string;
    geometry: THREE.BufferGeometry;
    /** Position and rotation to place the local-extruded shape into world coords. */
    position: [number, number, number];
    rotationY: number;
  }[];
  /** Panel meshes for windows/doors (filled into the holes). */
  panels: {
    geometry: THREE.BufferGeometry;
    position: [number, number, number];
    rotationY: number;
    kind: "window" | "door";
  }[];
}

export interface SceneBuildResult {
  instances: SceneStoryInstance[];
  bounds: THREE.Box3;
}

function ringFromFace(story: Story, faceId: string): { x: number; y: number }[] {
  const face = story.geometry.faces.find((f) => f.id === faceId);
  if (!face) return [];
  return faceRing(story.geometry, face).map(({ x, y }) => ({ x, y }));
}

function slabGeometry(ring: { x: number; y: number }[]): THREE.BufferGeometry | null {
  if (ring.length < 3) return null;
  const shape = new THREE.Shape();
  shape.moveTo(ring[0].x, ring[0].y);
  for (let i = 1; i < ring.length; i++) shape.lineTo(ring[i].x, ring[i].y);
  shape.lineTo(ring[0].x, ring[0].y);
  const geom = new THREE.ExtrudeGeometry(shape, {
    depth: FLOOR_THICKNESS,
    bevelEnabled: false,
  });
  geom.rotateX(-Math.PI / 2);
  geom.translate(0, FLOOR_THICKNESS, 0);
  return geom;
}

function holesForEdge(
  story: Story,
  edge: Edge,
  windowDefs: WindowDefinition[],
  doorDefs: DoorDefinition[],
): Hole[] {
  const a = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[0]);
  const b = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[1]);
  if (!a || !b) return [];
  const length = Math.hypot(b.x - a.x, b.y - a.y);

  const holes: Hole[] = [];
  for (const wp of story.windows) {
    if (wp.edge_id !== edge.id) continue;
    const def = windowDefs.find((d) => d.id === wp.window_definition_id);
    if (!def) continue;
    const alpha = typeof wp.alpha === "number" ? wp.alpha : 0.5;
    holes.push({
      centerS: alpha * length,
      width: def.width ?? 1,
      height: def.height ?? 1,
      bottom: def.sill_height ?? 0.9,
      kind: "window",
    });
  }
  for (const dp of story.doors) {
    const def = doorDefs.find((d) => d.id === dp.door_definition_id);
    if (!def) continue;
    if (dp.edge_id !== edge.id) continue;
    holes.push({
      centerS: dp.alpha * length,
      width: def.width,
      height: def.height,
      bottom: 0,
      kind: "door",
    });
  }
  return holes;
}

function buildWallForEdge(
  story: Story,
  edge: Edge,
  vById: Map<string, Vertex>,
  windowDefs: WindowDefinition[],
  doorDefs: DoorDefinition[],
  baseZ: number,
  storyHeight: number,
): SceneStoryInstance["walls"][number] | null {
  const a = vById.get(edge.vertex_ids[0]);
  const b = vById.get(edge.vertex_ids[1]);
  if (!a || !b) return null;
  const length = Math.hypot(b.x - a.x, b.y - a.y);
  if (length <= 1e-6) return null;

  const holes = holesForEdge(story, edge, windowDefs, doorDefs);
  const shape = buildWallShape(length, storyHeight, holes);
  const geom = new THREE.ExtrudeGeometry(shape, {
    depth: WALL_THICKNESS,
    bevelEnabled: false,
  });

  // Local shape lives in the (s, t, normal) frame.  Rotate so:
  //   local x (length)  -> world dir from a to b
  //   local y (height)  -> +world Y
  //   local z (depth)   -> world normal (we leave centered on the edge line)
  geom.translate(0, 0, -WALL_THICKNESS / 2);
  // First lay flat to XZ then rotate up: ExtrudeGeometry has shape in XY plane and depth along +Z.
  // We want shape's X to remain along the edge, shape's Y to become world Y, depth to become wall-normal.
  // Three.js ExtrudeGeometry: shape XY plane, depth along Z. So shape Y is already vertical if we rotate by 90deg around X? No — we want shape Y aligned with world Y, which it already is in default orientation. We need to rotate so depth (Z) is horizontal-perpendicular to the edge.
  // Default: x → world x, y → world y (vertical, good), z → world z (horizontal, depth into page).
  // So orient the edge along world X first (its natural state), then rotate the whole geom around world Y by the edge angle, and finally translate to vertex a + (baseZ on Y).

  const angle = Math.atan2(b.y - a.y, b.x - a.x);

  return {
    edgeId: edge.id,
    geometry: geom,
    position: [a.x, baseZ, -a.y],
    rotationY: -angle,
  };
}

function buildPanelGeometries(
  story: Story,
  vById: Map<string, Vertex>,
  windowDefs: WindowDefinition[],
  doorDefs: DoorDefinition[],
  baseZ: number,
): SceneStoryInstance["panels"] {
  const panels: SceneStoryInstance["panels"] = [];

  function pushPanel(
    edgeId: string,
    centerS: number,
    width: number,
    height: number,
    bottom: number,
    kind: "window" | "door",
  ) {
    const edge = story.geometry.edges.find((e) => e.id === edgeId);
    if (!edge) return;
    const a = vById.get(edge.vertex_ids[0]);
    const b = vById.get(edge.vertex_ids[1]);
    if (!a || !b) return;
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    if (length <= 0) return;

    const geom = new THREE.PlaneGeometry(width, height);
    const angle = Math.atan2(b.y - a.y, b.x - a.x);
    const s = centerS;
    const wx = a.x + (s / length) * (b.x - a.x);
    const wy = a.y + (s / length) * (b.y - a.y);
    panels.push({
      geometry: geom,
      position: [wx, baseZ + bottom + height / 2, -wy],
      rotationY: -angle,
      kind,
    });
  }

  for (const wp of story.windows) {
    const def = windowDefs.find((d) => d.id === wp.window_definition_id);
    if (!def) continue;
    const edge = story.geometry.edges.find((e) => e.id === wp.edge_id);
    if (!edge) continue;
    const a = vById.get(edge.vertex_ids[0]);
    const b = vById.get(edge.vertex_ids[1]);
    if (!a || !b) continue;
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    const alpha = typeof wp.alpha === "number" ? wp.alpha : 0.5;
    pushPanel(wp.edge_id, alpha * length, def.width ?? 1, def.height ?? 1, def.sill_height ?? 0.9, "window");
  }
  for (const dp of story.doors) {
    const def = doorDefs.find((d) => d.id === dp.door_definition_id);
    if (!def) continue;
    const edge = story.geometry.edges.find((e) => e.id === dp.edge_id);
    if (!edge) continue;
    const a = vById.get(edge.vertex_ids[0]);
    const b = vById.get(edge.vertex_ids[1]);
    if (!a || !b) continue;
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    pushPanel(dp.edge_id, dp.alpha * length, def.width, def.height, 0, "door");
  }
  return panels;
}

export function buildScene(doc: Floorplan): SceneBuildResult {
  const instances: SceneStoryInstance[] = [];
  const bounds = new THREE.Box3();

  let cumulativeBase = 0;
  for (const story of doc.stories) {
    const height = story.floor_to_ceiling_height ?? 3;
    const multiplier = story.multiplier ?? 1;
    const totalHeight =
      (story.below_floor_plenum_height ?? 0) +
      height +
      (story.above_ceiling_plenum_height ?? 0);

    const vById = new Map(story.geometry.vertices.map((v) => [v.id, v]));

    for (let m = 0; m < multiplier; m++) {
      const baseZ = cumulativeBase + (story.below_floor_plenum_height ?? 0);

      const slabs: SceneStoryInstance["slabs"] = [];
      for (const space of story.spaces) {
        if (!space.face_id) continue;
        const ring = ringFromFace(story, space.face_id);
        const geom = slabGeometry(ring);
        if (!geom) continue;
        // ExtrudeGeometry sits in XY plane; we already rotated it so it lies on XZ.
        // Move it down by FLOOR_THICKNESS so its top is at baseZ.
        geom.translate(0, baseZ - FLOOR_THICKNESS, 0);
        // Convert floorplan Y -> world Z (flip sign so "north" goes -Z)
        const flip = new THREE.Matrix4().makeScale(1, 1, -1);
        geom.applyMatrix4(flip);
        slabs.push({ geometry: geom, faceId: space.face_id });
      }

      // Deduplicate edges: one wall per unique edge belonging to at least one face.
      const wallEdges = story.geometry.edges.filter((e) => e.face_ids.length > 0);
      const walls: SceneStoryInstance["walls"] = [];
      for (const edge of wallEdges) {
        const wall = buildWallForEdge(
          story,
          edge,
          vById,
          doc.window_definitions,
          doc.door_definitions,
          baseZ,
          height,
        );
        if (wall) walls.push(wall);
      }

      const panels = buildPanelGeometries(
        story,
        vById,
        doc.window_definitions,
        doc.door_definitions,
        baseZ,
      );

      instances.push({
        storyId: story.id,
        baseZ,
        color: story.color ?? "#88B7D5",
        height,
        slabs,
        walls,
        panels,
      });

      for (const v of story.geometry.vertices) {
        bounds.expandByPoint(new THREE.Vector3(v.x, baseZ, -v.y));
        bounds.expandByPoint(new THREE.Vector3(v.x, baseZ + height, -v.y));
      }

      cumulativeBase += totalHeight;
    }
  }

  if (bounds.isEmpty()) {
    bounds.expandByPoint(new THREE.Vector3(-5, 0, -5));
    bounds.expandByPoint(new THREE.Vector3(5, 3, 5));
  }
  return { instances, bounds };
}
