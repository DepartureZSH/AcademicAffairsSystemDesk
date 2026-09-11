<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { confirm, open, save } from "@tauri-apps/plugin-dialog";
import {
  Activity,
  CalendarDays,
  ChevronDown,
  DatabaseBackup,
  DoorOpen,
  Info,
  LayoutDashboard,
  LogOut,
  NotebookPen,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  SlidersHorizontal,
  Upload,
  UsersRound,
} from "lucide-vue-next";
import CalendarView from "./components/CalendarView.vue";
import ConstraintsView from "./components/ConstraintsView.vue";
import PlanningView from "./components/PlanningView.vue";
import SchoolDataView from "./components/SchoolDataView.vue";
import RunsWorkspace from "./components/RunsWorkspace.vue";
import BackupsView from "./components/BackupsView.vue";
import ImportView from "./components/ImportView.vue";
import AboutView from "./components/AboutView.vue";
import { accessGate, type GateStatus } from "./lib/accessGate";
import { updater, type UpdateStatus } from "./lib/updater";
import { savedWorkspacePath, saveWorkspacePath } from "./lib/workspaceSettings";
import {
  localApi,
  formatLocalError,
  startSidecar,
  stopSidecar,
  type HealthStatus,
  type ProjectInfo,
  type RuntimeStatus,
} from "./lib/sidecar";

type NavItem = { key: string; label: string; icon: typeof LayoutDashboard };
type AuthMode = "signin" | "signup" | "reset" | "recover";

const navItems: NavItem[] = [
  { key: "workspace", label: "工作台", icon: LayoutDashboard },
  { key: "timetable", label: "课表设置", icon: CalendarDays },
  { key: "rooms", label: "教室设置", icon: DoorOpen },
  { key: "school", label: "学校数据", icon: UsersRound },
  { key: "planning", label: "课程计划", icon: NotebookPen },
  { key: "constraints", label: "约束配置", icon: SlidersHorizontal },
  { key: "runs", label: "排课运行", icon: Activity },
];

const gate = ref<GateStatus | null>(null);
const gateBusy = ref(true);
const authMode = ref<AuthMode>("signin");
const email = ref("");
const password = ref("");
const recoveryLink = ref("");
const newPassword = ref("");
const confirmNewPassword = ref("");
const gateError = ref("");
const gateNotice = ref("");

const runtime = ref<RuntimeStatus | null>(null);
const health = ref<HealthStatus | null>(null);
const projects = ref<Array<Record<string, unknown>>>([]);
const currentProject = ref<ProjectInfo | null>(null);
const projectRevision = ref(0);
const activeView = ref("workspace");
const projectName = ref("");
const saveAsName = ref("");
const workspaceBusy = ref(false);
const workspaceError = ref("");
const workspaceNotice = ref("");
const updateBusy = ref(false);
const availableUpdate = ref<UpdateStatus | null>(null);
const preferredWorkspacePath = ref(savedWorkspacePath() ?? "");
const sidebarCollapsed = ref(localStorage.getItem("stt-sidebar-collapsed") === "true");
const accountMenuOpen = ref(false);
const workflowCounts = ref<Record<string, number>>({});
const workflowBusy = ref(false);

const pageTitle = computed(() => {
  if (activeView.value === "about") return "软件信息";
  if (!gate.value?.canStartSidecar) return "身份与设备授权";
  if (activeView.value === "timetable") return "课表设置";
  if (activeView.value === "rooms") return "教室设置";
  if (activeView.value === "school") return "学校数据";
  if (activeView.value === "imports") return "数据导入";
  if (activeView.value === "planning") return "课程计划";
  if (activeView.value === "constraints") return "约束配置";
  if (activeView.value === "runs") return "排课运行";
  if (activeView.value === "backups") return "数据备份";
  return "工作台";
});

