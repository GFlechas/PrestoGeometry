import { useEffect, useMemo, useRef, useState } from "react";
import { Stage, Layer, Line, Circle, Rect, Group } from "react-konva";
import type Konva from "konva";
import { useFloorplan, useActiveStory } from "../state/useFloorplan";
import { useSelection, type ToolId } from "../state/selection";
import { snapPoint, type SnapResult } from "../drawing/snap";
import { faceRing, type DraftPoint } from "../drawing/geometryOps";
import { projectOnSegment } from "../drawing/snap";

interface ViewTransform {
  /** World units per pixel. */
  scale: number;
  /** Pan offset in pixels (where world origin sits on screen). */
  offsetX: number;
  offsetY: number;
}

const INITIAL: ViewTransform = { scale: 20, offsetX: 0, offsetY: 0 };

function worldToScreen(t: ViewTransform, x: number, y: number) {
  return {
    x: x * t.scale + t.offsetX,
    y: -y * t.scale + t.offsetY,
  };
}

function screenToWorld(t: ViewTransform, sx: number, sy: number) {
  return {
    x: (sx - t.offsetX) / t.scale,
    y: -(sy - t.offsetY) / t.scale,
  };
}

export function EditorCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [transform, setTransform] = useState<ViewTransform>(() => ({
    ...INITIAL,
    offsetX: 400,
    offsetY: 300,
  }));
  const [draft, setDraft] = useState<DraftPoint[]>([]);
  const [hover, setHover] = useState<{ snap: SnapResult; sx: number; sy: number } | null>(null);

  const story = useActiveStory();
  const tool = useSelection((s) => s.tool);
  const select = useSelection((s) => s.select);
  const setTool = useSelection((s) => s.setTool);
  const activeWindowDefId = useSelection((s) => s.activeWindowDefId);
  const activeDoorDefId = useSelection((s) => s.activeDoorDefId);
  const snapEnabled = useSelection((s) => s.snapEnabled);
  const snapThresholdPx = useSelection((s) => s.snapThresholdPx);

  const gridSpacing = useFloorplan((s) => s.doc.project.grid.spacing) ?? 0.5;
  const createSpaceFromPolygon = useFloorplan((s) => s.createSpaceFromPolygon);
  const placeWindow = useFloorplan((s) => s.placeWindow);
  const placeDoor = useFloorplan((s) => s.placeDoor);
  const removeSpace = useFloorplan((s) => s.removeSpace);
  const removeWindow = useFloorplan((s) => s.removeWindow);
  const removeDoor = useFloorplan((s) => s.removeDoor);
  const windowDefs = useFloorplan((s) => s.doc.window_definitions);
  const doorDefs = useFloorplan((s) => s.doc.door_definitions);

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const ro = new ResizeObserver(() => {
      setSize({ w: el.clientWidth, h: el.clientHeight });
      setTransform((t) => ({
        ...t,
        offsetX: el.clientWidth / 2,
        offsetY: el.clientHeight / 2,
      }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Clear draft when switching tool or story
  useEffect(() => {
    setDraft([]);
  }, [tool, story?.id]);

  // Enter key closes a polygon
  useEffect(() => {
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Enter" && tool === "draw-room" && draft.length >= 3 && story) {
        createSpaceFromPolygon(story.id, draft);
        setDraft([]);
      } else if (ev.key === "Escape") {
        setDraft([]);
        select(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tool, draft, story, createSpaceFromPolygon, select]);

  function computeSnap(sx: number, sy: number): SnapResult {
    const world = screenToWorld(transform, sx, sy);
    if (!snapEnabled || !story) {
      return { kind: "none", x: world.x, y: world.y };
    }
    return snapPoint({
      point: world,
      thresholdWorld: snapThresholdPx / transform.scale,
      gridSpacing,
      vertices: story.geometry.vertices,
      edges: story.geometry.edges,
    });
  }

  function handlePointerMove(ev: Konva.KonvaEventObject<MouseEvent>) {
    const stage = ev.target.getStage();
    if (!stage) return;
    const pos = stage.getPointerPosition();
    if (!pos) return;
    const snap = computeSnap(pos.x, pos.y);
    const screen = worldToScreen(transform, snap.x, snap.y);
    setHover({ snap, sx: screen.x, sy: screen.y });
  }

  function handleClick(ev: Konva.KonvaEventObject<MouseEvent>) {
    if (!story) return;
    const stage = ev.target.getStage();
    if (!stage) return;
    const pos = stage.getPointerPosition();
    if (!pos) return;
    const snap = computeSnap(pos.x, pos.y);

    if (tool === "draw-room") {
      // Close if we clicked near the first vertex
      if (draft.length >= 3) {
        const first = draft[0];
        const d = Math.hypot(first.x - snap.x, first.y - snap.y);
        if (d < snapThresholdPx / transform.scale) {
          createSpaceFromPolygon(story.id, draft);
          setDraft([]);
          return;
        }
      }
      setDraft((d) => [
        ...d,
        {
          x: snap.x,
          y: snap.y,
          snapVertexId: snap.kind === "vertex" ? snap.refId : undefined,
        },
      ]);
      return;
    }

    if (tool === "place-window" && snap.kind === "edge" && snap.refId && activeWindowDefId) {
      const edge = story.geometry.edges.find((e) => e.id === snap.refId);
      if (!edge) return;
      const a = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[0])!;
      const b = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[1])!;
      const proj = projectOnSegment(snap.x, snap.y, a.x, a.y, b.x, b.y);
      placeWindow(story.id, {
        window_definition_id: activeWindowDefId,
        edge_id: edge.id,
        alpha: proj.t,
      });
      return;
    }

    if (tool === "place-door" && snap.kind === "edge" && snap.refId && activeDoorDefId) {
      const edge = story.geometry.edges.find((e) => e.id === snap.refId);
      if (!edge) return;
      const a = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[0])!;
      const b = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[1])!;
      const proj = projectOnSegment(snap.x, snap.y, a.x, a.y, b.x, b.y);
      placeDoor(story.id, {
        door_definition_id: activeDoorDefId,
        edge_id: edge.id,
        alpha: proj.t,
      });
      return;
    }
  }

  function handleFaceClick(faceId: string) {
    if (!story) return;
    if (tool === "select") {
      const space = story.spaces.find((sp) => sp.face_id === faceId);
      if (space) {
        select({ kind: "space", storyId: story.id, spaceId: space.id });
      }
    } else if (tool === "erase") {
      const space = story.spaces.find((sp) => sp.face_id === faceId);
      if (space) removeSpace(story.id, space.id);
    }
  }

  function handleWindowClick(edgeId: string, defId: string) {
    if (!story) return;
    if (tool === "select") {
      select({ kind: "window", storyId: story.id, edgeId, windowDefId: defId });
    } else if (tool === "erase") {
      removeWindow(story.id, edgeId, defId);
    }
  }

  function handleDoorClick(edgeId: string, defId: string) {
    if (!story) return;
    if (tool === "select") {
      select({ kind: "door", storyId: story.id, edgeId, doorDefId: defId });
    } else if (tool === "erase") {
      removeDoor(story.id, edgeId, defId);
    }
  }

  // Wheel zoom around pointer
  function handleWheel(ev: Konva.KonvaEventObject<WheelEvent>) {
    ev.evt.preventDefault();
    const stage = ev.target.getStage();
    if (!stage) return;
    const pointer = stage.getPointerPosition();
    if (!pointer) return;
    const before = screenToWorld(transform, pointer.x, pointer.y);
    const factor = ev.evt.deltaY < 0 ? 1.15 : 1 / 1.15;
    const nextScale = Math.max(2, Math.min(400, transform.scale * factor));
    const nextOffsetX = pointer.x - before.x * nextScale;
    const nextOffsetY = pointer.y + before.y * nextScale;
    setTransform({ scale: nextScale, offsetX: nextOffsetX, offsetY: nextOffsetY });
  }

  // Middle-mouse / space-drag pan
  const [panning, setPanning] = useState<{ x: number; y: number } | null>(null);
  function handleMouseDown(ev: Konva.KonvaEventObject<MouseEvent>) {
    if (ev.evt.button === 1 || (ev.evt.button === 0 && ev.evt.shiftKey)) {
      setPanning({ x: ev.evt.clientX, y: ev.evt.clientY });
    }
  }
  function handleMouseUp() {
    setPanning(null);
  }
  function handleMouseMove(ev: Konva.KonvaEventObject<MouseEvent>) {
    if (panning) {
      const dx = ev.evt.clientX - panning.x;
      const dy = ev.evt.clientY - panning.y;
      setTransform((t) => ({ ...t, offsetX: t.offsetX + dx, offsetY: t.offsetY + dy }));
      setPanning({ x: ev.evt.clientX, y: ev.evt.clientY });
      return;
    }
    handlePointerMove(ev);
  }

  // Grid lines for the visible area
  const gridLines = useMemo(() => {
    const spacing = gridSpacing;
    if (!spacing || spacing <= 0) return [] as JSX.Element[];
    const pxSpacing = spacing * transform.scale;
    if (pxSpacing < 6) return []; // too dense to render
    const lines: JSX.Element[] = [];
    const left = screenToWorld(transform, 0, 0);
    const right = screenToWorld(transform, size.w, size.h);
    const minX = Math.floor(left.x / spacing) * spacing;
    const maxX = Math.ceil(right.x / spacing) * spacing;
    const minY = Math.floor(right.y / spacing) * spacing;
    const maxY = Math.ceil(left.y / spacing) * spacing;
    for (let x = minX; x <= maxX; x += spacing) {
      const sx = worldToScreen(transform, x, 0).x;
      lines.push(
        <Line
          key={`gx-${x}`}
          points={[sx, 0, sx, size.h]}
          stroke="#2f3540"
          strokeWidth={Math.abs(x) < 1e-6 ? 1.5 : 0.5}
          listening={false}
        />,
      );
    }
    for (let y = minY; y <= maxY; y += spacing) {
      const sy = worldToScreen(transform, 0, y).y;
      lines.push(
        <Line
          key={`gy-${y}`}
          points={[0, sy, size.w, sy]}
          stroke="#2f3540"
          strokeWidth={Math.abs(y) < 1e-6 ? 1.5 : 0.5}
          listening={false}
        />,
      );
    }
    return lines;
  }, [transform, gridSpacing, size]);

  const selection = useSelection((s) => s.selection);

  if (!story) {
    return (
      <div ref={containerRef} style={{ width: "100%", height: "100%" }}>
        <div className="overlay">No story selected. Add one in the Stories panel.</div>
      </div>
    );
  }

  const ring = (faceId: string) => {
    const face = story.geometry.faces.find((f) => f.id === faceId);
    if (!face) return [] as number[];
    const pts = faceRing(story.geometry, face);
    const flat: number[] = [];
    for (const p of pts) {
      const s = worldToScreen(transform, p.x, p.y);
      flat.push(s.x, s.y);
    }
    return flat;
  };

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", position: "relative" }}
      onContextMenu={(e) => e.preventDefault()}
    >
      <Stage
        width={size.w}
        height={size.h}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onClick={handleClick}
        onWheel={handleWheel}
        style={{ cursor: cursorFor(tool, panning != null) }}
      >
        <Layer listening={false}>{gridLines}</Layer>

        {/* Faces (spaces) */}
        <Layer>
          {story.spaces.map((sp) => {
            if (!sp.face_id) return null;
            const isSelected =
              selection?.kind === "space" && selection.spaceId === sp.id;
            return (
              <Line
                key={sp.id}
                points={ring(sp.face_id)}
                closed
                fill={isSelected ? "#4f9cff66" : "#88b7d544"}
                stroke={isSelected ? "#4f9cff" : "#88b7d5"}
                strokeWidth={isSelected ? 2 : 1}
                onClick={(e) => {
                  e.cancelBubble = true;
                  handleFaceClick(sp.face_id!);
                }}
              />
            );
          })}
        </Layer>

        {/* Edges (highlighted when hosting openings or during placement) */}
        <Layer>
          {story.geometry.edges.map((edge) => {
            const a = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[0]);
            const b = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[1]);
            if (!a || !b) return null;
            const sa = worldToScreen(transform, a.x, a.y);
            const sb = worldToScreen(transform, b.x, b.y);
            const hostsOpening =
              story.windows.some((w) => w.edge_id === edge.id) ||
              story.doors.some((d) => d.edge_id === edge.id);
            return (
              <Line
                key={edge.id}
                points={[sa.x, sa.y, sb.x, sb.y]}
                stroke={hostsOpening ? "#f0a82c" : "#cfd6e1"}
                strokeWidth={hostsOpening ? 2 : 1.5}
                listening={false}
              />
            );
          })}
        </Layer>

        {/* Windows + doors as markers along the edge */}
        <Layer>
          {story.windows.map((w, i) => {
            const edge = story.geometry.edges.find((e) => e.id === w.edge_id);
            if (!edge) return null;
            const a = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[0])!;
            const b = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[1])!;
            const alpha = typeof w.alpha === "number" ? w.alpha : 0.5;
            const wx = a.x + alpha * (b.x - a.x);
            const wy = a.y + alpha * (b.y - a.y);
            const s = worldToScreen(transform, wx, wy);
            const def = windowDefs.find((d) => d.id === w.window_definition_id);
            const widthPx = ((def?.width ?? 1) * transform.scale);
            const angle =
              (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
            return (
              <Group
                key={`w-${i}`}
                x={s.x}
                y={s.y}
                rotation={-angle}
                onClick={(e) => {
                  e.cancelBubble = true;
                  handleWindowClick(w.edge_id, w.window_definition_id);
                }}
              >
                <Rect
                  x={-widthPx / 2}
                  y={-3}
                  width={widthPx}
                  height={6}
                  fill="#4f9cff"
                  stroke="#1f2329"
                  strokeWidth={1}
                />
              </Group>
            );
          })}
          {story.doors.map((d, i) => {
            const edge = story.geometry.edges.find((e) => e.id === d.edge_id);
            if (!edge) return null;
            const a = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[0])!;
            const b = story.geometry.vertices.find((v) => v.id === edge.vertex_ids[1])!;
            const wx = a.x + d.alpha * (b.x - a.x);
            const wy = a.y + d.alpha * (b.y - a.y);
            const s = worldToScreen(transform, wx, wy);
            const def = doorDefs.find((dd) => dd.id === d.door_definition_id);
            const widthPx = ((def?.width ?? 0.9) * transform.scale);
            const angle =
              (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
            return (
              <Group
                key={`d-${i}`}
                x={s.x}
                y={s.y}
                rotation={-angle}
                onClick={(e) => {
                  e.cancelBubble = true;
                  handleDoorClick(d.edge_id, d.door_definition_id);
                }}
              >
                <Rect
                  x={-widthPx / 2}
                  y={-4}
                  width={widthPx}
                  height={8}
                  fill="#a86b3a"
                  stroke="#1f2329"
                  strokeWidth={1}
                />
              </Group>
            );
          })}
        </Layer>

        {/* Draft polygon */}
        {tool === "draw-room" && draft.length > 0 && (
          <Layer listening={false}>
            <Line
              points={[
                ...draft.flatMap((p) => {
                  const s = worldToScreen(transform, p.x, p.y);
                  return [s.x, s.y];
                }),
                ...(hover && tool === "draw-room"
                  ? [hover.sx, hover.sy]
                  : []),
              ]}
              stroke="#4f9cff"
              strokeWidth={1.5}
              dash={[6, 4]}
            />
            {draft.map((p, i) => {
              const s = worldToScreen(transform, p.x, p.y);
              return (
                <Circle
                  key={i}
                  x={s.x}
                  y={s.y}
                  radius={i === 0 ? 6 : 4}
                  fill={i === 0 ? "#4f9cff" : "#cfd6e1"}
                  stroke="#1f2329"
                  strokeWidth={1}
                />
              );
            })}
          </Layer>
        )}

        {/* Vertices (visible during draw) */}
        {tool === "draw-room" && (
          <Layer listening={false}>
            {story.geometry.vertices.map((v) => {
              const s = worldToScreen(transform, v.x, v.y);
              return <Circle key={v.id} x={s.x} y={s.y} radius={3} fill="#9aa3b2" />;
            })}
          </Layer>
        )}

        {/* Snap indicator */}
        {hover && hover.snap.kind !== "none" && tool !== "select" && (
          <Layer listening={false}>
            <SnapIndicator snap={hover.snap} sx={hover.sx} sy={hover.sy} />
          </Layer>
        )}
      </Stage>
      <div className="overlay">
        Tool: {tool} · Scale: {transform.scale.toFixed(1)} px/m · Story: {story.name}
        {tool === "draw-room" && draft.length > 0 && (
          <> · {draft.length} pt(s) — Enter to close, Esc to cancel</>
        )}
        {(tool === "place-window" || tool === "place-door") &&
          !(tool === "place-window" ? activeWindowDefId : activeDoorDefId) && (
            <> · Select a definition in the right panel</>
          )}
      </div>
      <Hotkeys setTool={setTool} />
    </div>
  );
}

