import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": resolve(process.cwd(), "src") } },
  base: "/static/app/",
  build: {
    outDir: resolve(process.cwd(), "../web/app"),
    emptyOutDir: true,
    lib: {
      entry: resolve(process.cwd(), "src/main.tsx"),
      formats: ["es"],
      fileName: () => "workspace.js",
    },
    cssCodeSplit: false,
    rollupOptions: {
      output: { assetFileNames: "workspace.[ext]" },
    },
  },
});
