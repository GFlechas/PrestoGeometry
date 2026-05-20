import { describe, expect, it } from "vitest";
import { closePolygon, faceRing, signedArea } from "./geometryOps";
import type { Geometry } from "../schema/types";

const emptyGeom = (): Geometry => ({
  id: "g",
  vertices: [],
  edges: [],
  faces: [],
});

describe("signedArea", () => {
  it("is positive for CCW square", () => {
    const a = signedArea([
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ]);
    expect(a).toBeGreaterThan(0);
  });

  it("is negative for CW square", () => {
    const a = signedArea([
      { x: 0, y: 0 },
      { x: 0, y: 10 },
      { x: 10, y: 10 },
      { x: 10, y: 0 },
    ]);
    expect(a).toBeLessThan(0);
  });
});

describe("closePolygon", () => {
  it("creates 4 vertices, 4 edges, 1 face for a fresh square", () => {
    const result = closePolygon(emptyGeom(), [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ]);
    expect(result).not.toBeNull();
    const g = result!.geometry;
    expect(g.vertices).toHaveLength(4);
    expect(g.edges).toHaveLength(4);
    expect(g.faces).toHaveLength(1);
    for (const e of g.edges) {
      expect(e.face_ids).toContain(result!.faceId);
    }
    for (const v of g.vertices) {
      expect(v.edge_ids).toHaveLength(2);
    }
  });

  it("deduplicates vertices and edges for adjacent rooms sharing a wall", () => {
    const first = closePolygon(emptyGeom(), [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ])!;
    const second = closePolygon(first.geometry, [
      { x: 10, y: 0 },
      { x: 20, y: 0 },
      { x: 20, y: 10 },
      { x: 10, y: 10 },
    ])!;
    const g = second.geometry;
    expect(g.vertices).toHaveLength(6);
    expect(g.edges).toHaveLength(7);
    expect(g.faces).toHaveLength(2);
    const shared = g.edges.filter((e) => e.face_ids.length === 2);
    expect(shared).toHaveLength(1);
  });

  it("rejects degenerate polygons", () => {
    expect(
      closePolygon(emptyGeom(), [
        { x: 0, y: 0 },
        { x: 1, y: 0 },
      ]),
    ).toBeNull();
    expect(
      closePolygon(emptyGeom(), [
        { x: 0, y: 0 },
        { x: 1, y: 0 },
        { x: 2, y: 0 },
      ]),
    ).toBeNull();
  });

  it("face ring walks vertices in winding order", () => {
    const r = closePolygon(emptyGeom(), [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ])!;
    const face = r.geometry.faces[0];
    const ring = faceRing(r.geometry, face);
    expect(ring).toHaveLength(4);
    expect(ring[0]).toMatchObject({ x: 0, y: 0 });
  });
});
