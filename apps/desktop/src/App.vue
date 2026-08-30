<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { confirm, open, save } from "@tauri-apps/plugin-dialog";
import CalendarView from "./components/CalendarView.vue";
import ConstraintsView from "./components/ConstraintsView.vue";
import PlanningView from "./components/PlanningView.vue";
import SchoolDataView from "./components/SchoolDataView.vue";
import SchedulingView from "./components/SchedulingView.vue";
import TimetableView from "./components/TimetableView.vue";
import BackupsView from "./components/BackupsView.vue";
import ImportView from "./components/ImportView.vue";
import { accessGate, type GateStatus } from "./lib/accessGate";
import { updater, type UpdateStatus } from "./lib/updater";
import {
  localApi,
  formatLocalError,
  startSidecar,
  stopSidecar,
  type HealthStatus,
  type ProjectInfo,
  type RuntimeStatus,
} from "./lib/sidecar";

type NavItem = { key: string; label: string; enabled: boolean };
type AuthMode = "signin" | "signup" | "reset";

const navItems: NavItem[] = [
  { key: "workspace", label: "项目工作台", enabled: true },
  { key: "calendar", label: "学期与作息", enabled: true },
  { key: "school", label: "基础资料", enabled: true },
  { key: "imports", label: "批量导入", enabled: true },
  { key: "planning", label: "课程计划", enabled: true },
  { key: "constraints", label: "约束配置", enabled: true },
  { key: "scheduling", label: "排课运行", enabled: true },
  { key: "timetables", label: "课表与导出", enabled: true },
  { key: "backups", label: "备份恢复", enabled: true },
];

const gate = ref<GateStatus | null>(null);
const gateBusy = ref(true);
const authMode = ref<AuthMode>("signin");
const email = ref("");
const password = ref("");
const enterpriseKey = ref("");
const gateError = ref("");
const gateNotice = ref("");

const runtime = ref<RuntimeStatus | null>(null);
const health = ref<HealthStatus | null>(null);
const projects = ref<Array<Record<string, unknown>>>([]);
const currentProject = ref<ProjectInfo | null>(null);
const projectRevision = ref(0);
const activeView = ref("workspace");
const projectName = ref("");
const workspaceBusy = ref(false);
const workspaceError = ref("");
const workspaceNotice = ref("");
const updateBusy = ref(false);
const availableUpdate = ref<UpdateStatus | null>(null);

const mockServices = computed(() => {
  const serviceModes = health.value?.serviceModes;
  if (serviceModes) {
    return Object.entries(serviceModes)
      .filter(([, mode]) => mode === "mock")
      .map(([name]) => name);
  }
  return gate.value?.license.mode === "mock" ? ["license"] : [];
});

const licenseExpiry = computed(() => {
  const expiresAt = gate.value?.license.expiresAt;
  return expiresAt ? new Date(expiresAt * 1000).toLocaleString("zh-CN") : "尚未激活";
});

const pageTitle = computed(() => {
  if (!gate.value?.canStartSidecar) return "身份与设备授权";
  if (activeView.value === "calendar") return "学期与作息";
  if (activeView.value === "school") return "基础资料";
  if (activeView.value === "imports") return "CSV / Excel 批量导入";
  if (activeView.value === "planning") return "课程计划";
  if (activeView.value === "constraints") return "约束配置";
  if (activeView.value === "scheduling") return "排课运行与候选方案";
  if (activeView.value === "timetables") return "课表查看与手工调整";
  if (activeView.value === "backups") return "备份与恢复";
  return currentProject.value?.name ?? "项目工作台";
});

async function refreshProjects() {
  projects.value = (await localApi.listProjects()).projects;
}

async function bootstrapWorkspace() {
  workspaceBusy.value = true;
  workspaceError.value = "";
  try {
    runtime.value = await startSidecar();
    health.value = await localApi.health();
    await refreshProjects();
  } catch (error) {
    workspaceError.value = formatLocalError(error);
  } finally {
    workspaceBusy.value = false;
  }
}

