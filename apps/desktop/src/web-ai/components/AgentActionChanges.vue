<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { computed, inject } from "vue";
import { APP_CONTEXT_KEY } from "./appContext";
import { buildAgentChangeTables, changeTargets } from "../utils/agentChangeTables";

const { selectedAgentAction, selectedAgentActionItems, selectedAgentActionContextItems, selectedAgentActionItemTotal, agentActionItemsLoading,
  agentActionItemQuery, agentActionItemTarget, agentActionItemOperation, loadSelectedAgentActionItems,
  schoolData, planningData, durationText, constraintTypeLabel } = inject(APP_CONTEXT_KEY)!;
const warnings = computed(() => {
  const values = selectedAgentAction?.value?.preview?.warnings;
  return Array.isArray(values) ? values.filter((value): value is string => typeof value === "string") : [];
});
const tables = computed(() => buildAgentChangeTables(selectedAgentActionItems.value, {
  teacher: schoolData.value.teachers, homeroom: schoolData.value.homerooms, subject: schoolData.value.subjects,
  room: schoolData.value.rooms, room_type: schoolData.value.room_types,
  timetable_template: schoolData.value.weekly_timetable_templates, period: schoolData.value.weekly_timetable_periods,
  course_plan: planningData.value.course_plans, task: planningData.value.teaching_tasks, lesson: planningData.value.task_lessons,
}, { duration: durationText, constraintType: constraintTypeLabel }, selectedAgentActionContextItems?.value.length ? selectedAgentActionContextItems.value : selectedAgentActionItems.value));
async function search(reset = true) {
  try { await loadSelectedAgentActionItems(reset); }
  catch { /* The request helper reports errors within the assistant. */ }
}
</script>

