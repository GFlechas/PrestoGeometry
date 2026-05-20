import { Suspense, lazy } from "react";
import { create } from "zustand";
import { EditorCanvas } from "./EditorCanvas";

const PreviewCanvas3D = lazy(() =>
  import("./PreviewCanvas3D").then((m) => ({ default: m.PreviewCanvas3D })),
);

export type ViewMode = "2d" | "3d";

interface ViewState {
  mode: ViewMode;
  setMode: (m: ViewMode) => void;
}

export const useViewMode = create<ViewState>((set) => ({
  mode: "2d",
  setMode: (mode) => set({ mode }),
}));

export function ViewTabs() {
  const mode = useViewMode((s) => s.mode);
  const setMode = useViewMode((s) => s.setMode);
  return (
    <div className="tabs">
      <button className={mode === "2d" ? "active" : ""} onClick={() => setMode("2d")}>
        2D Editor
      </button>
      <button className={mode === "3d" ? "active" : ""} onClick={() => setMode("3d")}>
        3D Preview
      </button>
    </div>
  );
}

export function ViewBody() {
  const mode = useViewMode((s) => s.mode);
  if (mode === "3d") {
    return (
      <Suspense fallback={<div className="overlay">Loading 3D…</div>}>
        <PreviewCanvas3D />
      </Suspense>
    );
  }
  return <EditorCanvas />;
}
