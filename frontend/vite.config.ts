import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: resolve(__dirname, "../presto_geometry/web/static"),
    emptyOutDir: true,
  },
  test: {
    environment: "node",
    globals: true,
  },
});
