<script setup lang="ts">
defineProps<{ modelValue: 'independent' | 'reuse'; canReuse: boolean; disabled?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [value: 'independent' | 'reuse'] }>();
</script>
<template>
  <fieldset class="template-planning-mode">
    <legend>选择课次规划方式</legend>
    <label><input type="radio" name="template-planning-mode" value="independent" :checked="modelValue === 'independent'" :disabled="disabled" @change="emit('update:modelValue', 'independent')" />独立课次安排</label>
    <label><input type="radio" name="template-planning-mode" value="reuse" :checked="modelValue === 'reuse'" :disabled="disabled || !canReuse" @change="emit('update:modelValue', 'reuse')" />复用默认安排</label>
  </fieldset>
</template>
<style scoped>
.template-planning-mode { display: flex; gap: 24px; flex-wrap: wrap; border: 0; padding: 12px 0; margin: 0; }
legend { font-weight: 600; margin-bottom: 12px; }
label { display: flex; align-items: center; gap: 8px; }
input { width: auto; }
</style>
