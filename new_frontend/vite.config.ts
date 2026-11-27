/// <reference types="vitest/config" />
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `npm run dev` serves on :5173 and proxies /api to a backend on :8000
// (docker compose publishes it there), mirroring what nginx does in the image.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: backend,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
        configure: (proxy) => {
          // The backend's CSRF check compares Origin with PUBLIC_BASE_URL; the
          // dev server is same-origin from the browser's point of view.
          proxy.on("proxyReq", (req) => req.removeHeader("origin"));
        },
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom", "@tanstack/react-query", "zustand"],
          graph: ["@xyflow/react", "@dagrejs/dagre"],
          ui: [
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-accordion",
            "@radix-ui/react-tabs",
            "@radix-ui/react-tooltip",
            "@radix-ui/react-popover",
            "cmdk",
            "sonner",
          ],
          markdown: ["react-markdown"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
