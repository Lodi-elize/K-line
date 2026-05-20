import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("recharts") || id.includes("d3-")) return "charts";
          if (id.includes("lucide-react")) return "icons";
          if (id.includes("react") || id.includes("react-dom")) return "react-vendor";
        }
      }
    }
  },
  server: {
    host: "127.0.0.1",
    port: 8081,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:9091",
      "/ws": {
        target: "ws://127.0.0.1:9091",
        ws: true
      }
    }
  }
});
