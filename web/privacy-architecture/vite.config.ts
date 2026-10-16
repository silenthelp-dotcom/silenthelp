import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
// Served by Flask under silenthelp.org: page at /privacy-architecture, files at /static/explore/privacy/.
export default defineConfig({plugins:[react()],base:'/static/explore/privacy/',build:{outDir:'../../static/explore/privacy',emptyOutDir:true}});
