import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return "react-vendor";
          if (/node_modules\/(cytoscape|cytoscape-[^/]+|layout-base|cose-base)\//.test(id)) return "graph-vendor";
          if (/node_modules\/(recharts|d3-[^/]+|victory-vendor)\//.test(id)) return "charts-vendor";
          if (/node_modules\/motion\//.test(id)) return "motion-vendor";
          if (/node_modules\/lucide-react\//.test(id)) return "icons-vendor";
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
