import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  PoseExtractionStatus,
  ScaleKind,
  extractFloorplan,
  getStatus,
  saveFloorplan,
} from "./api";

interface Story {
  geometry: {
    vertices: { id: string; x: number; y: number }[];
  };
}

interface Floorplan {
  stories: Story[];
  [key: string]: unknown;
}

const MIN_IMAGES = 4;
const MAX_IMAGES = 10;

interface Props {
  onLoaded?: () => void;
}

export function PhotoImportPage({ onLoaded }: Props): JSX.Element {
  const [files, setFiles] = useState<File[]>([]);
  const [scaleKind, setScaleKind] = useState<ScaleKind>("total_height");
  const [scaleValue, setScaleValue] = useState<number>(9);
  const [fch, setFch] = useState<number>(3);
  const [snap, setSnap] = useState<boolean>(true);
  const [status, setStatus] = useState<PoseExtractionStatus | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Floorplan | null>(null);

  useEffect(() => {
    getStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const thumbs = useMemo(
    () => files.map((f) => ({ name: f.name, url: URL.createObjectURL(f) })),
    [files],
  );
  useEffect(
    () => () => thumbs.forEach((t) => URL.revokeObjectURL(t.url)),
    [thumbs],
  );

  const onDrop = useCallback((ev: React.DragEvent<HTMLDivElement>) => {
    ev.preventDefault();
    const incoming = Array.from(ev.dataTransfer.files).filter((f) =>
      /\.(jpe?g|png)$/i.test(f.name),
    );
    setFiles((prev) => [...prev, ...incoming].slice(0, MAX_IMAGES));
  }, []);

  const canSubmit =
    !busy && files.length >= MIN_IMAGES && files.length <= MAX_IMAGES && scaleValue > 0;

  const handleExtract = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const plan = (await extractFloorplan(files, {
        kind: scaleKind,
        value: scaleValue,
        floor_to_ceiling_height: fch,
        snap_orthogonal: snap,
      })) as Floorplan;
      setResult(plan);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleLoadIntoEditor = async () => {
    if (!result) return;
    setBusy(true);
    setError(null);
    try {
      await saveFloorplan(result);
      onLoaded?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const downloadJson = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "imported_floorplan.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="photo-import">
      <h2>Import building geometry from photos</h2>
      {status && !status.cuda_available && status.torch_available && (
        <p className="warn">
          CUDA not detected — DUSt3R will run on CPU and may be very slow.
        </p>
      )}
      {status && !status.torch_available && (
        <p className="warn">
          PyTorch / DUSt3R not installed on the server. Install with{" "}
          <code>pip install -e .[dust3r]</code>.
        </p>
      )}

      <div
        className="dropzone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
      >
        <p>
          Drag and drop {MIN_IMAGES}–{MAX_IMAGES} exterior photos here, or{" "}
          <label className="link">
            browse
            <input
              type="file"
              accept="image/jpeg,image/png"
              multiple
              hidden
              onChange={(e) => {
                const incoming = Array.from(e.target.files || []);
                setFiles((prev) => [...prev, ...incoming].slice(0, MAX_IMAGES));
                e.target.value = "";
              }}
            />
          </label>
          .
        </p>
        <p className="dim">{files.length} / {MAX_IMAGES} selected</p>
      </div>

      {thumbs.length > 0 && (
        <div className="thumb-strip">
          {thumbs.map((t, i) => (
            <div key={t.url} className="thumb">
              <img src={t.url} alt={t.name} />
              <button
                className="thumb-remove"
                onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
              >
                x
              </button>
            </div>
          ))}
        </div>
      )}

      <fieldset className="scale-form">
        <legend>Real-world scale reference</legend>
        <label>
          <input
            type="radio"
            checked={scaleKind === "total_height"}
            onChange={() => setScaleKind("total_height")}
          />
          Total building height
        </label>
        <label>
          <input
            type="radio"
            checked={scaleKind === "wall_length"}
            onChange={() => setScaleKind("wall_length")}
          />
          Longest wall length
        </label>
        <label>
          Value (m):
          <input
            type="number"
            min={0.1}
            step={0.1}
            value={scaleValue}
            onChange={(e) => setScaleValue(parseFloat(e.target.value) || 0)}
          />
        </label>
        <label>
          Floor-to-ceiling height (m):
          <input
            type="number"
            min={0.1}
            step={0.1}
            value={fch}
            onChange={(e) => setFch(parseFloat(e.target.value) || 0)}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={snap}
            onChange={(e) => setSnap(e.target.checked)}
          />
          Snap footprint edges to orthogonal
        </label>
      </fieldset>

      <div className="actions">
        <button disabled={!canSubmit} onClick={handleExtract}>
          {busy ? "Extracting…" : "Extract floorplan"}
        </button>
        {result && (
          <>
            <button disabled={busy} onClick={handleLoadIntoEditor}>
              Load into editor
            </button>
            <button disabled={busy} onClick={downloadJson}>
              Download JSON
            </button>
          </>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {result && <FootprintPreview floorplan={result} />}
    </div>
  );
}

function FootprintPreview({ floorplan }: { floorplan: Floorplan }): JSX.Element {
  const story = floorplan.stories[0];
  const verts = story?.geometry?.vertices ?? [];
  if (verts.length < 3) {
    return <p className="dim">No footprint to preview.</p>;
  }
  const xs = verts.map((v) => v.x);
  const ys = verts.map((v) => v.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const pad = Math.max((maxX - minX) * 0.1, 1);
  const W = maxX - minX + 2 * pad;
  const H = maxY - minY + 2 * pad;
  const pts = verts
    .map((v) => `${v.x - minX + pad},${maxY - v.y + pad}`)
    .join(" ");

  return (
    <div className="preview">
      <h3>
        Recovered footprint — {floorplan.stories.length} stor
        {floorplan.stories.length === 1 ? "y" : "ies"}
      </h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="footprint-svg">
        <polygon
          points={pts}
          fill="rgba(79, 156, 255, 0.2)"
          stroke="#4f9cff"
          strokeWidth={Math.max(W, H) * 0.005}
        />
      </svg>
      <p className="dim">
        {verts.length} vertices · ~{(maxX - minX).toFixed(1)} m ×{" "}
        {(maxY - minY).toFixed(1)} m
      </p>
    </div>
  );
}