const workflowSteps = computed(() => {
  const count = workflowCounts.value;
  return [
    { key: "timetable", label: "课表设置", detail: `${count.bell_schedule ?? 0} 套作息 · ${count.time_slot ?? 0} 个课节`, ready: (count.bell_schedule ?? 0) > 0 && (count.time_slot ?? 0) > 0 },
    { key: "rooms", label: "教室设置", detail: `${count.room ?? 0} 间教室`, ready: (count.room ?? 0) > 0 },
    { key: "school", label: "学校数据", detail: `教师 ${count.teacher ?? 0} · 班级 ${count.homeroom ?? 0} · 科目 ${count.subject ?? 0}`, ready: (count.teacher ?? 0) > 0 && (count.homeroom ?? 0) > 0 && (count.subject ?? 0) > 0 },
    { key: "planning", label: "课程计划", detail: `${count.teaching_task ?? 0} 项任务 · ${count.task_lesson ?? 0} 个课次`, ready: (count.task_lesson ?? 0) > 0 },
    { key: "constraints", label: "约束配置", detail: `${count.constraint ?? 0} 条自定义规则`, ready: true, optional: true },
    { key: "runs", label: "排课运行", detail: (count.candidate ?? 0) > 0 ? `已有 ${count.candidate} 个候选方案` : "准备好后即可开始排课", ready: (count.candidate ?? 0) > 0 },
  ];
});

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  localStorage.setItem("stt-sidebar-collapsed", String(sidebarCollapsed.value));
}

function navigate(view: string) {
  activeView.value = view;
  accountMenuOpen.value = false;
}

async function refreshWorkflowCounts() {
  if (!currentProject.value || workflowBusy.value) return;
  workflowBusy.value = true;
  try {
    const types = ["bell_schedule", "time_slot", "room", "teacher", "homeroom", "subject", "teaching_task", "task_lesson", "constraint"];
    const [entities, candidates] = await Promise.all([
      Promise.all(types.map((type) => localApi.listEntities(type, { limit: 1 }))),
      localApi.listSchedulingCandidates(),
    ]);
    const next: Record<string, number> = {};
    types.forEach((type, index) => { next[type] = entities[index].total ?? entities[index].items.length; });
    next.candidate = candidates.items.length;
    workflowCounts.value = next;
  } catch {
    // Readiness is guidance only; module pages still show actionable errors.
  } finally {
    workflowBusy.value = false;
  }
}

function applyProjectRevision(value: number) {
  projectRevision.value = value;
  void refreshWorkflowCounts();
}

async function refreshProjects() {
  projects.value = (await localApi.listProjects()).projects;
}

async function bootstrapWorkspace() {
  workspaceBusy.value = true;
  workspaceError.value = "";
  try {
    runtime.value = await startSidecar(preferredWorkspacePath.value || undefined);
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
    } else if (authMode.value === "reset") {
      gateNotice.value = await accessGate.requestPasswordReset(email.value.trim());
      authMode.value = "recover";
    } else {
      if (newPassword.value !== confirmNewPassword.value) throw new Error("两次输入的新密码不一致");
      const link = recoveryLink.value.trim();
      const replacement = newPassword.value;
      recoveryLink.value = "";
      newPassword.value = "";
      confirmNewPassword.value = "";
      gateNotice.value = await accessGate.completePasswordReset(link, replacement);
      authMode.value = "signin";
    }
  } catch (error) {
    gateError.value = String(error);
  } finally {
    gateBusy.value = false;
  }
}

async function openPurchasePage() {
  gateBusy.value = true;
  gateError.value = "";
  try {
    const result = await accessGate.openPurchasePage();
    gateNotice.value = result.message;
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
    gateNotice.value = "已退出并清除本地登录会话与会员校验状态";
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
    await refreshWorkflowCounts();
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
    await refreshWorkflowCounts();
    health.value = await localApi.health();
  } catch (error) {
    workspaceError.value = formatLocalError(error);
  } finally {
    workspaceBusy.value = false;
  }
}

