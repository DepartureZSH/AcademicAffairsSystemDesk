<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { constraintDefinition, constraintValues, encodeConstraint } from "./itcConstraints";
const props = withDefaults(defineProps<{ modelValue: string; showDescription?: boolean }>(), { showDescription: true });
const emit = defineEmits<{ "update:modelValue": [value: string]; validity: [valid: boolean] }>();
const definition = computed(() => constraintDefinition(props.modelValue));
const values = ref<number[]>([]);
const error = ref("");
watch(() => props.modelValue, value => { values.value = constraintValues(value); error.value = ""; emit("validity", true); }, { immediate: true });
function update(event: Event) {
  const input = event.target as HTMLInputElement;
  try { emit("update:modelValue", encodeConstraint(props.modelValue, values.value)); error.value = ""; input.setCustomValidity(""); }
  catch (exc) { error.value = (exc as Error).message; input.setCustomValidity(error.value); }
  emit("validity", !error.value);
}
</script>
<template>
  <div v-if="definition" class="itc-rule-fields">
    <p v-if="showDescription">{{ definition.description }}</p>
    <div v-if="definition.parameters.length" class="itc-parameter-grid">
      <label v-for="(parameter, index) in definition.parameters" :key="parameter.label" class="form-field">
        <span>{{ parameter.label }}（{{ parameter.unit }}）</span>
        <input v-model.number="values[index]" type="number" :min="parameter.min" :max="parameter.max" :step="parameter.step" required @input="update" />
      </label>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
  </div>
</template>
<style scoped>
.itc-rule-fields { min-width: 0; }
.itc-rule-fields p { margin: 0 0 12px; color: var(--muted, #617773); font-size: 13px; line-height: 1.65; }
.itc-rule-fields [role="alert"] { color: #b42318; }
.itc-parameter-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 12px; }
.itc-parameter-grid input { width: 100%; box-sizing: border-box; }
</style>
