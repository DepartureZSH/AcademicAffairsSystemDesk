<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { inject, ref } from "vue";
import { FileSpreadsheet } from "lucide-vue-next";
import { APP_CONTEXT_KEY } from "./appContext";
const props = defineProps<{ scene: "timetable" | "rooms" | "school" | "planning" | "constraints" }>();
const { downloadOfficialWorkbook } = inject(APP_CONTEXT_KEY)!;
const labels = { timetable: "课表设置", rooms: "教室设置", school: "学校数据", planning: "课程计划", constraints: "约束配置" };
const error = ref("");
const busy = ref(false);
async function download() {
  if (busy.value || !['rooms', 'school', 'planning'].includes(props.scene)) return;
  const scene = props.scene;
  const path = `/api/agent/official-templates/${scene}.xlsx`;
  busy.value = true;
  error.value = "";
  try {
    await downloadOfficialWorkbook(scene);
  } catch { error.value = "模板下载失败，请重试。"; }
  finally { busy.value = false; }
}
</script>

<template>
  <div v-if="scene === 'rooms' || scene === 'school' || scene === 'planning'" class="official-workbook-entry">
    <button type="button" class="btn-secondary" :disabled="busy" :aria-busy="busy" @click="download"><FileSpreadsheet :size="16" />{{ busy ? '正在下载…' : 'Excel 模板' }}</button>
    <span v-if="error" role="alert">{{ error }}</span>
  </div>
</template>

<style scoped>
.official-workbook-entry { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.official-workbook-entry button { display: inline-flex; align-items: center; gap: 6px; }
.official-workbook-entry [role="alert"] { font-size: 12px; color: #a33e35; }
</style>
