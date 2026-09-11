import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

/** Serve-only bridge: the browser never receives the sidecar session token. */
export function browserSidecar(): Plugin {
  return {
    name: "stt-isolated-browser-development",
    apply: "serve",
    configureServer(server) {
      const root = resolve(fileURLToPath(new URL("../../..", import.meta.url)));
      const token = randomBytes(32).toString("hex");
      const python = process.env.STT_DEV_PYTHON || resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
      const child = spawn(python, [resolve(root, "scripts/browser-dev-sidecar.py")], {
        cwd: root, windowsHide: true, stdio: ["pipe", "pipe", "pipe"],
        env: { ...process.env, PYTHONPATH: resolve(root, "sidecar"), STT_BROWSER_SESSION_TOKEN: token },
      });
      let output = "";
      let readyError = "";
      const ready = new Promise<number>((accept, reject) => {
        const timer = setTimeout(() => reject(new Error("本地预览服务启动超时")), 30000);
        child.stdout.on("data", chunk => {
          output += String(chunk);
          const match = output.match(/STT_BROWSER_READY:(\d+)/);
          if (match) { clearTimeout(timer); accept(Number(match[1])); }
        });
        child.once("error", () => { clearTimeout(timer); reject(new Error("无法启动 Python，请检查 .venv 或 STT_DEV_PYTHON")); });
        child.once("exit", () => { clearTimeout(timer); reject(new Error("本地预览服务已退出")); });
      });
      void ready.catch(error => { readyError = String(error); server.config.logger.error(readyError); });
      // Do not forward process output or environment values into browser responses.
      child.stderr.on("data", () => {});
      const close = () => child.stdin.end();
      server.httpServer?.once("close", close);
      process.once("exit", close);
      server.middlewares.use("/__desktop_dev", async (req, res) => {
        res.setHeader("Cache-Control", "no-store");
        const host = `127.0.0.1:${server.config.server.port}`;
        if (req.headers.host !== host || req.headers["x-stt-dev"] !== "1" ||
            (req.headers.origin && req.headers.origin !== `http://${host}`)) {
          res.statusCode = 403; res.end("本地开发请求被拒绝"); return;
        }
        // Isolated project editing and scheduling only; no filesystem export/import or auth.
        const url = req.url || "";
        const editorPath = /^\/v1\/(?:timetable\/(?:settings|templates(?:\/[\w-]+)?)|data\/[a-z_]+(?:\/[\w-]+)?)(?:\?|$)/.test(url);
        const runPath = /^\/v1\/(?:validation\/preflight|scheduling\/(?:rounds(?:\/[\w-]+\/cancel)?|candidates)|timetables\/(?:[\w-]+|validate-move|manual-fork))(?:\?|$)/.test(url);
        const exportHistory = req.method === 'GET' && url === '/v1/exports';
        const planningPath = (req.method === 'PUT' && url === '/v1/planning/tasks') || (req.method === 'POST' && url === '/v1/planning/copy-class');
        if (!editorPath && !runPath && !exportHistory && !planningPath) {
          res.statusCode = 404; res.end("此操作不在浏览器预览范围内"); return;
        }
        try {
          if (readyError) throw new Error(readyError);
          const port = await ready;
          const chunks: Buffer[] = [];
          let size = 0;
          for await (const chunk of req) {
            size += chunk.length;
            if (size > 2 * 1024 * 1024) throw new Error("请求过大");
            chunks.push(Buffer.from(chunk));
          }
          const response = await fetch(`http://127.0.0.1:${port}${url}`, {
            method: req.method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
            body: chunks.length ? Buffer.concat(chunks) : undefined,
          });
          res.statusCode = response.status;
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          res.end(await response.text());
        } catch {
          res.statusCode = 503;
          res.end(JSON.stringify({error:{message:"本地预览服务暂不可用，请检查开发终端并重启 dev:browser。"}}));
        }
      });
    },
  };
}
