import { defineConfig } from "vite";

export default defineConfig({
  base: "./", // GitHub Pages serves the site from /<repo>/
  publicDir: "../data",
  build: { target: "es2022" },
});