async function deleteProject(project: Record<string, unknown>) {
  const projectId = String(project.project_id);
  const projectName = String(project.name);
  const projectPath = String(project.path || `${runtime.value?.workspacePath ?? "当前工作目录"}\\projects\\${projectId}`);
  if (currentProject.value?.id === projectId) {
    workspaceError.value = `项目“${projectName}”当前正在打开，请先关闭项目后再删除。`;
    return;
  }
  const firstAccepted = await confirm(
    `删除项目“${projectName}”？\n\n准确路径：${projectPath}\n\n项目会移入当前工作区的隔离回收区，不会立即擦除。`,
    { title: "删除本地项目", kind: "warning" },
  );
  if (!firstAccepted) return;
  const secondAccepted = await confirm(
    `再次确认删除“${projectName}”。\n\n该项目将从项目列表移除；需要恢复时必须从隔离回收路径人工处理。`,
    { title: "再次确认删除", kind: "warning" },
  );
  if (!secondAccepted) return;
  workspaceBusy.value = true;
  workspaceError.value = "";
  workspaceNotice.value = "";
  try {
    const result = await localApi.deleteProject(projectId, projectName);
    await refreshProjects();
    workspaceNotice.value = `项目已移入隔离回收区，可恢复路径：${result.deleted.trashPath}`;
  } catch (error) {
    workspaceError.value = formatLocalError(error);
  } finally {
    workspaceBusy.value = false;
  }
}

async function closeCurrentProject() {
  if (!currentProject.value) return;
  const accepted = await confirm(
    `关闭项目“${currentProject.value.name}”？所有已提交数据仍保留在：\n\n${runtime.value?.workspacePath ?? "当前工作目录"}`,
    { title: "关闭当前项目", kind: "info" },
  );
  if (!accepted) return;
  workspaceBusy.value = true;
  workspaceError.value = "";
  try {
    await localApi.closeProject();
    currentProject.value = null;
    projectRevision.value = 0;
    activeView.value = "workspace";
    health.value = await localApi.health();
    workspaceNotice.value = "项目已关闭，本地文件未删除";
  } catch (error) {
    workspaceError.value = formatLocalError(error);
  } finally {
    workspaceBusy.value = false;
  }
}

