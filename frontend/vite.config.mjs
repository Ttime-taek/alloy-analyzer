import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Production UI is built to frontend/dist and served by api_server on :8000.
export default defineConfig({
  plugins: [react()]
});
