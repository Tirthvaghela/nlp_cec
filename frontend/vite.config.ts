/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to the FastAPI backend, so the browser talks to one origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.VITE_PROXY_TARGET ?? "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          editor: ["@tiptap/react", "@tiptap/starter-kit", "@tiptap/extension-table", "@tiptap/extensions"],
          react: ["react", "react-dom", "react-router-dom", "@tanstack/react-query"],
          ui: ["@radix-ui/react-dialog", "@radix-ui/react-alert-dialog", "@radix-ui/react-dropdown-menu", "@radix-ui/react-tabs", "lucide-react", "sonner"],
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
