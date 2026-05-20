import { useFloorplan } from "../state/useFloorplan";
import { useSelection } from "../state/selection";

export function InspectorPanel() {
  const selection = useSelection((s) => s.selection);
  const stories = useFloorplan((s) => s.doc.stories);
  const zones = useFloorplan((s) => s.doc.thermal_zones);
  const windowDefs = useFloorplan((s) => s.doc.window_definitions);
  const doorDefs = useFloorplan((s) => s.doc.door_definitions);
  const updateSpace = useFloorplan((s) => s.updateSpace);

  if (!selection) {
    return (
      <div className="panel">
        <h3>Inspector</h3>
        <div className="muted">Select something on the canvas (V) to edit.</div>
      </div>
    );
  }

  const story = stories.find((s) => s.id === selection.storyId);
  if (!story) return null;

  if (selection.kind === "space") {
    const space = story.spaces.find((sp) => sp.id === selection.spaceId);
    if (!space) return null;
    return (
      <div className="panel">
        <h3>Space</h3>
        <div className="row">
          <label>Name</label>
          <input
            value={space.name ?? ""}
            onChange={(e) => updateSpace(story.id, space.id, { name: e.target.value })}
          />
        </div>
        <div className="row">
          <label>Thermal Zone</label>
          <select
            value={space.thermal_zone_id ?? ""}
            onChange={(e) =>
              updateSpace(story.id, space.id, {
                thermal_zone_id: e.target.value || null,
              })
            }
          >
            <option value="">(none)</option>
            {zones.map((z) => (
              <option key={z.id} value={z.id}>
                {z.name ?? z.id}
              </option>
            ))}
          </select>
        </div>
        <div className="row">
          <label>Override ceiling (m)</label>
          <input
            type="number"
            step={0.1}
            min={0}
            value={space.floor_to_ceiling_height ?? ""}
            placeholder={`${story.floor_to_ceiling_height ?? 3}`}
            onChange={(e) =>
              updateSpace(story.id, space.id, {
                floor_to_ceiling_height: e.target.value === "" ? null : parseFloat(e.target.value),
              })
            }
          />
        </div>
        <div className="row">
          <label>Open to below</label>
          <input
            type="checkbox"
            checked={space.open_to_below ?? false}
            onChange={(e) =>
              updateSpace(story.id, space.id, { open_to_below: e.target.checked })
            }
          />
        </div>
      </div>
    );
  }

  if (selection.kind === "window") {
    const def = windowDefs.find((d) => d.id === selection.windowDefId);
    const placement = story.windows.find(
      (w) => w.edge_id === selection.edgeId && w.window_definition_id === selection.windowDefId,
    );
    if (!def || !placement) return null;
    return (
      <div className="panel">
        <h3>Window</h3>
        <div className="row">
          <label>Definition</label>
          <span>{def.name}</span>
        </div>
        <div className="row">
          <label>Edge</label>
          <span className="muted">{selection.edgeId.slice(0, 8)}…</span>
        </div>
        <div className="row">
          <label>Alpha</label>
          <span>{typeof placement.alpha === "number" ? placement.alpha.toFixed(2) : "—"}</span>
        </div>
        <div className="muted" style={{ marginTop: 6 }}>
          To delete, switch to Erase (X) and click the marker.
        </div>
      </div>
    );
  }

  if (selection.kind === "door") {
    const def = doorDefs.find((d) => d.id === selection.doorDefId);
    const placement = story.doors.find(
      (d) => d.edge_id === selection.edgeId && d.door_definition_id === selection.doorDefId,
    );
    if (!def || !placement) return null;
    return (
      <div className="panel">
        <h3>Door</h3>
        <div className="row">
          <label>Definition</label>
          <span>{def.name}</span>
        </div>
        <div className="row">
          <label>Edge</label>
          <span className="muted">{selection.edgeId.slice(0, 8)}…</span>
        </div>
        <div className="row">
          <label>Alpha</label>
          <span>{placement.alpha.toFixed(2)}</span>
        </div>
      </div>
    );
  }

  return null;
}
