// Separate development entry: never imported by index.html or the desktop release.
import { createApp } from "vue";
import { mockIPC } from "@tauri-apps/api/mocks";
import DevApp from "./DevApp.vue";
import "./styles.css";
import "./web-timetable/web-timetable.css";

if (!import.meta.env.DEV || import.meta.env.MODE !== "browser-dev") {
  throw new Error("本地预览仅在 dev:browser 模式开放");
}
mockIPC(async (command, args) => {
  if (command !== "sidecar_request") throw new Error("此操作需要桌面应用，浏览器仅提供页面预览和本地数据编辑。");
  const { request } = args as {request:{path:string;method:string;body?:unknown}};
  const response = await fetch(`/__desktop_dev${request.path}`, {
    method: request.method,
    headers: {"X-STT-Dev":"1", "Content-Type":"application/json"},
    body: request.body === undefined ? undefined : JSON.stringify(request.body),
  });
  const text = await response.text();
  if (!response.ok) throw text;
  return JSON.parse(text);
});
createApp(DevApp).mount("#app");
