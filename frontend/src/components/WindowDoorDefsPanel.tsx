import { useFloorplan } from "../state/useFloorplan";
import { useSelection } from "../state/selection";

export function WindowDoorDefsPanel() {
  const windowDefs = useFloorplan((s) => s.doc.window_definitions);
  const doorDefs = useFloorplan((s) => s.doc.door_definitions);
  const addWindow = useFloorplan((s) => s.addWindowDefinition);
  const removeWindow = useFloorplan((s) => s.removeWindowDefinition);
  const updateWindow = useFloorplan((s) => s.updateWindowDefinition);
  const addDoor = useFloorplan((s) => s.addDoorDefinition);
  const removeDoor = useFloorplan((s) => s.removeDoorDefinition);
  const updateDoor = useFloorplan((s) => s.updateDoorDefinition);

  const activeWindowDefId = useSelection((s) => s.activeWindowDefId);
  const activeDoorDefId = useSelection((s) => s.activeDoorDefId);
  const setActiveWindowDefId = useSelection((s) => s.setActiveWindowDefId);
  const setActiveDoorDefId = useSelection((s) => s.setActiveDoorDefId);
  const setTool = useSelection((s) => s.setTool);

  return (
    <>
      <div className="panel">
        <h3>Window Definitions</h3>
        <div className="list" style={{ marginBottom: 8 }}>
          {windowDefs.map((w) => (
            <div
              key={w.id}
              className={`list-item ${activeWindowDefId === w.id ? "active" : ""}`}
              onClick={() => {
                setActiveWindowDefId(w.id);
                setTool("place-window");
              }}
            >
              <span className="item-label">
                {w.name ?? "(unnamed)"}{" "}
                <span className="muted">
                  {(w.width ?? 0).toFixed(2)} × {(w.height ?? 0).toFixed(2)} m
                </span>
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeWindow(w.id);
                }}
                style={{ padding: "2px 6px" }}
              >
                ×
              </button>
            </div>
          ))}
          {windowDefs.length === 0 && <div className="muted">No window definitions.</div>}
        </div>
        <button onClick={() => setActiveWindowDefId(addWindow())}>+ Add Window Def</button>
        {activeWindowDefId &&
          (() => {
            const w = windowDefs.find((x) => x.id === activeWindowDefId);
            if (!w) return null;
            return (
              <div style={{ marginTop: 8 }}>
                <div className="row">
                  <label>Name</label>
                  <input
                    value={w.name ?? ""}
                    onChange={(e) => updateWindow(w.id, { name: e.target.value })}
                  />
                </div>
                <div className="row">
                  <label>Width (m)</label>
                  <input
                    type="number"
                    step={0.1}
                    min={0.1}
                    value={w.width ?? 1}
                    onChange={(e) => updateWindow(w.id, { width: parseFloat(e.target.value) })}
                  />
                </div>
                <div className="row">
                  <label>Height (m)</label>
                  <input
                    type="number"
                    step={0.1}
                    min={0.1}
                    value={w.height ?? 1}
                    onChange={(e) => updateWindow(w.id, { height: parseFloat(e.target.value) })}
                  />
                </div>
                <div className="row">
                  <label>Sill (m)</label>
                  <input
                    type="number"
                    step={0.05}
                    min={0}
                    value={w.sill_height ?? 0.9}
                    onChange={(e) =>
                      updateWindow(w.id, { sill_height: parseFloat(e.target.value) })
                    }
                  />
                </div>
                <div className="row">
                  <label>Type</label>
                  <select
                    value={w.window_type}
                    onChange={(e) =>
                      updateWindow(w.id, {
                        window_type: e.target.value as "Fixed" | "Operable",
                      })
                    }
                  >
                    <option value="Fixed">Fixed</option>
                    <option value="Operable">Operable</option>
                  </select>
                </div>
              </div>
            );
          })()}
      </div>

      <div className="panel">
        <h3>Door Definitions</h3>
        <div className="list" style={{ marginBottom: 8 }}>
          {doorDefs.map((d) => (
            <div
              key={d.id}
              className={`list-item ${activeDoorDefId === d.id ? "active" : ""}`}
              onClick={() => {
                setActiveDoorDefId(d.id);
                setTool("place-door");
              }}
            >
              <span className="item-label">
                {d.name ?? "(unnamed)"}{" "}
                <span className="muted">
                  {d.width.toFixed(2)} × {d.height.toFixed(2)} m
                </span>
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeDoor(d.id);
                }}
                style={{ padding: "2px 6px" }}
              >
                ×
              </button>
            </div>
          ))}
          {doorDefs.length === 0 && <div className="muted">No door definitions.</div>}
        </div>
        <button onClick={() => setActiveDoorDefId(addDoor())}>+ Add Door Def</button>
        {activeDoorDefId &&
          (() => {
            const d = doorDefs.find((x) => x.id === activeDoorDefId);
            if (!d) return null;
            return (
              <div style={{ marginTop: 8 }}>
                <div className="row">
                  <label>Name</label>
                  <input
                    value={d.name ?? ""}
                    onChange={(e) => updateDoor(d.id, { name: e.target.value })}
                  />
                </div>
                <div className="row">
                  <label>Width (m)</label>
                  <input
                    type="number"
                    step={0.05}
                    min={0.1}
                    value={d.width}
                    onChange={(e) => updateDoor(d.id, { width: parseFloat(e.target.value) })}
                  />
                </div>
                <div className="row">
                  <label>Height (m)</label>
                  <input
                    type="number"
                    step={0.05}
                    min={0.1}
                    value={d.height}
                    onChange={(e) => updateDoor(d.id, { height: parseFloat(e.target.value) })}
                  />
                </div>
                <div className="row">
                  <label>Type</label>
                  <select
                    value={d.door_type}
                    onChange={(e) =>
                      updateDoor(d.id, {
                        door_type: e.target.value as "Door" | "Glass Door" | "Overhead Door",
                      })
                    }
                  >
                    <option value="Door">Door</option>
                    <option value="Glass Door">Glass Door</option>
                    <option value="Overhead Door">Overhead Door</option>
                  </select>
                </div>
              </div>
            );
          })()}
      </div>
    </>
  );
}