async function selectWorkspaceDirectory() {
  if (health.value?.activeSchedulingRounds.length) {
    workspaceError.value = "排课轮次运行期间不能切换工作目录，请先取消或等待完成";
    activeView.value = "runs";
    return;
  }
  const selected = await open({
    multiple: false,
    directory: true,
    title: "选择时奕教务排课项目工作目录",
  });
  if (typeof selected !== "string" || selected === runtime.value?.workspacePath) return;
  const accepted = await confirm(
    `切换工作目录会关闭当前项目并重启本地服务。不会移动或删除原目录中的任何项目。\n\n新目录：${selected}\n\n是否继续？`,
    { title: "切换项目工作目录", kind: "warning" },
  );
  if (!accepted) return;

  workspaceBusy.value = true;
  workspaceError.value = "";
  workspaceNotice.value = "";
  const previousPath = preferredWorkspacePath.value;
  try {
    if (runtime.value?.running) await stopSidecar();
    runtime.value = null;
    health.value = null;
    currentProject.value = null;
    projectRevision.value = 0;
    preferredWorkspacePath.value = selected;
    saveWorkspacePath(selected);
    runtime.value = await startSidecar(selected);
    health.value = await localApi.health();
    await refreshProjects();
    workspaceNotice.value = `已切换工作目录：${selected}`;
  } catch (error) {
    preferredWorkspacePath.value = previousPath;
    saveWorkspacePath(previousPath || undefined);
    workspaceError.value = `无法使用新工作目录，已恢复原设置：${formatLocalError(error)}`;
    try {
      runtime.value = await startSidecar(previousPath || undefined);
      health.value = await localApi.health();
      await refreshProjects();
      workspaceNotice.value = workspaceError.value;
      workspaceError.value = "";
    } catch {
      runtime.value = null;
      health.value = null;
    }
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

async function saveProjectAs() {
  const name = saveAsName.value.trim();
  if (!currentProject.value || !name) return;
  workspaceBusy.value = true;
  workspaceError.value = "";
  workspaceNotice.value = "";
  try {
    const sourceName = currentProject.value.name;
    const result = await localApi.cloneCurrentProject(name);
    currentProject.value = result.project;
    projectRevision.value = result.revision;
    saveAsName.value = "";
    await refreshProjects();
    health.value = await localApi.health();
    workspaceNotice.value = `已将“${sourceName}”另存为独立项目“${result.project.name}”，原项目保持不变`;
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
    await refreshWorkflowCounts();
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
  void refreshWorkflowCounts();
}

let membershipTimer: ReturnType<typeof setInterval> | undefined;
let membershipChecking = false;
async function checkRunningMembership() {
  if (gateBusy.value || membershipChecking || !gate.value?.auth.authenticated) return;
  membershipChecking = true;
  try {
    const next = await accessGate.status();
    // Login/logout may have completed while the check was in flight.
    if (gateBusy.value || gate.value?.auth.user?.id !== next.auth.user?.id) return;
    gate.value = next;
    if (!next.canStartSidecar) {
      runtime.value = null;
      health.value = null;
      gateNotice.value = next.license.message ?? next.auth.message ?? "请重新检查会员权益";
    }
  } catch (error) {
    if (!gateBusy.value && gate.value) {
      gate.value = { ...gate.value, canStartSidecar: false, license: { ...gate.value.license, active: false } };
      runtime.value = null;
      health.value = null;
      gateError.value = String(error);
    }
  } finally { membershipChecking = false; }
}
onMounted(() => {
  void bootstrapGate();
  membershipTimer = setInterval(() => { void checkRunningMembership(); }, 20_000);
});
onUnmounted(() => { if (membershipTimer) clearInterval(membershipTimer); });
</script>

<template>
  <main class="app-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">时</div>
        <div class="brand-copy"><strong>时奕教务</strong><span>本地排课系统</span></div>
        <button class="sidebar-toggle" :title="sidebarCollapsed ? '展开菜单' : '收起菜单'" @click="toggleSidebar">
          <PanelLeftOpen v-if="sidebarCollapsed" :size="18" />
          <PanelLeftClose v-else :size="18" />
        </button>
      </div>

      <nav aria-label="主要功能">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: item.key === activeView }"
          :disabled="!gate?.canStartSidecar || (item.key !== 'workspace' && !currentProject)"
          :title="sidebarCollapsed ? item.label : undefined"
          @click="navigate(item.key)"
        >
          <component :is="item.icon" :size="19" aria-hidden="true" />
          <span class="nav-label">{{ item.label }}</span>
        </button>
      </nav>

      <div class="local-status" :title="runtime?.running ? '本地服务已连接' : '本地服务未启动'">
        <span class="status-dot" :class="runtime?.running ? 'online' : 'offline'"></span>
        <span class="nav-label">{{ runtime?.running ? "数据保存在本机" : gate?.license.active ? "正在准备" : "等待登录" }}</span>
      </div>
    </aside>

    <section class="content">
      <header class="topbar">
        <h1>{{ pageTitle }}</h1>
        <div class="topbar-badges">
          <button v-if="availableUpdate?.available" class="text-button" :disabled="updateBusy" @click="installUpdate">安装 {{ availableUpdate.version }}</button>
          <div v-if="gate?.auth.authenticated" class="account-menu">
            <button class="account-trigger" @click="accountMenuOpen = !accountMenuOpen">
              <span class="account-avatar">{{ gate.auth.user?.email?.slice(0, 1).toUpperCase() }}</span>
              <span>{{ gate.auth.user?.email }}</span><ChevronDown :size="15" />
            </button>
            <div v-if="accountMenuOpen" class="account-popover">
              <button :disabled="!currentProject" @click="navigate('backups')"><DatabaseBackup :size="16" />数据备份</button>
              <button @click="navigate('about')"><Info :size="16" />软件信息</button>
              <button :disabled="updateBusy" @click="checkForUpdate"><RefreshCw :size="16" />{{ updateBusy ? "检查中…" : "检查更新" }}</button>
              <button :disabled="gateBusy" @click="signOut"><LogOut :size="16" />退出登录</button>
            </div>
          </div>
        </div>
      </header>

      <div v-if="currentProject && !['workspace', 'about'].includes(activeView)" class="project-context">
        <span>当前项目</span><strong>{{ currentProject.name }}</strong>
        <button @click="navigate('workspace')">返回工作台选择项目</button>
        <button v-if="activeView === 'runs'" class="context-action" @click="navigate('imports')"><Upload :size="15" />导入数据</button>
      </div>

      <div v-if="gateBusy && !gate" class="state-panel">
        <div class="spinner"></div><h2>正在检查登录状态和会员权益</h2><p>请稍候…</p>
      </div>

      <AboutView v-else-if="activeView === 'about'" />

      <section v-else-if="!gate?.auth.configured" class="auth-layout">
        <article class="auth-card warning-card">
          <p class="eyebrow">应用配置异常</p>
          <h2>登录服务暂时不可用</h2>
          <p>{{ gate?.auth.message ?? gateError }}</p>
          <p>请确认安装的是完整发行版；如果问题持续出现，请重新安装或联系技术支持。</p>
          <button class="primary-button" @click="bootstrapGate">重新检查</button>
        </article>
      </section>

      <section v-else-if="!gate.auth.authenticated" class="auth-layout">
        <article class="auth-card">
          <p class="eyebrow">账号登录</p>
          <h2>{{ authMode === "signin" ? "登录时奕桌面版" : authMode === "signup" ? "注册账号" : authMode === "reset" ? "申请重置密码" : "设置新密码" }}</h2>
          <p class="form-copy">使用网页版的同一账号登录，会员权益自动核验。</p>
          <form @submit.prevent="submitAuth">
            <template v-if="authMode !== 'recover'">
              <label for="auth-email">邮箱</label>
              <input id="auth-email" v-model="email" type="email" autocomplete="email" required />
            </template>
            <template v-if="authMode === 'signin' || authMode === 'signup'">
              <label for="auth-password">密码</label>
              <input id="auth-password" v-model="password" type="password" :autocomplete="authMode === 'signin' ? 'current-password' : 'new-password'" minlength="8" required />
            </template>
            <template v-if="authMode === 'recover'">
              <p class="form-copy recovery-copy">从密码恢复邮件复制完整链接并粘贴到这里。链接只用于本次验证，不会保存到本地凭据或日志。</p>
              <label for="recovery-link">完整恢复链接</label>
              <input id="recovery-link" v-model="recoveryLink" type="password" autocomplete="off" spellcheck="false" required />
              <label for="new-password">新密码</label>
              <input id="new-password" v-model="newPassword" type="password" autocomplete="new-password" minlength="8" required />
              <label for="confirm-new-password">再次输入新密码</label>
              <input id="confirm-new-password" v-model="confirmNewPassword" type="password" autocomplete="new-password" minlength="8" required />
            </template>
            <p v-if="gateError" class="form-message error-copy">{{ gateError }}</p>
            <p v-if="gateNotice" class="form-message notice-copy">{{ gateNotice }}</p>
            <button class="primary-button full-button" :disabled="gateBusy">
              {{ gateBusy ? "处理中…" : authMode === "signin" ? "登录" : authMode === "signup" ? "注册并验证邮箱" : authMode === "reset" ? "发送重置邮件" : "验证链接并更新密码" }}
            </button>
          </form>
          <div class="auth-actions">
            <button class="link-button" @click="authMode = authMode === 'signup' ? 'signin' : 'signup'">{{ authMode === "signup" ? "返回登录" : "注册账号" }}</button>
            <button class="link-button" @click="authMode = authMode === 'reset' || authMode === 'recover' ? 'signin' : 'reset'">{{ authMode === "reset" || authMode === "recover" ? "返回登录" : "忘记密码" }}</button>
          </div>
        </article>
        <aside class="security-card">
          <p class="eyebrow">隐私说明</p><h2>账号联网，教务数据留在本机</h2>
          <ul><li>使用时奕账号登录并核验会员权益。</li><li>学校、教师、班级、课程和课表仅保存在这台电脑。</li><li>登录状态由系统安全保存。</li></ul>
        </aside>
      </section>

      <section v-else-if="!gate.license.active" class="auth-layout">
        <article class="auth-card">
          <p class="eyebrow">会员权益</p><h2>账号会员权益</h2>
          <p class="form-copy">已登录 {{ gate.auth.user?.email }}。</p>
          <form @submit.prevent="bootstrapGate">
            <p v-if="gateError" class="form-message error-copy">{{ gateError }}</p>
            <p v-else-if="gate.license.message" class="form-message notice-copy">{{ gate.license.message }}</p>
            <button class="primary-button full-button" :disabled="gateBusy">{{ gateBusy ? "正在核验…" : "重新检查会员权益" }}</button>
          </form>
          <div class="auth-actions purchase-actions">
            <span>尚未开通会员？</span>
            <button class="link-button" :disabled="gateBusy" @click="openPurchasePage">在系统浏览器购买</button>
          </div>
        </article>
        <aside class="security-card">
          <p class="eyebrow">会员说明</p><h2>同一账号，共享会员权益</h2>
          <ul><li>无需激活码或单独购买桌面许可证。</li><li>账号邮箱须已验证，会员须在有效期内。</li><li>当前版本需要联网核验会员，不支持离线授权。</li></ul>
        </aside>
      </section>

      <CalendarView v-else-if="activeView === 'timetable' && currentProject" :revision="projectRevision" @revision="applyProjectRevision" />
      <SchoolDataView v-else-if="activeView === 'rooms' && currentProject" mode="rooms" :revision="projectRevision" @revision="applyProjectRevision" />
      <SchoolDataView v-else-if="activeView === 'school' && currentProject" mode="school" :revision="projectRevision" @revision="applyProjectRevision" />
      <ImportView v-else-if="activeView === 'imports' && currentProject" :revision="projectRevision" @revision="applyProjectRevision" />
      <PlanningView v-else-if="activeView === 'planning' && currentProject" :revision="projectRevision" @revision="applyProjectRevision" />
      <ConstraintsView v-else-if="activeView === 'constraints' && currentProject" :revision="projectRevision" @revision="applyProjectRevision" />
      <RunsWorkspace v-else-if="activeView === 'runs' && currentProject" :revision="projectRevision" @revision="applyProjectRevision" />
      <BackupsView v-else-if="activeView === 'backups' && currentProject" :revision="projectRevision" @revision="applyProjectRevision" @project-restored="applyRestoredProject" />
      <template v-else>
        <div v-if="workspaceBusy && !runtime" class="state-panel">
          <div class="spinner"></div><h2>正在准备本地工作区</h2><p>首次启动可能需要十几秒，请稍候…</p>
        </div>
        <div v-else-if="workspaceError" class="state-panel error-panel">
          <h2>本地服务启动失败</h2><p>{{ workspaceError }}</p><button class="primary-button" @click="bootstrapWorkspace">重新尝试</button>
        </div>
        <template v-else>
          <section class="home-welcome panel">
            <div>
              <h2>用户主页</h2>
              <p>选择一个排课项目，然后按照左侧菜单依次完成学校数据、课程计划、约束配置和排课运行。</p>
            </div>
            <div class="home-actions">
              <button class="secondary-button" :disabled="workspaceBusy" @click="selectWorkspaceDirectory">选择工作目录</button>
              <button v-if="currentProject" class="text-button" :disabled="workspaceBusy" @click="closeCurrentProject">关闭当前项目</button>
            </div>
          </section>

          <p v-if="workspaceNotice" class="form-message notice-copy">{{ workspaceNotice }}</p>
          <section class="home-grid">
            <article class="panel projects-panel">
              <div class="panel-heading"><div><h2>我的排课项目</h2><p>项目资料只保存在这台电脑。</p></div><span>{{ projects.length }} 个</span></div>
              <div class="quick-create">
                <input id="project-name" v-model="projectName" maxlength="200" placeholder="输入项目名称，如：2026 学年第一学期" @keyup.enter="createProject" />
                <button class="primary-button" :disabled="workspaceBusy || !projectName.trim()" @click="createProject">新建项目</button>
              </div>
              <p v-if="projects.length === 0" class="empty-copy">还没有项目。输入名称并点击“新建项目”即可开始。</p>
              <div v-for="project in projects" v-else :key="String(project.project_id)" class="project-list-row" :class="{ current: currentProject?.id === String(project.project_id) }">
                <button class="project-row" @click="openProject(String(project.project_id))">
                  <span><strong>{{ project.name }}</strong><small>{{ project.updated_at }}</small></span><b>{{ currentProject?.id === String(project.project_id) ? "当前项目" : "打开" }}</b>
                </button>
                <button class="project-delete" :disabled="workspaceBusy || currentProject?.id === String(project.project_id)" :title="currentProject?.id === String(project.project_id) ? '请先关闭当前项目' : '删除项目'" @click="deleteProject(project)">删除</button>
              </div>

              <details class="advanced-details project-tools">
                <summary>项目导入、导出与另存</summary>
                <div class="project-tool-actions">
                  <button class="secondary-button" :disabled="workspaceBusy" @click="importProjectArchive">导入项目文件</button>
                  <button class="secondary-button" :disabled="workspaceBusy || !currentProject" @click="exportProjectArchive">导出当前项目</button>
                </div>
                <template v-if="currentProject">
                  <label for="save-as-name">另存为新项目</label>
                  <div class="quick-create"><input id="save-as-name" v-model="saveAsName" maxlength="200" :placeholder="`${currentProject.name} - 副本`" @keyup.enter="saveProjectAs" /><button class="secondary-button" :disabled="workspaceBusy || !saveAsName.trim()" @click="saveProjectAs">另存</button></div>
                </template>
              </details>
            </article>

            <article class="panel readiness-panel">
              <div class="panel-heading"><div><h2>完整流程指引</h2><p>{{ currentProject ? `当前：${currentProject.name}` : "先从左侧选择一个项目" }}</p></div></div>
              <div v-if="currentProject" class="workflow-list">
                <button v-for="(step, index) in workflowSteps" :key="step.key" @click="navigate(step.key)">
                  <span class="workflow-index" :class="{ done: step.ready }">{{ step.ready ? "✓" : index + 1 }}</span>
                  <span><strong>{{ step.label }}</strong><small>{{ step.detail }}</small></span>
                  <b>{{ step.optional ? "可选" : step.ready ? "已完成" : "去设置" }}</b>
                </button>
              </div>
              <div v-else class="empty-workflow"><CalendarDays :size="38" /><p>打开项目后，这里会按网页版的顺序提示下一步。</p></div>
              <button v-if="currentProject" class="primary-button start-next" @click="navigate(workflowSteps.find((step) => !step.ready && !step.optional)?.key ?? 'runs')">继续下一步</button>
            </article>
          </section>
        </template>
      </template>
    </section>
  </main>
</template>