function cursorFor(tool: ToolId, panning: boolean) {
  if (panning) return "grabbing";
  if (tool === "select") return "default";
  if (tool === "erase") return "not-allowed";
  return "crosshair";
}

function SnapIndicator({ snap, sx, sy }: { snap: SnapResult; sx: number; sy: number }) {
  if (snap.kind === "vertex") {
    return <Circle x={sx} y={sy} radius={8} stroke="#5cc488" strokeWidth={2} />;
  }
  if (snap.kind === "edge") {
    return (
      <Rect
        x={sx - 5}
        y={sy - 5}
        width={10}
        height={10}
        stroke="#f0a82c"
        strokeWidth={2}
        rotation={45}
      />
    );
  }
  return <Rect x={sx - 5} y={sy - 5} width={10} height={10} stroke="#9aa3b2" strokeWidth={1} />;
}

function Hotkeys({ setTool }: { setTool: (t: ToolId) => void }) {
  useEffect(() => {
    function onKey(ev: KeyboardEvent) {
      if (ev.target instanceof HTMLInputElement || ev.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (ev.key === "v") setTool("select");
      else if (ev.key === "r") setTool("draw-room");
      else if (ev.key === "w") setTool("place-window");
      else if (ev.key === "d") setTool("place-door");
      else if (ev.key === "x") setTool("erase");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setTool]);
  return null;
}
