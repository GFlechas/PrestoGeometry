import React, { useState } from "react";
import { PhotoImportPage } from "./photoImport/PhotoImportPage";

type Tab = "editor" | "photoImport";

export function App(): JSX.Element {
  const [tab, setTab] = useState<Tab>("photoImport");

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>PrestoGeometry</h1>
        <nav className="app-nav">
          <button
            className={tab === "editor" ? "active" : ""}
            onClick={() => setTab("editor")}
          >
            Floorplan Editor
          </button>
          <button
            className={tab === "photoImport" ? "active" : ""}
            onClick={() => setTab("photoImport")}
          >
            Import from Photos
          </button>
        </nav>
      </header>
      <main className="app-main">
        {tab === "editor" ? <FloorplanEditorPlaceholder /> : <PhotoImportPage onLoaded={() => setTab("editor")} />}
      </main>
    </div>
  );
}

function FloorplanEditorPlaceholder(): JSX.Element {
  return (
    <div className="placeholder">
      <p>The floorspace.js editor lives here. Use “Import from Photos” to
      seed it with geometry recovered from building exterior photos, or open
      an existing plan via the API at <code>GET /api/floorplan</code>.</p>
    </div>
  );
}
