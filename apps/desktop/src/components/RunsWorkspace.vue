<script setup lang="ts">
import SchedulingView from "./SchedulingView.vue";

defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();
</script>

<template>
  <section class="runs-workspace">
    <SchedulingView :revision="revision" @revision="emit('revision', $event)" />
  </section>
</template>
