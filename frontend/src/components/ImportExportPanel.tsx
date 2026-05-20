import { useRef, useState } from "react";
import { useFloorplan } from "../state/useFloorplan";
import {
  downloadAsFile,
  fetchServerFloorplan,
  loadFromFile,
  postServerFloorplan,
} from "../io/floorspaceJson";
import { validateFloorplan } from "../schema/validate";

type Status =
  | { kind: "idle" }
  | { kind: "ok"; message: string }
  | { kind: "err"; errors: { path: string; message: string }[] };

export function ImportExportPanel() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const doc = useFloorplan((s) => s.doc);
  const load = useFloorplan((s) => s.load);
  const reset = useFloorplan((s) => s.reset);

  async function handleFile(file: File) {
    const result = await loadFromFile(file);
    if (result.doc) {
      load(result.doc);
      setStatus({ kind: "ok", message: `Loaded ${file.name}` });
    } else {
      setStatus({ kind: "err", errors: result.errors });
    }
  }

  async function handleExport() {
    const result = await validateFloorplan(doc);
    if (!result.valid) {
      setStatus({ kind: "err", errors: result.errors });
      return;
    }
    downloadAsFile(doc);
    setStatus({ kind: "ok", message: "Downloaded floorplan.json" });
  }

  async function handleSaveServer() {
    const result = await validateFloorplan(doc);
    if (!result.valid) {
      setStatus({ kind: "err", errors: result.errors });
      return;
    }
    const res = await postServerFloorplan(doc);
    if (res.ok) {
      setStatus({ kind: "ok", message: "Saved to server" });
    } else {
      setStatus({
        kind: "err",
        errors: (res.errors ?? []).map((e) => ({
          path: e.path.join("/") || "/",
          message: e.message,
        })),
      });
    }
  }

  async function handleLoadServer() {
    try {
      const remote = await fetchServerFloorplan();
      load(remote);
      setStatus({ kind: "ok", message: "Loaded from server" });
    } catch (err) {
      setStatus({ kind: "err", errors: [{ path: "/", message: String(err) }] });
    }
  }

  return (
    <div className="panel">
      <h3>Import / Export</h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <button onClick={() => fileRef.current?.click()}>Import JSON…</button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
            e.target.value = "";
          }}
        />
        <button onClick={handleExport}>Download JSON</button>
        <button onClick={handleSaveServer}>Save to Server</button>
        <button onClick={handleLoadServer}>Load from Server</button>
        <button
          onClick={() => {
            if (confirm("Clear the whole floorplan?")) {
              reset();
              setStatus({ kind: "ok", message: "Cleared" });
            }
          }}
        >
          New / Clear
        </button>
      </div>
      {status.kind === "ok" && (
        <div style={{ color: "var(--good)", fontSize: 12, marginTop: 8 }}>
          {status.message}
        </div>
      )}
      {status.kind === "err" && (
        <div className="error-list" style={{ marginTop: 8 }}>
          <strong>Validation failed:</strong>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {status.errors.slice(0, 12).map((e, i) => (
              <li key={i}>
                <code>{e.path}</code>: {e.message}
              </li>
            ))}
            {status.errors.length > 12 && (
              <li>…and {status.errors.length - 12} more</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
