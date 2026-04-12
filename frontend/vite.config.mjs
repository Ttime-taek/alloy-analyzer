import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import checker from "vite-plugin-checker";

// Backend FastAPI는 http://127.0.0.1:8000 에서 동작한다고 가정합니다.
// API를 외부에 열려면 서버 쪽은 --host 0.0.0.0 (또는 python api_server.py).
// 다른 PC에서 http://<이머신IP>:5173 으로 접속할 때도, 프록시는 이 PC의 127.0.0.1:8000 으로 전달됩니다.
// (골프 스윙 앱은 5174 — 이 포트와 겹치지 않게 동시 실행 가능)

/** LAN에서 접속할 때 브라우저·HMR이 붙을 호스트 (IP 바뀌면 VITE_DEV_LAN_HOST 로 덮어쓰기) */
const devLanHost = process.env.VITE_DEV_LAN_HOST || "192.168.82.215";
const devPort = 5173;

/** 백엔드가 꺼져 있을 때 http-proxy가 500을 내 콘솔에 Failed to load resource가 쌓이는 것을 줄이기 위해 503 JSON으로 응답 */
function configureProxyFallback(proxy) {
  proxy.on("error", (_err, _req, res) => {
    if (res && typeof res.writeHead === "function" && !res.headersSent) {
      res.writeHead(503, { "Content-Type": "application/json; charset=utf-8" });
      res.end(
        JSON.stringify({
          detail:
            "백엔드(127.0.0.1:8000)에 연결할 수 없습니다. 터미널에서 python api_server.py 실행 후 새로고침하세요.",
          offline: true
        })
      );
    }
  });
}

export default defineConfig({
  plugins: [
    react(),
    // 개발 서버에서 ESLint(접근성 jsx-a11y 등) 결과를 브라우저 오버레이로 표시 — 디자인·a11y 리뷰에 가깝게
    checker({
      eslint: {
        useFlatConfig: true,
        lintCommand: 'eslint "./src/**/*.{js,jsx}"',
      },
    }),
  ],
  server: {
    // 0.0.0.0: 모든 NIC — http://192.168.82.215:5173/ 등으로 접속
    host: "0.0.0.0",
    port: devPort,
    strictPort: true,
    // 다른 기기에서 LAN IP로 열 때 HMR(WebSocket)이 localhost로 가지 않도록
    hmr: {
      host: devLanHost,
      port: devPort,
      clientPort: devPort
    },
    proxy: {
      "/api": {
        // localhost는 Windows에서 IPv6(::1)로 잡혀 uvicorn(127.0.0.1)과 안 맞는 경우가 있어 127.0.0.1 고정
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        configure: configureProxyFallback
      },
      "/docs": {
        // FastAPI Swagger UI — /docs 링크가 Vite SPA로 가지 않도록 백엔드로 프록시
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        configure: configureProxyFallback
      },
      "/openapi.json": {
        // Swagger가 참조하는 OpenAPI 스펙도 함께 프록시
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        configure: configureProxyFallback
      }
    }
  },
  preview: {
    // npm run build 후 preview도 LAN에서 열기
    host: true,
    port: 4173
  }
});

