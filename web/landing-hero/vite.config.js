import {defineConfig} from 'vite';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({plugins:[tailwindcss()],base:'/static/cinematic/hero/',build:{outDir:'../../static/cinematic/hero',emptyOutDir:true,rollupOptions:{input:'src.jsx',output:{entryFileNames:'hero.js',chunkFileNames:'[name]-[hash].js',assetFileNames:'hero.[ext]'}}}});
