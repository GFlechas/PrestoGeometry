/**
 * Pointer-snap logic shared by all drawing tools.
 *
 * All inputs and outputs are in WORLD coordinates (metres). The caller is
 * responsible for converting between screen pixels and world coordinates and
 * for converting the snap threshold accordingly.
 */

import type { Edge, Vertex } from "../schema/types";

export type SnapKind = "none" | "grid" | "vertex" | "edge";

export interface SnapResult {
  kind: SnapKind;
  x: number;
  y: number;
  /** Edge id when kind === "edge" or vertex id when kind === "vertex". */
  refId?: string;
}

export interface SnapInputs {
  /** Raw pointer position in world coordinates. */
  point: { x: number; y: number };
  /** Threshold for accepting a snap, expressed in WORLD units. */
  thresholdWorld: number;
  /** Grid spacing in world units (set to 0 or negative to disable grid snap). */
  gridSpacing: number;
  /** Vertices in the current story. */
  vertices: Vertex[];
  /** Edges in the current story. */
  edges: Edge[];
  /** Whether grid snap is enabled. */
  gridEnabled?: boolean;
}

function dist2(ax: number, ay: number, bx: number, by: number): number {
  const dx = ax - bx;
  const dy = ay - by;
  return dx * dx + dy * dy;
}

/** Perpendicular foot of point P onto segment AB, clamped to the segment. */
export function projectOnSegment(
  px: number,
  py: number,
  ax: number,
  ay: number,
  bx: number,
  by: number,
): { x: number; y: number; t: number } {
  const abx = bx - ax;
  const aby = by - ay;
  const len2 = abx * abx + aby * aby;
  if (len2 === 0) return { x: ax, y: ay, t: 0 };
  let t = ((px - ax) * abx + (py - ay) * aby) / len2;
  t = Math.max(0, Math.min(1, t));
  return { x: ax + t * abx, y: ay + t * aby, t };
}

export function snapPoint(inputs: SnapInputs): SnapResult {
  const { point, thresholdWorld, vertices, edges } = inputs;
  const gridSpacing = inputs.gridSpacing;
  const gridEnabled = inputs.gridEnabled ?? true;

  const threshold2 = thresholdWorld * thresholdWorld;
  let best: SnapResult = { kind: "none", x: point.x, y: point.y };

  // Vertex snap has absolute priority: if any vertex is in range, the closest
  // wins regardless of nearby edges.
  let bestVertexD2 = Infinity;
  for (const v of vertices) {
    const d2 = dist2(point.x, point.y, v.x, v.y);
    if (d2 < bestVertexD2 && d2 <= threshold2) {
      bestVertexD2 = d2;
      best = { kind: "vertex", x: v.x, y: v.y, refId: v.id };
    }
  }

  if (best.kind === "vertex") {
    return best;
  }

  // Edge projection snap
  let bestEdgeD2 = Infinity;
  const vById = new Map(vertices.map((v) => [v.id, v]));
  for (const e of edges) {
    const a = vById.get(e.vertex_ids[0]);
    const b = vById.get(e.vertex_ids[1]);
    if (!a || !b) continue;
    const proj = projectOnSegment(point.x, point.y, a.x, a.y, b.x, b.y);
    const d2 = dist2(point.x, point.y, proj.x, proj.y);
    if (d2 <= threshold2 && d2 < bestEdgeD2) {
      bestEdgeD2 = d2;
      best = { kind: "edge", x: proj.x, y: proj.y, refId: e.id };
    }
  }

  // Grid snap (lowest priority - only used if nothing else snapped)
  if (best.kind === "none" && gridEnabled && gridSpacing > 0) {
    const gx = Math.round(point.x / gridSpacing) * gridSpacing;
    const gy = Math.round(point.y / gridSpacing) * gridSpacing;
    const d2 = dist2(point.x, point.y, gx, gy);
    if (d2 <= threshold2) {
      best = { kind: "grid", x: gx, y: gy };
    } else {
      // Even outside threshold, grid snap is the implicit default for drawing
      best = { kind: "grid", x: gx, y: gy };
    }
  }

  return best;
}
