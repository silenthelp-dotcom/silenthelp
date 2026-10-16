import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// HQ_BASE lets the app be served under a path, e.g. HQ_BASE=/hq1/ for silenthelp.org/hq1.
export default defineConfig({base:process.env.HQ_BASE||'/',plugins:[react()],build:{rollupOptions:{output:{manualChunks:{charts:['recharts'],editor:['@tiptap/react','@tiptap/starter-kit','@tiptap/extension-table']}}}}});
