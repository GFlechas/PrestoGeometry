export type ScaleKind = "total_height" | "wall_length";

export interface ScaleRef {
  kind: ScaleKind;
  value: number;
  floor_to_ceiling_height?: number;
  snap_orthogonal?: boolean;
}

export interface PoseExtractionStatus {
  cuda_available: boolean;
  torch_available: boolean;
  model_loaded: boolean;
  device: string | null;
}

export async function getStatus(): Promise<PoseExtractionStatus> {
  const res = await fetch("/api/pose-extraction/status");
  if (!res.ok) throw new Error(`status ${res.status}`);
  return res.json();
}

export async function extractFloorplan(
  files: File[],
  scale: ScaleRef,
): Promise<Record<string, unknown>> {
  const fd = new FormData();
  for (const f of files) fd.append("images", f, f.name);
  fd.append("scale_kind", scale.kind);
  fd.append("scale_value", String(scale.value));
  if (scale.floor_to_ceiling_height !== undefined) {
    fd.append("floor_to_ceiling_height", String(scale.floor_to_ceiling_height));
  }
  fd.append("snap_orthogonal", scale.snap_orthogonal === false ? "false" : "true");

  const res = await fetch("/api/pose-extraction", { method: "POST", body: fd });
  const body = await res.json();
  if (!res.ok) {
    const msg = (body && (body.error || body.message)) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return body;
}

export async function saveFloorplan(plan: Record<string, unknown>): Promise<void> {
  const res = await fetch("/api/floorplan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
  const body = await res.json();
  if (!res.ok || body.ok === false) {
    const msg = JSON.stringify(body.errors || body.error || body);
    throw new Error(`save failed: ${msg}`);
  }
}
