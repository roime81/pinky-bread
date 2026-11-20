import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  base: "/static/a2a/",
  build: {
    outDir: resolve(__dirname, "../web/a2a"),
    emptyOutDir: true,
    lib: {
      entry: resolve(__dirname, "src/main.tsx"),
      formats: ["es"],
      fileName: () => "agent-workspace.js",
    },
    rollupOptions: {
      output: { assetFileNames: "agent-workspace.[ext]" },
    },
  },
});
