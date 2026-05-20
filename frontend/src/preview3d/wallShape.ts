import * as THREE from "three";

export interface Hole {
  /** Center of hole measured along the wall (metres from the start vertex). */
  centerS: number;
  /** Width of the hole along the wall (metres). */
  width: number;
  /** Height of the hole (metres). */
  height: number;
  /** Distance from the wall base to the bottom of the hole (metres). */
  bottom: number;
  kind: "window" | "door";
}

/**
 * Build a THREE.Shape representing one wall in local (s, t) coordinates where
 *   s = distance along the edge from the start vertex
 *   t = height above the wall base
 *
 * The outer rectangle is wound CCW; each hole rectangle is wound CW (opposite),
 * which is required by THREE.Shape for the extruder to interpret them as holes.
 *
 * Returns an empty (zero-area) shape if the edge length is invalid.
 */
export function buildWallShape(length: number, height: number, holes: Hole[]): THREE.Shape {
  const shape = new THREE.Shape();
  if (length <= 0 || height <= 0) return shape;

  shape.moveTo(0, 0);
  shape.lineTo(length, 0);
  shape.lineTo(length, height);
  shape.lineTo(0, height);
  shape.lineTo(0, 0);

  for (const h of holes) {
    const halfW = h.width / 2;
    const left = Math.max(0, h.centerS - halfW);
    const right = Math.min(length, h.centerS + halfW);
    const bottom = Math.max(0, h.bottom);
    const top = Math.min(height, h.bottom + h.height);
    if (right - left <= 0 || top - bottom <= 0) continue;

    const path = new THREE.Path();
    path.moveTo(left, bottom);
    path.lineTo(left, top);
    path.lineTo(right, top);
    path.lineTo(right, bottom);
    path.lineTo(left, bottom);
    shape.holes.push(path);
  }

  return shape;
}
