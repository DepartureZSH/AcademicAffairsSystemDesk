<script setup lang="ts">
import { ref } from "vue";
import SchedulingView from "./SchedulingView.vue";
import TimetableView from "./TimetableView.vue";

defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();
const activeTab = ref<"run" | "result">("run");
</script>

<template>
  <section class="runs-workspace">
    <div class="runs-tabs" role="tablist" aria-label="排课运行">
      <button :class="{ active: activeTab === 'run' }" @click="activeTab = 'run'">排课运行</button>
      <button :class="{ active: activeTab === 'result' }" @click="activeTab = 'result'">候选课表</button>
    </div>
    <SchedulingView v-if="activeTab === 'run'" :revision="revision" @revision="emit('revision', $event)" />
    <TimetableView v-else :revision="revision" @revision="emit('revision', $event)" />
  </section>
</template>
