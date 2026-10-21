import { defineConfig } from 'vite'

export default defineConfig(({ command }) => ({
  base: './',              // GitHub Pages serves the site from /<repo>/
  publicDir: command === 'serve' ? '../data' : false,
  build: { target: 'es2022' },
}))
