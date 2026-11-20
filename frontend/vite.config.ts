import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": resolve(process.cwd(), "src") },
  },
  base: "/static/a2a/",
  build: {
    outDir: resolve(process.cwd(), "../web/a2a"),
    emptyOutDir: true,
    lib: {
      entry: resolve(process.cwd(), "src/main.tsx"),
      formats: ["es"],
      fileName: () => "agent-workspace.js",
    },
    rollupOptions: {
      output: { assetFileNames: "agent-workspace.[ext]" },
    },
  },
});
