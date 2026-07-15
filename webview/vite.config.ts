import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  base: './',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // dev 下把后端接口转发到 ling/backend FastAPI :8765，绕开 CORS、免硬编码地址
    proxy: {
      // SSE 流式聊天：放 /chat 前，确保 text/event-stream 不被缓冲
      '/chat/stream': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/chat': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/tts': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/history': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/reset': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/asr': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/video/frame': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/stickers': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      // V0.2 新增：个人资料 + 朋友圈（缺失则 dev 下走 SPA fallback，moments 退回 mock、profile 不持久）
      '/profile': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/moments': { target: 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
})
