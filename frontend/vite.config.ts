import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = process.env.QUIETWATER_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: "127.0.0.1",
    proxy: { "/api": { target: api, changeOrigin: true } },
  },
});
