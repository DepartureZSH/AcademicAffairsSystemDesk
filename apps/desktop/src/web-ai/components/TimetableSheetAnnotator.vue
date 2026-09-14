<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { computed, ref, watch } from 'vue';
import type { TimetableSheet, TimetableSheetCell, TimetableAiOptions } from '../utils/timetableAi';
type Roles = NonNullable<TimetableAiOptions['cell_roles']>;
const props = defineProps<{ sheet: TimetableSheet; modelValue: Roles; headerRow?: number; disabled?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [value: Roles] }>();
const selected = ref<string[]>([]);
const anchor = ref<TimetableSheetCell | null>(null);
const role = ref<keyof typeof labels>('course');
const labels = { course: '课程单元格', custom: '自定义单元格', detail: '课程附属字段', header: '标题区', axis: '时间轴行头' };
function cellLabel(cell: TimetableSheetCell) {
  return cell.row === props.headerRow ? '主表头' : props.modelValue[cell.address] ? labels[props.modelValue[cell.address]] : '未标注';
}
function clearSelection() { selected.value = []; anchor.value = null; }
watch(() => props.sheet, () => { selected.value = []; anchor.value = null; });
const rows = computed(() => Array.from({ length: props.sheet.rows }, (_, index) => (props.sheet.cells || []).filter(c => c.row === index + 1 && (!c.merge || c.merge.anchor === c.address))));
function columnName(index: number): string { return index > 26 ? columnName(Math.floor((index - 1) / 26)) + String.fromCharCode(65 + (index - 1) % 26) : String.fromCharCode(64 + index); }
function select(cell: TimetableSheetCell, range: boolean) {
  if (props.disabled) return;
  if (range && anchor.value) {
    const first = anchor.value;
    selected.value = (props.sheet.cells || []).filter(c => (!c.merge || c.merge.anchor === c.address)
      && c.row <= Math.max(first.row, cell.row) && c.row + (c.merge?.rowspan || 1) - 1 >= Math.min(first.row, cell.row)
      && c.column <= Math.max(first.column, cell.column) && c.column + (c.merge?.colspan || 1) - 1 >= Math.min(first.column, cell.column)).map(c => c.address);
  } else {
    selected.value = selected.value.includes(cell.address) ? selected.value.filter(c => c !== cell.address) : [...selected.value, cell.address];
    anchor.value = cell;
  }
}
function apply(clear = false) {
  if (props.disabled || !selected.value.length) return;
  const value = { ...props.modelValue };
  for (const address of selected.value) { if (clear) delete value[address]; else value[address] = role.value; }
  emit('update:modelValue', value);
  clearSelection();
}
</script>
<template>
  <section class="sheet-annotations" aria-label="原表分区标注">
    <header><strong>原表分区标注</strong><span>已选 {{ selected.length }} 格 · 已标注 {{ Object.keys(modelValue).length }} 格</span></header>
    <div class="annotation-tools">
      <select v-model="role" aria-label="单元格类型" :disabled="disabled"><option v-for="(label, value) in labels" :key="value" :value="value">{{ label }}</option></select>
      <button type="button" :disabled="disabled || !selected.length" @click="apply()">标注选中区域</button>
      <button type="button" class="btn-secondary" :disabled="disabled || !selected.length" @click="apply(true)">取消标注</button>
      <button type="button" class="btn-secondary" :disabled="disabled || !selected.length" @click="clearSelection">取消选择</button>
    </div>
    <div class="annotation-table" tabindex="0" aria-label="Excel原表">
      <table><thead><tr><th scope="col">行</th><th v-for="column in sheet.columns" :key="column" scope="col">{{ columnName(column) }}</th></tr></thead><tbody>
        <tr v-for="(row, index) in rows" :key="index"><th scope="row">{{ index + 1 }}</th><td v-for="cell in row" :key="cell.address" :rowspan="cell.merge?.rowspan || 1" :colspan="cell.merge?.colspan || 1" :data-role="modelValue[cell.address]" :class="{ selected: selected.includes(cell.address) }">
          <button type="button" :disabled="disabled" :aria-pressed="selected.includes(cell.address)" :aria-label="`${cell.address} ${cell.value || '空白'} ${cellLabel(cell)}`" @click="select(cell, $event.shiftKey)"><span>{{ cell.value || ' ' }}</span><small v-if="modelValue[cell.address] || cell.row === headerRow">{{ cellLabel(cell) }}</small></button>
        </td></tr>
      </tbody></table>
    </div>
  </section>
</template>
<style scoped>
.sheet-annotations { min-width: 0; border-top: 1px solid #dce5df; padding-top: 16px; }
header, .annotation-tools { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 12px; }
header span { margin-left: auto; color: #64736d; font-size: 12px; }
.annotation-tools button, select { font-size: 13px; min-height: 34px; padding: 6px 10px; width: auto; }
.annotation-table { overflow: auto; max-height: 420px; border: 1px solid #dce5df; }
table { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 12px; }
th, td { border-right: 1px solid #dce5df; border-bottom: 1px solid #dce5df; padding: 0; min-width: 90px; }
th { background: #f0f4f2; padding: 6px; }
thead th { position: sticky; top: 0; z-index: 1; }
th:first-child { min-width: 30px; }
td button { display: flex; flex-direction: column; gap: 4px; width: 100%; min-height: 42px; padding: 8px; border: 0; border-radius: 0; background: transparent; color: #29443e; box-shadow: none; font: inherit; white-space: pre-wrap; overflow-wrap: anywhere; }
td[data-role=course] { background: #e9f5ee; } td[data-role=custom] { background: #fff4db; } td[data-role=detail] { background: #eaf2fa; }
td[data-role=header], td[data-role=axis] { background: #f0f4f2; }
td.selected { outline: 2px solid #2d7b6c; outline-offset: -2px; }
small { color: #52695f; font-size: 11px; }
button:focus-visible { outline: 2px solid #2d7b6c; outline-offset: -2px; }
</style>
