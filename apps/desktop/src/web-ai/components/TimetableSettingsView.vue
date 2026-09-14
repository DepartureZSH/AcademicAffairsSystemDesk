<script setup lang="ts">
// The existing desktop transplant owns its local timetable context.
import CalendarView from '../../components/CalendarView.vue';
import { inject } from 'vue';
import { APP_CONTEXT_KEY } from './appContext';
const { aiTimetableDraft, timetableTemplateSaveRevision, loadOverview } = inject(APP_CONTEXT_KEY)!;
function saved() { timetableTemplateSaveRevision.value++; void loadOverview(); }
</script>
<template><CalendarView :revision="0" :ai-draft="aiTimetableDraft" @saved="saved" /></template>