async function bootstrapGate() {
  gateBusy.value = true;
  gateError.value = "";
  try {
    gate.value = await accessGate.status();
    gateNotice.value = gate.value.auth.message ?? gate.value.license.message ?? "";
    if (gate.value.canStartSidecar) await bootstrapWorkspace();
  } catch (error) {
    gateError.value = String(error);
  } finally {
    gateBusy.value = false;
  }
}

async function submitAuth() {
  gateBusy.value = true;
  gateError.value = "";
  gateNotice.value = "";
  try {
    if (authMode.value === "signin") {
      gate.value = await accessGate.signIn(email.value.trim(), password.value);
      password.value = "";
      gateNotice.value = gate.value.license.message ?? "登录成功";
      if (gate.value.canStartSidecar) await bootstrapWorkspace();
    } else if (authMode.value === "signup") {
      const status = await accessGate.signUp(email.value.trim(), password.value);
      password.value = "";
      gateNotice.value = status.message ?? "注册成功，请登录";
      if (status.authenticated) await bootstrapGate();
      else authMode.value = "signin";
    } else {
      gateNotice.value = await accessGate.requestPasswordReset(email.value.trim());
      authMode.value = "signin";
    }
  } catch (error) {
    gateError.value = String(error);
  } finally {
    gateBusy.value = false;
  }
}

async function activateLicense() {
  if (!enterpriseKey.value.trim()) return;
  gateBusy.value = true;
  gateError.value = "";
  try {
    gate.value = await accessGate.activateLicense(enterpriseKey.value);
    enterpriseKey.value = "";
    gateNotice.value = "当前设备已激活，授权凭证已进入系统凭据库";
    if (gate.value.canStartSidecar) await bootstrapWorkspace();
  } catch (error) {
    gateError.value = String(error);
  } finally {
    gateBusy.value = false;
  }
}

async function signOut() {
  gateBusy.value = true;
  gateError.value = "";
  try {
    if (runtime.value?.running) await stopSidecar();
    runtime.value = null;
    health.value = null;
    currentProject.value = null;
    activeView.value = "workspace";
    gate.value = await accessGate.signOut();
    gateNotice.value = "已退出并清除本地登录会话与授权；设备私钥已保留";
  } catch (error) {
    gateError.value = String(error);
  } finally {
    gateBusy.value = false;
  }
}

async function createProject() {
  const name = projectName.value.trim();
  if (!name) return;
  workspaceBusy.value = true;
  workspaceError.value = "";
  try {
    const result = await localApi.createProject(name);
    currentProject.value = result.project;
    projectRevision.value = result.revision;
    projectName.value = "";
    await refreshProjects();
    health.value = await localApi.health();
  } catch (error) {
    workspaceError.value = formatLocalError(error);
  } finally {
    workspaceBusy.value = false;
  }
}

async function openProject(projectId: string) {
  workspaceBusy.value = true;
  workspaceError.value = "";
  try {
    const result = await localApi.openProject(projectId);
    currentProject.value = result.project;
    projectRevision.value = result.revision;
    health.value = await localApi.health();
  } catch (error) {
    workspaceError.value = formatLocalError(error);
  } finally {
    workspaceBusy.value = false;
  }
}

async function exportProjectArchive() {
  if (!currentProject.value) return;
  const path = await save({
    defaultPath: `${currentProject.value.name}.sttproj`,
    filters: [{ name: "时奕排课项目", extensions: ["sttproj"] }],
  });
  if (!path) return;
  workspaceBusy.value = true;
  workspaceError.value = "";
  workspaceNotice.value = "";
  try {
    const result = await localApi.exportProjectArchive(path, true);
    workspaceNotice.value = `项目包已导出并校验：${String(result.package.fileName)}`;
  } catch (error) {
    workspaceError.value = formatLocalError(error);
  } finally {
    workspaceBusy.value = false;
  }
}

