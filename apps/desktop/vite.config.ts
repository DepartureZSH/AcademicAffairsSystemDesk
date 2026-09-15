import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { browserSidecar } from "./dev/browserSidecar";

export default defineConfig(({mode}) => ({
  plugins: [vue(), ...(mode === "browser-dev" ? [browserSidecar()] : [])],
  clearScreen: false,
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true,
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: "es2022",
    minify: "oxc",
    sourcemap: true,
  },
}));
