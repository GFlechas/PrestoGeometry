/**
 * Mutations on a Story's Geometry (vertices/edges/faces).
 *
 * All ops are pure and return a new Geometry. Vertex/edge dedupe is centralised
 * here so the polygon tool and any future tools share identical behaviour.
 */

import { v4 as uuid } from "uuid";
import type { Edge, Face, Geometry, Vertex } from "../schema/types";

/**
 * One point in a polygon being drawn. ``snapVertexId`` is set when the point
 * was snapped to an existing vertex (so we reuse instead of creating).
 */
export interface DraftPoint {
  x: number;
  y: number;
  snapVertexId?: string;
}

const EPS = 1e-6;

function nearlyEqual(a: number, b: number): boolean {
  return Math.abs(a - b) < EPS;
}

function findVertexAt(
  geometry: Geometry,
  x: number,
  y: number,
): Vertex | undefined {
  return geometry.vertices.find((v) => nearlyEqual(v.x, x) && nearlyEqual(v.y, y));
}

function findEdgeBetween(
  geometry: Geometry,
  a: string,
  b: string,
): Edge | undefined {
  return geometry.edges.find(
    (e) =>
      (e.vertex_ids[0] === a && e.vertex_ids[1] === b) ||
      (e.vertex_ids[0] === b && e.vertex_ids[1] === a),
  );
}

function getOrCreateVertex(
  geometry: Geometry,
  point: DraftPoint,
): { geometry: Geometry; vertex: Vertex } {
  if (point.snapVertexId) {
    const existing = geometry.vertices.find((v) => v.id === point.snapVertexId);
    if (existing) return { geometry, vertex: existing };
  }
  const existingByCoord = findVertexAt(geometry, point.x, point.y);
  if (existingByCoord) return { geometry, vertex: existingByCoord };

  const vertex: Vertex = { id: uuid(), x: point.x, y: point.y, edge_ids: [] };
  return {
    geometry: { ...geometry, vertices: [...geometry.vertices, vertex] },
    vertex,
  };
}

function getOrCreateEdge(
  geometry: Geometry,
  aId: string,
  bId: string,
): { geometry: Geometry; edge: Edge; reversed: boolean } {
  const existing = findEdgeBetween(geometry, aId, bId);
  if (existing) {
    const reversed = existing.vertex_ids[0] !== aId;
    return { geometry, edge: existing, reversed };
  }
  const edge: Edge = {
    id: uuid(),
    vertex_ids: [aId, bId],
    face_ids: [],
  };
  return {
    geometry: { ...geometry, edges: [...geometry.edges, edge] },
    edge,
    reversed: false,
  };
}

/**
 * Signed area of a polygon (positive = counter-clockwise).
 * Used to enforce consistent winding.
 */
export function signedArea(points: { x: number; y: number }[]): number {
  let a = 0;
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    const q = points[(i + 1) % points.length];
    a += p.x * q.y - q.x * p.y;
  }
  return a / 2;
}

/**
 * Take a draft polygon (3+ points) and weld it into the existing Geometry,
 * creating a new Face plus any missing Vertices/Edges. Returns the updated
 * Geometry and the new Face's id, or null if the polygon was degenerate.
 */
export function closePolygon(
  geometry: Geometry,
  points: DraftPoint[],
): { geometry: Geometry; faceId: string } | null {
  if (points.length < 3) return null;
  if (Math.abs(signedArea(points)) < EPS) return null;

  // Force counter-clockwise winding so floor slabs render with a sensible
  // outward normal in 3D.
  const ordered = signedArea(points) < 0 ? [...points].reverse() : points;

  let g = geometry;
  const vertexIds: string[] = [];
  for (const pt of ordered) {
    const r = getOrCreateVertex(g, pt);
    g = r.geometry;
    vertexIds.push(r.vertex.id);
  }

  const edgeIds: string[] = [];
  const edgeOrder: (0 | 1)[] = [];
  for (let i = 0; i < vertexIds.length; i++) {
    const a = vertexIds[i];
    const b = vertexIds[(i + 1) % vertexIds.length];
    if (a === b) return null;
    const r = getOrCreateEdge(g, a, b);
    g = r.geometry;
    edgeIds.push(r.edge.id);
    edgeOrder.push(r.reversed ? 1 : 0);
  }

  const face: Face = { id: uuid(), edge_ids: edgeIds, edge_order: edgeOrder };

  // Backlink edges -> face, and refresh edge_ids on the involved vertices.
  const edgeIdSet = new Set(edgeIds);
  const edges = g.edges.map((e) =>
    edgeIdSet.has(e.id)
      ? { ...e, face_ids: e.face_ids.includes(face.id) ? e.face_ids : [...e.face_ids, face.id] }
      : e,
  );

  const vertexEdgeMap = new Map<string, Set<string>>();
  for (const e of edges) {
    for (const vid of e.vertex_ids) {
      if (!vertexEdgeMap.has(vid)) vertexEdgeMap.set(vid, new Set());
      vertexEdgeMap.get(vid)!.add(e.id);
    }
  }
  const vertices = g.vertices.map((v) =>
    vertexEdgeMap.has(v.id)
      ? { ...v, edge_ids: Array.from(vertexEdgeMap.get(v.id)!) }
      : v,
  );

  return {
    geometry: {
      ...g,
      edges,
      vertices,
      faces: [...g.faces, face],
    },
    faceId: face.id,
  };
}

/** Resolve a Face into its outer ring of vertex coordinates (in winding order). */
export function faceRing(geometry: Geometry, face: Face): { x: number; y: number; vertexId: string }[] {
  const ring: { x: number; y: number; vertexId: string }[] = [];
  const vById = new Map(geometry.vertices.map((v) => [v.id, v]));
  const eById = new Map(geometry.edges.map((e) => [e.id, e]));
  for (let i = 0; i < face.edge_ids.length; i++) {
    const edge = eById.get(face.edge_ids[i]);
    if (!edge) continue;
    const reversed = face.edge_order[i] === 1;
    const vid = reversed ? edge.vertex_ids[1] : edge.vertex_ids[0];
    const vertex = vById.get(vid);
    if (vertex) ring.push({ x: vertex.x, y: vertex.y, vertexId: vertex.id });
  }
  return ring;
}
