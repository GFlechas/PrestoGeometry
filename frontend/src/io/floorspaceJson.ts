import type { Floorplan } from "../schema/types";
import { validateFloorplan } from "../schema/validate";

export async function loadFromFile(file: File): Promise<{
  doc: Floorplan | null;
  errors: { path: string; message: string }[];
}> {
  const text = await file.text();
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (err) {
    return { doc: null, errors: [{ path: "/", message: `invalid JSON: ${err}` }] };
  }
  const result = await validateFloorplan(parsed);
  if (!result.valid) return { doc: null, errors: result.errors };
  return { doc: parsed as Floorplan, errors: [] };
}

export function downloadAsFile(doc: Floorplan, filename = "floorplan.json") {
  const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function fetchServerFloorplan(): Promise<Floorplan> {
  const res = await fetch("/api/floorplan");
  if (!res.ok) throw new Error(`/api/floorplan failed: ${res.status}`);
  return res.json();
}

export async function postServerFloorplan(doc: Floorplan): Promise<{
  ok: boolean;
  errors?: { path: string[]; message: string }[];
}> {
  const res = await fetch("/api/floorplan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(doc),
  });
  return res.json();
}
