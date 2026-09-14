<script setup lang="ts">
import { onMounted, provide, watch } from "vue";
import TimetableSettingsView from "../web-timetable/TimetableSettingsView.vue";
import { useTimetableEditor } from "../web-timetable/useTimetableEditor";
import { APP_CONTEXT_KEY } from "../web-timetable/appContext";
const props = defineProps<{ revision: number; aiDraft?: { result: any; options: any; targetId: string } | null }>();
const emit = defineEmits<{ revision: [value: number]; saved: [value: number] }>();
let ready = false;
const editor = useTimetableEditor(value => emit("revision", value), value => emit("saved", value));
provide(APP_CONTEXT_KEY, editor);
const applyDraft = () => { if (ready && props.aiDraft) editor.applyAiTimetableDraft(props.aiDraft.result, props.aiDraft.options, props.aiDraft.targetId); };
onMounted(async () => { await editor.loadSchoolData(); ready = true; applyDraft(); });
watch(() => props.aiDraft, applyDraft);
</script>
<template>
  <div class="web-timetable"><TimetableSettingsView /></div>
</template>