<template>
  <section class="agent-action-audit-section change-ledger" :aria-busy="agentActionItemsLoading">
    <p v-for="warning in warnings" :key="warning" class="change-warning" role="note">{{ warning }}</p>
    <header class="change-ledger-header">
      <h4>变更明细 <small>已展示 {{ selectedAgentActionItems.length }} / {{ selectedAgentActionItemTotal }} 项</small></h4>
      <div class="change-legend"><span class="op-create">新增</span><span class="op-update">修改</span><span class="op-delete">删除</span></div>
    </header>
    <form class="change-filters" @submit.prevent="search()">
      <input v-model="agentActionItemQuery" maxlength="80" aria-label="搜索变更明细" placeholder="搜索名称或来源" />
      <select v-model="agentActionItemTarget" aria-label="数据类型" @change="search()">
        <option value="">全部数据</option><option v-for="(label, key) in changeTargets" :key="key" :value="key">{{ label }}</option>
      </select>
      <select v-model="agentActionItemOperation" aria-label="操作类型" @change="search()">
        <option value="">全部操作</option><option value="create">新增</option><option value="update">修改</option>
        <option value="delete">删除</option><option value="skip">跳过</option><option value="run">发起排课</option>
      </select>
      <button type="submit" class="btn-secondary" :disabled="agentActionItemsLoading">搜索</button>
    </form>
    <section v-for="table in tables" :key="table.target" class="change-group">
      <h5>{{ table.title }} <span>{{ table.rows.length }} 项</span></h5>
      <div class="change-table-scroll" tabindex="0" role="region" :aria-label="table.title + '变更表格'">
        <table class="change-table">
          <thead><tr><th scope="col">操作</th><th v-for="column in table.columns" :key="column.key" scope="col">{{ column.label }}</th><th scope="col">执行状态</th><th scope="col">来源</th></tr></thead>
          <tbody>
            <tr v-for="row in table.rows" :key="row.id" :class="'op-' + row.operation">
              <td><span class="change-operation">{{ row.operationLabel }}</span></td>
              <td v-for="cell in row.cells" :key="cell.key" :class="{ 'changed-cell': cell.changed }">
                <details v-if="cell.expanded" class="change-cell-details"><summary>{{ cell.changed ? '查看修改前后' : '查看内容' }}</summary>
                  <div v-if="cell.changed" class="old-value"><small>修改前</small>{{ cell.before }}</div>
                  <div><small v-if="cell.changed">修改后</small>{{ cell.after }}</div>
                </details>
                <template v-else><div v-if="cell.changed" class="old-value"><small>修改前</small>{{ cell.before }}</div><div><small v-if="cell.changed">修改后</small>{{ cell.after }}</div></template>
              </td>
              <td>{{ row.status }}<p v-if="row.error" class="change-error">{{ row.error }}</p></td><td class="change-source">{{ row.source }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <p v-if="agentActionItemsLoading" class="change-empty" role="status">正在加载变更明细...</p>
    <p v-else-if="!selectedAgentActionItems.length" class="change-empty">没有符合筛选条件的明细。</p>
    <button v-if="selectedAgentActionItems.length < selectedAgentActionItemTotal" type="button" class="btn-secondary change-more" :disabled="agentActionItemsLoading" @click="search(false)">加载更多</button>
  </section>
</template>

<style scoped>
.change-ledger { min-width: 0; display: grid; gap: 14px; padding: 0; border: 0; border-radius: 0; background: transparent; }
.change-warning { margin: 0; padding: 10px 12px; border-left: 3px solid #b58a29; background: #fff7dd; color: #785d20; font-size: 13px; line-height: 1.6; }
.change-ledger-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
.change-ledger-header h4 { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; margin: 0; font-size: 15px; }
.change-ledger-header small, .change-group h5 span { font-size: 12px; font-weight: 400; color: #63736e; }
.change-legend { display: flex; gap: 8px; font-size: 12px; }
.change-legend span { padding: 3px 8px; border-radius: 4px; }
.change-filters { display: flex; flex-wrap: wrap; gap: 8px; }
.change-filters input { flex: 1 1 200px; min-width: 0; }
.change-filters select { flex: 1 1 110px; min-width: 0; max-width: 180px; }
.change-filters input, .change-filters select { border: 1px solid #d8e2dd; border-radius: 6px; padding: 8px 10px; background: #fff; color: #354d43; font-size: 13px; }
.change-group { min-width: 0; }
.change-group h5 { margin: 0 0 8px; font-size: 14px; display: flex; gap: 8px; align-items: baseline; }
.change-table-scroll { overflow: auto; max-width: 100%; max-height: min(420px, 45dvh); scrollbar-gutter: stable; overscroll-behavior-x: contain; border: 1px solid #dfe7e2; border-radius: 6px; }
.change-table-scroll:focus-visible { outline: 2px solid #2f7d6d; outline-offset: 2px; }
.change-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
.change-table th, .change-table td { padding: 10px 12px; border-bottom: 1px solid #dfe7e2; vertical-align: top; min-width: 110px; max-width: 320px; line-height: 1.6; overflow-wrap: anywhere; }
.change-table th { position: sticky; top: 0; z-index: 1; background: #eff4f1; box-shadow: 0 1px 0 #dfe7e2; color: #51665c; font-weight: 600; white-space: nowrap; }
.change-table td { white-space: pre-wrap; }
.change-table td:first-child, .change-table th:first-child { min-width: 70px; }
.change-table tr:last-child td { border-bottom: 0; }
.op-create { background: #eff9f2; color: #24653c; }
.op-delete { background: #fff0ef; color: #a33e35; }
.op-update { background: #fffae9; color: #785d20; }
.op-skip, .op-run { background: #f7f9fa; color: #53626b; }
.change-table .changed-cell { background: #fff0bf; }
.change-operation { font-weight: 600; white-space: nowrap; }
.old-value { color: #7b7164; text-decoration: line-through; margin-bottom: 6px; }
.change-table small { display: block; font-size: 11px; font-weight: 400; text-decoration: none; opacity: .85; }
.change-cell-details { min-width: 180px; max-width: 320px; }
.change-cell-details summary { cursor: pointer; font-weight: 500; }
.change-cell-details[open] summary { margin-bottom: 8px; }
.change-cell-details > div { max-height: 260px; overflow: auto; overscroll-behavior: contain; }
.change-source { font-size: 12px; color: #66786d; }
.change-error { color: #a33e35; margin: 4px 0 0; }
.change-empty { margin: 12px 0; color: #75867b; text-align: center; font-size: 13px; }
.change-more { justify-self: center; }
</style>