async function importProjectArchive() {
  const path = await open({
    multiple: false,
    directory: false,
    filters: [{ name: "时奕排课项目", extensions: ["sttproj"] }],
  });
  if (typeof path !== "string") return;
  const accepted = await confirm(
    `将校验并导入为一个新的本地项目，不覆盖任何现有项目：\n\n${path}\n\n是否继续？`,
    { title: "确认导入项目", kind: "warning" },
  );
  if (!accepted) return;
  workspaceBusy.value = true;
  workspaceError.value = "";
  workspaceNotice.value = "";
  try {
    const result = await localApi.importProjectArchive({
      archive_path: path,
      imported_name: null,
      confirmed: true,
    });
    currentProject.value = result.project;
    projectRevision.value = result.revision;
    workspaceNotice.value = `已导入并打开项目：${result.project.name}`;
    await refreshProjects();
    health.value = await localApi.health();
  } catch (error) {
    workspaceError.value = formatLocalError(error);
  } finally {
    workspaceBusy.value = false;
  }
}

async function checkForUpdate() {
  updateBusy.value = true;
  workspaceError.value = "";
  try {
    availableUpdate.value = await updater.check();
    workspaceNotice.value = availableUpdate.value.message;
  } catch (error) {
    workspaceError.value = String(error);
  } finally {
    updateBusy.value = false;
  }
}

async function installUpdate() {
  if (!availableUpdate.value?.available) return;
  const accepted = await confirm(
    `已验证版本 ${availableUpdate.value.version} 的 Ed25519 更新签名。安装将关闭并重新启动应用，是否继续？`,
    { title: "安装时奕教务排课更新", kind: "info" },
  );
  if (!accepted) return;
  updateBusy.value = true;
  workspaceError.value = "";
  try {
    await updater.install();
  } catch (error) {
    workspaceError.value = String(error);
    updateBusy.value = false;
  }
}

function applyRestoredProject(project: ProjectInfo, revision: number) {
  currentProject.value = project;
  projectRevision.value = revision;
  void refreshProjects();
}

onMounted(bootstrapGate);
</script>

