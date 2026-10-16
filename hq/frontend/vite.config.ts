import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],build:{rollupOptions:{output:{manualChunks:{charts:['recharts'],editor:['@tiptap/react','@tiptap/starter-kit','@tiptap/extension-table']}}}}});
