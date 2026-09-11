<script setup lang="ts">
import { onMounted, provide } from "vue";
import TimetableSettingsView from "../web-timetable/TimetableSettingsView.vue";
import { useTimetableEditor } from "../web-timetable/useTimetableEditor";
import { APP_CONTEXT_KEY } from "../web-timetable/appContext";
defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();
const editor = useTimetableEditor(value => emit("revision", value));
provide(APP_CONTEXT_KEY, editor);
onMounted(editor.loadSchoolData);
</script>
<template>
  <div class="web-timetable"><TimetableSettingsView /></div>
</template>