<template>
  <main class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">时</div>
        <div><strong>时奕教务排课</strong><span>本地桌面版</span></div>
      </div>

      <nav aria-label="主要功能">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: item.key === activeView }"
          :disabled="!item.enabled || !gate?.canStartSidecar || (item.key !== 'workspace' && !currentProject)"
          @click="activeView = item.key"
        >
          <span>{{ item.label }}</span><small v-if="!item.enabled">实施中</small>
        </button>
      </nav>

      <div class="runtime-card">
        <span class="status-dot" :class="runtime?.running ? 'online' : 'offline'"></span>
        <div>
          <strong>{{ runtime?.running ? "本地服务已连接" : "本地服务未启动" }}</strong>
          <small v-if="runtime?.port">随机端口 · {{ runtime.port }}</small>
          <small v-else>{{ gate?.license.active ? "等待本地服务" : "等待身份与授权" }}</small>
        </div>
      </div>
    </aside>

    <section class="content">
      <header class="topbar">
        <div>
          <p class="eyebrow">LOCAL-FIRST SCHEDULING</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div class="topbar-badges">
          <span class="badge secure">教务数据仅在本机</span>
          <span v-if="mockServices.length" class="badge mock">模拟服务：{{ mockServices.join(" / ") }}</span>
          <span v-if="gate?.auth.user" class="badge account">{{ gate.auth.user.email }}</span>
          <button v-if="gate?.canStartSidecar" class="text-button" :disabled="updateBusy" @click="checkForUpdate">{{ updateBusy ? "检查中…" : "检查更新" }}</button>
          <button v-if="availableUpdate?.available" class="text-button" :disabled="updateBusy" @click="installUpdate">安装 {{ availableUpdate.version }}</button>
          <button v-if="gate?.auth.authenticated" class="text-button" :disabled="gateBusy" @click="signOut">退出</button>
        </div>
      </header>

      <div v-if="gateBusy && !gate" class="state-panel">
        <div class="spinner"></div><h2>正在检查身份与设备授权</h2><p>令牌和设备私钥只从系统凭据库读取…</p>
      </div>

      <section v-else-if="!gate?.auth.configured" class="auth-layout">
        <article class="auth-card warning-card">
          <p class="eyebrow">CONFIGURATION REQUIRED</p>
          <h2>Supabase 身份服务尚未配置</h2>
          <p>{{ gate?.auth.message ?? gateError }}</p>
          <p>开发环境请设置 `STT_SUPABASE_PUBLISHABLE_KEY`，密钥值不要写入仓库或日志。</p>
          <button class="primary-button" @click="bootstrapGate">重新检查</button>
        </article>
      </section>

      <section v-else-if="!gate.auth.authenticated" class="auth-layout">
        <article class="auth-card">
          <p class="eyebrow">SUPABASE AUTH</p>
          <h2>{{ authMode === "signin" ? "登录时奕桌面版" : authMode === "signup" ? "注册账号" : "重置密码" }}</h2>
          <p class="form-copy">邮箱密码用于确认账号身份；激活设备时还需要企业密钥。</p>
          <form @submit.prevent="submitAuth">
            <label for="auth-email">邮箱</label>
            <input id="auth-email" v-model="email" type="email" autocomplete="email" required />
            <template v-if="authMode !== 'reset'">
              <label for="auth-password">密码</label>
              <input id="auth-password" v-model="password" type="password" :autocomplete="authMode === 'signin' ? 'current-password' : 'new-password'" minlength="8" required />
            </template>
            <p v-if="gateError" class="form-message error-copy">{{ gateError }}</p>
            <p v-if="gateNotice" class="form-message notice-copy">{{ gateNotice }}</p>
            <button class="primary-button full-button" :disabled="gateBusy">
              {{ gateBusy ? "处理中…" : authMode === "signin" ? "登录" : authMode === "signup" ? "注册并验证邮箱" : "发送重置邮件" }}
            </button>
          </form>
          <div class="auth-actions">
            <button class="link-button" @click="authMode = authMode === 'signup' ? 'signin' : 'signup'">{{ authMode === "signup" ? "返回登录" : "注册账号" }}</button>
            <button class="link-button" @click="authMode = authMode === 'reset' ? 'signin' : 'reset'">{{ authMode === "reset" ? "返回登录" : "忘记密码" }}</button>
          </div>
        </article>
        <aside class="security-card">
          <p class="eyebrow">PRIVACY BOUNDARY</p><h2>身份联网，教务离线</h2>
          <ul><li>Supabase 仅接收账号认证与许可证请求。</li><li>学校、教师、班级、课程和课表不上传。</li><li>登录令牌和设备私钥不进入 WebView。</li></ul>
        </aside>
      </section>

      <section v-else-if="!gate.license.active" class="auth-layout">
        <article class="auth-card">
          <p class="eyebrow">DEVICE ACTIVATION</p><h2>激活当前设备</h2>
          <p class="form-copy">已登录 {{ gate.auth.user?.email }}。请输入该购买账号收到的企业密钥。</p>
          <form @submit.prevent="activateLicense">
            <label for="enterprise-key">企业密钥</label>
            <input id="enterprise-key" v-model="enterpriseKey" type="password" autocomplete="off" required />
            <p v-if="gate.license.deviceId" class="device-copy">设备指纹：{{ gate.license.deviceId }}</p>
            <p v-if="gateError" class="form-message error-copy">{{ gateError }}</p>
            <p v-else-if="gate.license.message" class="form-message notice-copy">{{ gate.license.message }}</p>
            <button class="primary-button full-button" :disabled="gateBusy || !enterpriseKey.trim()">{{ gateBusy ? "正在验证…" : "验证并激活" }}</button>
          </form>
        </article>
        <aside class="security-card">
          <p class="eyebrow">LICENSE POLICY</p><h2>年度授权 · 最多 {{ gate.license.deviceLimit }} 台设备</h2>
          <ul><li>企业密钥只在首次激活时提交。</li><li>设备私钥保存在 Windows Credential Manager。</li><li>Mock 授权有效期 7 天，正式服务由 Ed25519 JWS 签发。</li></ul>
        </aside>
      </section>

      <CalendarView v-else-if="activeView === 'calendar' && currentProject" :revision="projectRevision" @revision="projectRevision = $event" />
      <SchoolDataView v-else-if="activeView === 'school' && currentProject" :revision="projectRevision" @revision="projectRevision = $event" />
      <ImportView v-else-if="activeView === 'imports' && currentProject" :revision="projectRevision" @revision="projectRevision = $event" />
      <PlanningView v-else-if="activeView === 'planning' && currentProject" :revision="projectRevision" @revision="projectRevision = $event" />
      <ConstraintsView v-else-if="activeView === 'constraints' && currentProject" :revision="projectRevision" @revision="projectRevision = $event" />
      <SchedulingView v-else-if="activeView === 'scheduling' && currentProject" :revision="projectRevision" @revision="projectRevision = $event" />
      <TimetableView v-else-if="activeView === 'timetables' && currentProject" :revision="projectRevision" @revision="projectRevision = $event" />
      <BackupsView v-else-if="activeView === 'backups' && currentProject" :revision="projectRevision" @revision="projectRevision = $event" @project-restored="applyRestoredProject" />
      <template v-else>
        <div v-if="workspaceBusy && !runtime" class="state-panel">
          <div class="spinner"></div><h2>正在启动安全本地服务</h2><p>校验随机端口、一次性令牌和项目工作目录…</p>
        </div>
        <div v-else-if="workspaceError" class="state-panel error-panel">
          <h2>本地服务启动失败</h2><p>{{ workspaceError }}</p><button class="primary-button" @click="bootstrapWorkspace">重新尝试</button>
        </div>
        <template v-else>
          <section class="hero-card">
            <div>
              <p class="eyebrow">工作目录</p><h2>建立或打开一个本地排课项目</h2>
              <p>每个项目使用独立 SQLite、附件与备份目录。账号和授权服务不会接收教务数据。</p>
            </div>
            <dl>
              <div><dt>协议</dt><dd>v{{ health?.protocolVersion }}</dd></div>
              <div><dt>数据结构</dt><dd>Schema {{ health?.schemaVersion }}</dd></div>
              <div><dt>授权到期</dt><dd>{{ licenseExpiry }}</dd></div>
              <div><dt>工作区</dt><dd>{{ runtime?.workspacePath ?? "应用数据目录" }}</dd></div>
            </dl>
          </section>

          <section class="grid-layout">
            <article class="panel create-panel">
              <p class="eyebrow">新建项目</p><h2>从空白项目开始</h2>
              <p v-if="workspaceError" class="form-message error-copy">{{ workspaceError }}</p>
              <p v-if="workspaceNotice" class="form-message notice-copy">{{ workspaceNotice }}</p>
              <label for="project-name">项目名称</label>
              <input id="project-name" v-model="projectName" maxlength="200" placeholder="例如：2026 学年第一学期" @keyup.enter="createProject" />
              <button class="primary-button" :disabled="workspaceBusy || !projectName.trim()" @click="createProject">创建并打开</button>
              <hr class="soft-divider" />
              <p class="eyebrow">可移植项目包</p>
              <button class="secondary-button" :disabled="workspaceBusy" @click="importProjectArchive">导入 .sttproj</button>
              <button class="secondary-button" :disabled="workspaceBusy || !currentProject" @click="exportProjectArchive">导出当前项目</button>
            </article>
            <article class="panel projects-panel">
              <div class="panel-heading"><div><p class="eyebrow">最近项目</p><h2>本机项目</h2></div><span>{{ projects.length }} 个</span></div>
              <p v-if="projects.length === 0" class="empty-copy">还没有项目。创建后即可配置学期、资料和排课计划。</p>
              <button v-for="project in projects" v-else :key="String(project.project_id)" class="project-row" @click="openProject(String(project.project_id))">
                <span><strong>{{ project.name }}</strong><small>Revision {{ project.revision }} · {{ project.updated_at }}</small></span><b>打开</b>
              </button>
            </article>
          </section>
        </template>
      </template>
    </section>
  </main>
</template>
