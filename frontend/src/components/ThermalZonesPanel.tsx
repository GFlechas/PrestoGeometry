import { useFloorplan } from "../state/useFloorplan";

export function ThermalZonesPanel() {
  const zones = useFloorplan((s) => s.doc.thermal_zones);
  const addZone = useFloorplan((s) => s.addThermalZone);
  const removeZone = useFloorplan((s) => s.removeThermalZone);
  const updateZone = useFloorplan((s) => s.updateThermalZone);

  return (
    <div className="panel">
      <h3>Thermal Zones</h3>
      <div className="list" style={{ marginBottom: 8 }}>
        {zones.map((z) => (
          <div key={z.id} className="list-item">
            <span className="item-label" style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <input
                type="color"
                value={z.color ?? "#88B7D5"}
                onChange={(e) => updateZone(z.id, { color: e.target.value })}
                style={{ width: 24, height: 18, padding: 0, border: "none", background: "none" }}
              />
              <input
                value={z.name ?? ""}
                onChange={(e) => updateZone(z.id, { name: e.target.value })}
                style={{ flex: 1 }}
              />
            </span>
            <button onClick={() => removeZone(z.id)} style={{ padding: "2px 6px" }}>
              ×
            </button>
          </div>
        ))}
        {zones.length === 0 && <div className="muted">No thermal zones yet.</div>}
      </div>
      <button onClick={() => addZone()}>+ Add Zone</button>
    </div>
  );
}
