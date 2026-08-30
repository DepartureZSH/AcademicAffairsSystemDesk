<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { confirm, open, save } from "@tauri-apps/plugin-dialog";
import {
  formatLocalError,
  localApi,
  type BackupRecord,
  type ProjectInfo,
} from "../lib/sidecar";

const props = defineProps<{ revision: number }>();
const emit = defineEmits<{
  revision: [value: number];
  projectRestored: [project: ProjectInfo, revision: number];
}>();

const revision = ref(props.revision);
const backups = ref<BackupRecord[]>([]);
const reason = ref("手工备份");
const retained = ref(true);
const restoredName = ref("");
const busy = ref(false);
const errorMessage = ref("");
const notice = ref("");

watch(() => props.revision, (value) => { revision.value = value; });

function fileSize(value: number | null) {
  if (value == null) return "文件缺失";
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

async function loadBackups() {
  errorMessage.value = "";
  try {
    const result = await localApi.listBackups();
    backups.value = result.items;
    revision.value = result.revision;
    emit("revision", revision.value);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  }
}

async function createBackup(copyOutside = false) {
  let destinationPath: string | null = null;
  if (copyOutside) {
    destinationPath = await save({
      defaultPath: `时奕项目备份-${new Date().toISOString().slice(0, 10)}.sttbackup`,
      filters: [{ name: "时奕完整备份", extensions: ["sttbackup"] }],
    });
    if (!destinationPath) return;
  }
  busy.value = true;
  errorMessage.value = "";
  notice.value = "";
  try {
    const result = await localApi.createBackup({
      reason: reason.value.trim() || "手工备份",
      retained: retained.value,
      destination_path: destinationPath,
      overwrite: Boolean(destinationPath),
    });
    notice.value = `备份已创建并校验：${String(result.backup.fileName)}`;
    await loadBackups();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function verifyBackup(item: BackupRecord) {
  busy.value = true;
  errorMessage.value = "";
  notice.value = "";
  try {
    const result = await localApi.verifyBackup(item.id);
    notice.value = `校验通过：${String(result.sha256).slice(0, 16)}… · ${fileSize(Number(result.sizeBytes))}`;
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function toggleRetained(item: BackupRecord) {
  busy.value = true;
  try {
    await localApi.retainBackup(item.id, !item.retained);
    await loadBackups();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function restore(source: { backup_id?: string; archive_path?: string }, displayPath: string) {
  const accepted = await confirm(
    `将从以下备份恢复为一个新的本地项目副本，不覆盖当前项目：\n\n${displayPath}\n\n恢复前会重新校验 ZIP 路径、文件哈希、SQLite 完整性和数据结构版本。是否继续？`,
    { title: "确认恢复备份", kind: "warning" },
  );
  if (!accepted) return;
  busy.value = true;
  errorMessage.value = "";
  notice.value = "";
  try {
    const result = await localApi.restoreBackup({
      ...source,
      restored_name: restoredName.value.trim() || null,
      confirmed: true,
    });
    notice.value = `已恢复并打开新项目：${result.project.name}`;
    emit("projectRestored", result.project, result.revision);
    await loadBackups();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function restoreExternal() {
  const path = await open({
    multiple: false,
    directory: false,
    filters: [{ name: "时奕完整备份", extensions: ["sttbackup"] }],
  });
  if (typeof path === "string") await restore({ archive_path: path }, path);
}

onMounted(loadBackups);
</script>

<template>
  <section class="module-view">
    <div class="module-heading"><div><p class="eyebrow">BACKUP & RECOVERY</p><h2>备份与恢复</h2><p>备份先做一致性快照、哈希和解压校验；恢复始终创建新项目副本。</p></div><span>Revision {{ revision }}</span></div>
    <div class="invariant-banner"><strong>不覆盖原项目</strong><span>恢复失败不会修改当前项目；保留的手工备份不参与最近 10 份自动备份清理。</span></div>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>
    <p v-if="notice" class="form-message notice-copy">{{ notice }}</p>

    <div class="directory-layout planning-layout">
      <article class="panel data-panel">
        <p class="eyebrow">CREATE BACKUP</p><h3>创建完整备份</h3>
        <form class="compact-form" @submit.prevent="createBackup(false)">
          <label>备份原因<input v-model="reason" maxlength="200" required /></label>
          <label class="check-label"><input v-model="retained" type="checkbox" />标记为长期保留</label>
          <button class="primary-button" :disabled="busy">{{ busy ? "正在校验…" : "保存到工作区" }}</button>
          <button type="button" class="secondary-button" :disabled="busy" @click="createBackup(true)">创建并另存一份</button>
        </form>
        <hr class="soft-divider" />
        <p class="eyebrow">RESTORE COPY</p><h3>恢复为新项目</h3>
        <div class="compact-form">
          <label>新项目名称（可选）<input v-model="restoredName" maxlength="200" placeholder="默认添加恢复日期" /></label>
          <button class="secondary-button" :disabled="busy" @click="restoreExternal">选择外部 .sttbackup</button>
        </div>
      </article>

      <article class="panel data-panel records-panel">
        <div class="panel-heading"><div><p class="eyebrow">VERIFIED COPIES</p><h3>项目备份</h3></div><span>{{ backups.length }} 份</span></div>
        <p v-if="!backups.length" class="empty-copy">还没有备份。业务数据首次成功保存后也会自动生成每日备份。</p>
        <div v-else class="data-list tall-list">
          <div v-for="item in backups" :key="item.id" class="data-row backup-row">
            <span><strong>{{ item.reason }} · Revision {{ item.revision }}</strong><small>{{ item.created_at }} · {{ fileSize(item.size_bytes) }} · {{ item.relative_path }}</small><small>{{ item.retained ? "长期保留" : "自动保留策略" }} · {{ item.exists ? "文件存在" : "文件缺失" }}</small></span>
            <div class="row-actions"><button :disabled="busy || !item.exists" @click="verifyBackup(item)">校验</button><button :disabled="busy" @click="toggleRetained(item)">{{ item.retained ? "取消保留" : "保留" }}</button><button :disabled="busy || !item.exists" @click="restore({ backup_id: item.id }, item.relative_path)">恢复副本</button></div>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>
