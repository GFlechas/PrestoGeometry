import { describe, expect, it } from "vitest";
import { projectOnSegment, snapPoint } from "./snap";
import type { Edge, Vertex } from "../schema/types";

const v = (id: string, x: number, y: number): Vertex => ({
  id,
  x,
  y,
  edge_ids: [],
});
const e = (id: string, a: string, b: string): Edge => ({
  id,
  vertex_ids: [a, b],
  face_ids: ["f"],
});

describe("projectOnSegment", () => {
  it("projects to midpoint", () => {
    const r = projectOnSegment(5, 1, 0, 0, 10, 0);
    expect(r.x).toBe(5);
    expect(r.y).toBe(0);
    expect(r.t).toBeCloseTo(0.5);
  });

  it("clamps before the start", () => {
    const r = projectOnSegment(-3, 1, 0, 0, 10, 0);
    expect(r.x).toBe(0);
    expect(r.t).toBe(0);
  });

  it("clamps past the end", () => {
    const r = projectOnSegment(20, 0, 0, 0, 10, 0);
    expect(r.x).toBe(10);
    expect(r.t).toBe(1);
  });
});

describe("snapPoint", () => {
  const vertices = [v("v1", 0, 0), v("v2", 10, 0), v("v3", 10, 10)];
  const edges = [e("e1", "v1", "v2"), e("e2", "v2", "v3")];

  it("snaps to a nearby vertex over edge", () => {
    const r = snapPoint({
      point: { x: 0.2, y: 0.2 },
      thresholdWorld: 1,
      gridSpacing: 0.5,
      vertices,
      edges,
    });
    expect(r.kind).toBe("vertex");
    expect(r.refId).toBe("v1");
  });

  it("snaps to an edge projection when no vertex is in range", () => {
    const r = snapPoint({
      point: { x: 5, y: 0.3 },
      thresholdWorld: 1,
      gridSpacing: 0.5,
      vertices,
      edges,
    });
    expect(r.kind).toBe("edge");
    expect(r.refId).toBe("e1");
    expect(r.y).toBe(0);
  });

  it("falls back to grid when nothing else is near", () => {
    const r = snapPoint({
      point: { x: 3.27, y: 7.13 },
      thresholdWorld: 1,
      gridSpacing: 0.5,
      vertices,
      edges,
    });
    expect(r.kind).toBe("grid");
    expect(r.x).toBeCloseTo(3.5);
    expect(r.y).toBeCloseTo(7);
  });

  it("vertex beats edge when both are in range", () => {
    const r = snapPoint({
      point: { x: 9.9, y: 0.05 },
      thresholdWorld: 1,
      gridSpacing: 0.5,
      vertices,
      edges,
    });
    expect(r.kind).toBe("vertex");
    expect(r.refId).toBe("v2");
  });

  it("grid disabled returns no snap when nothing in range", () => {
    const r = snapPoint({
      point: { x: 3.27, y: 7.13 },
      thresholdWorld: 0.5,
      gridSpacing: 0.5,
      vertices,
      edges,
      gridEnabled: false,
    });
    expect(r.kind).toBe("none");
  });
});
