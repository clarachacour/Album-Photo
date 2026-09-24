import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // `import x from "@/lib/api"` → src/lib/api
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  // Only variables starting with REACT_APP_ are exposed to the browser
  // (read with import.meta.env.REACT_APP_...). The prefix is kept from Create
  // React App so the variables already set on Vercel keep working as is.
  envPrefix: "REACT_APP_",
  server: { port: 3000 },
  preview: { port: 3000 },
  // "build" (not Vite's default "dist") so Vercel serves the same folder as before.
  build: { outDir: "build" },
});
