import { useFloorplan } from "../state/useFloorplan";

export function StoriesPanel() {
  const stories = useFloorplan((s) => s.doc.stories);
  const activeStoryId = useFloorplan((s) => s.activeStoryId);
  const addStory = useFloorplan((s) => s.addStory);
  const removeStory = useFloorplan((s) => s.removeStory);
  const setActiveStory = useFloorplan((s) => s.setActiveStory);
  const updateStory = useFloorplan((s) => s.updateStory);

  const active = stories.find((s) => s.id === activeStoryId) ?? null;

  return (
    <div className="panel">
      <h3>Stories</h3>
      <div className="list" style={{ marginBottom: 8 }}>
        {stories.map((s) => (
          <div
            key={s.id}
            className={`list-item ${s.id === activeStoryId ? "active" : ""}`}
            onClick={() => setActiveStory(s.id)}
          >
            <span className="item-label">
              <span className="swatch" style={{ background: s.color ?? "#888" }} />
              {s.name ?? "(unnamed)"}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`Delete story "${s.name}"?`)) removeStory(s.id);
              }}
              style={{ padding: "2px 6px" }}
            >
              ×
            </button>
          </div>
        ))}
        {stories.length === 0 && (
          <div className="muted">No stories yet. Add one below.</div>
        )}
      </div>
      <button onClick={() => addStory()}>+ Add Story</button>

      {active && (
        <div style={{ marginTop: 12 }}>
          <h3>Active Story</h3>
          <div className="row">
            <label>Name</label>
            <input
              value={active.name ?? ""}
              onChange={(e) => updateStory(active.id, { name: e.target.value })}
            />
          </div>
          <div className="row">
            <label>Ceiling (m)</label>
            <input
              type="number"
              step={0.1}
              min={0}
              value={active.floor_to_ceiling_height ?? 3}
              onChange={(e) =>
                updateStory(active.id, {
                  floor_to_ceiling_height: parseFloat(e.target.value),
                })
              }
            />
          </div>
          <div className="row">
            <label>Multiplier</label>
            <input
              type="number"
              step={1}
              min={1}
              value={active.multiplier ?? 1}
              onChange={(e) =>
                updateStory(active.id, { multiplier: parseInt(e.target.value, 10) || 1 })
              }
            />
          </div>
          <div className="row">
            <label>Below plenum (m)</label>
            <input
              type="number"
              step={0.1}
              min={0}
              value={active.below_floor_plenum_height ?? 0}
              onChange={(e) =>
                updateStory(active.id, {
                  below_floor_plenum_height: parseFloat(e.target.value),
                })
              }
            />
          </div>
          <div className="row">
            <label>Above plenum (m)</label>
            <input
              type="number"
              step={0.1}
              min={0}
              value={active.above_ceiling_plenum_height ?? 0}
              onChange={(e) =>
                updateStory(active.id, {
                  above_ceiling_plenum_height: parseFloat(e.target.value),
                })
              }
            />
          </div>
        </div>
      )}
    </div>
  );
}
