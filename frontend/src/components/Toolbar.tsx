import { useSelection, type ToolId } from "../state/selection";

const TOOLS: { id: ToolId; label: string; hotkey: string }[] = [
  { id: "select", label: "Select", hotkey: "V" },
  { id: "draw-room", label: "Draw Room", hotkey: "R" },
  { id: "place-window", label: "Window", hotkey: "W" },
  { id: "place-door", label: "Door", hotkey: "D" },
  { id: "erase", label: "Erase", hotkey: "X" },
];

export function Toolbar() {
  const tool = useSelection((s) => s.tool);
  const setTool = useSelection((s) => s.setTool);
  const snapEnabled = useSelection((s) => s.snapEnabled);
  const setSnapEnabled = useSelection((s) => s.setSnapEnabled);

  return (
    <div className="toolbar">
      {TOOLS.map((t) => (
        <button
          key={t.id}
          className={tool === t.id ? "active" : ""}
          onClick={() => setTool(t.id)}
          title={`${t.label} (${t.hotkey})`}
        >
          {t.label}
        </button>
      ))}
      <label style={{ marginLeft: 12, color: "var(--text-dim)", fontSize: 12 }}>
        <input
          type="checkbox"
          checked={snapEnabled}
          onChange={(e) => setSnapEnabled(e.target.checked)}
        />{" "}
        Snap
      </label>
    </div>
  );
}
