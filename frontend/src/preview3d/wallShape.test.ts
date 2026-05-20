import { describe, expect, it } from "vitest";
import { buildWallShape } from "./wallShape";

function signedArea2D(pts: { x: number; y: number }[]): number {
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    const q = pts[(i + 1) % pts.length];
    a += p.x * q.y - q.x * p.y;
  }
  return a / 2;
}

describe("buildWallShape", () => {
  it("creates a CCW outer ring and CW hole for one window", () => {
    const shape = buildWallShape(5, 3, [
      { centerS: 2.5, width: 1, height: 1, bottom: 0.9, kind: "window" },
    ]);
    const outer = shape.getPoints(0);
    expect(signedArea2D(outer)).toBeGreaterThan(0);

    expect(shape.holes).toHaveLength(1);
    const holePts = shape.holes[0].getPoints(0);
    expect(signedArea2D(holePts)).toBeLessThan(0);
  });

  it("ignores zero-sized holes", () => {
    const shape = buildWallShape(5, 3, [
      { centerS: 2.5, width: 0, height: 1, bottom: 0.9, kind: "window" },
    ]);
    expect(shape.holes).toHaveLength(0);
  });

  it("clips holes that fall outside the wall to nothing", () => {
    const shape = buildWallShape(5, 3, [
      { centerS: 100, width: 1, height: 1, bottom: 0.9, kind: "window" },
    ]);
    expect(shape.holes).toHaveLength(0);
  });
});
