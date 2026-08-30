<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  localApi,
  startSidecar,
  type HealthStatus,
  type ProjectInfo,
  type RuntimeStatus,
} from "./lib/sidecar";

type NavItem = { key: string; label: string; enabled: boolean };

const navItems: NavItem[] = [
  { key: "workspace", label: "项目工作台", enabled: true },
  { key: "calendar", label: "学期与作息", enabled: false },
  { key: "school", label: "基础资料", enabled: false },
  { key: "planning", label: "课程计划", enabled: false },
  { key: "constraints", label: "约束配置", enabled: false },
  { key: "scheduling", label: "排课运行", enabled: false },
  { key: "timetables", label: "课表与导出", enabled: false },
  { key: "backups", label: "备份恢复", enabled: false },
];

const runtime = ref<RuntimeStatus | null>(null);
const health = ref<HealthStatus | null>(null);
const projects = ref<Array<Record<string, unknown>>>([]);
const currentProject = ref<ProjectInfo | null>(null);
const projectName = ref("");
const busy = ref(true);
const errorMessage = ref("");

const mockServices = computed(() =>
  Object.entries(health.value?.serviceModes ?? {})
    .filter(([, mode]) => mode === "mock")
    .map(([name]) => name),
);

async function refreshProjects() {
  projects.value = (await localApi.listProjects()).projects;
}

async function bootstrap() {
  busy.value = true;
  errorMessage.value = "";
  try {
    runtime.value = await startSidecar();
    health.value = await localApi.health();
    await refreshProjects();
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    busy.value = false;
  }
}

async function createProject() {
  const name = projectName.value.trim();
  if (!name) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    const result = await localApi.createProject(name);
    currentProject.value = result.project;
    projectName.value = "";
    await refreshProjects();
    health.value = await localApi.health();
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    busy.value = false;
  }
}

async function openProject(projectId: string) {
  busy.value = true;
  errorMessage.value = "";
  try {
    const result = await localApi.openProject(projectId);
    currentProject.value = result.project;
    health.value = await localApi.health();
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    busy.value = false;
  }
}

onMounted(bootstrap);
</script>

<template>
  <main class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">时</div>
        <div>
          <strong>时奕教务排课</strong>
          <span>本地桌面版</span>
        </div>
      </div>

      <nav aria-label="主要功能">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: item.key === 'workspace' }"
          :disabled="!item.enabled"
        >
          <span>{{ item.label }}</span>
          <small v-if="!item.enabled">实施中</small>
        </button>
      </nav>

      <div class="runtime-card">
        <span class="status-dot" :class="runtime?.running ? 'online' : 'offline'"></span>
        <div>
          <strong>{{ runtime?.running ? "本地服务已连接" : "本地服务未连接" }}</strong>
          <small v-if="runtime?.port">随机端口 · {{ runtime.port }}</small>
        </div>
      </div>
    </aside>

    <section class="content">
      <header class="topbar">
        <div>
          <p class="eyebrow">LOCAL-FIRST SCHEDULING</p>
          <h1>{{ currentProject?.name ?? "项目工作台" }}</h1>
        </div>
        <div class="topbar-badges">
          <span class="badge secure">教务数据仅在本机</span>
          <span v-if="mockServices.length" class="badge mock">
            模拟服务：{{ mockServices.join(" / ") }}
          </span>
        </div>
      </header>

      <div v-if="busy && !runtime" class="state-panel">
        <div class="spinner"></div>
        <h2>正在启动安全本地服务</h2>
        <p>校验随机端口、一次性令牌和项目工作目录…</p>
      </div>

      <div v-else-if="errorMessage" class="state-panel error-panel">
        <h2>本地服务启动失败</h2>
        <p>{{ errorMessage }}</p>
        <button class="primary-button" @click="bootstrap">重新尝试</button>
      </div>

      <template v-else>
        <section class="hero-card">
          <div>
            <p class="eyebrow">工作目录</p>
            <h2>建立或打开一个本地排课项目</h2>
            <p>每个项目使用独立 SQLite、附件与备份目录。账号和授权服务不会接收教务数据。</p>
          </div>
          <dl>
            <div>
              <dt>协议</dt>
              <dd>v{{ health?.protocolVersion }}</dd>
            </div>
            <div>
              <dt>数据结构</dt>
              <dd>Schema {{ health?.schemaVersion }}</dd>
            </div>
            <div>
              <dt>工作区</dt>
              <dd>{{ runtime?.workspacePath ?? "应用数据目录" }}</dd>
            </div>
          </dl>
        </section>

        <section class="grid-layout">
          <article class="panel create-panel">
            <p class="eyebrow">新建项目</p>
            <h2>从空白项目开始</h2>
            <label for="project-name">项目名称</label>
            <input
              id="project-name"
              v-model="projectName"
              maxlength="200"
              placeholder="例如：2026 学年第一学期"
              @keyup.enter="createProject"
            />
            <button class="primary-button" :disabled="busy || !projectName.trim()" @click="createProject">
              创建并打开
            </button>
          </article>

          <article class="panel projects-panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">最近项目</p>
                <h2>本机项目</h2>
              </div>
              <span>{{ projects.length }} 个</span>
            </div>
            <p v-if="projects.length === 0" class="empty-copy">还没有项目。创建后即可配置学期、资料和排课计划。</p>
            <button
              v-for="project in projects"
              v-else
              :key="String(project.project_id)"
              class="project-row"
              @click="openProject(String(project.project_id))"
            >
              <span>
                <strong>{{ project.name }}</strong>
                <small>Revision {{ project.revision }} · {{ project.updated_at }}</small>
              </span>
              <b>打开</b>
            </button>
          </article>
        </section>
      </template>
    </section>
  </main>
</template>
