import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte(), tailwindcss()],
  server: {
    // 4.3: dev and production stay on one origin. The original reason was the
    // session cookie, which is gone; it stays because same-origin removes a
    // whole class of bug that only shows up after the deploy — CORS, proxy
    // headers on the SSE, relative asset paths.
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${process.env.PORT ?? 3000}`,
        changeOrigin: true,
      },
    },
  },
});
