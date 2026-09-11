<script setup lang="ts">
import { computed, ref } from 'vue';
import { ArrowDown, ArrowUp, X } from 'lucide-vue-next';
import ConstraintCategoryStrip from './ConstraintCategoryStrip.vue';
import ConstraintParameters from './ConstraintParameters.vue';
import SearchableSelect from '../web-timetable/SearchableSelect.vue';
import { commonConstraintScenarios } from './itcConstraints';
import type { EntityRecord } from '../lib/sidecar';
import './web-workflows.css';

const props = defineProps<{ lessons: EntityRecord[]; tasks: EntityRecord[]; teachers: EntityRecord[];
  homerooms: EntityRecord[]; subjects: EntityRecord[]; busy: boolean; error: string; record?: EntityRecord | null }>();
const emit = defineEmits<{ close: []; save: [data: Record<string, unknown>] }>();
// Only expose save for rules actually compiled and validated by the local solver.
const executable = new Set(['NotOverlap', 'SameStart', 'SameTime', 'DifferentTime', 'Consecutive', 'Precedence', 'DifferentDays', 'SameDays', 'DifferentWeeks', 'SameRoom']);
const initial = commonConstraintScenarios.find(s => s.type === props.record?.type) ?? commonConstraintScenarios[0];
const category = ref('all');
const ruleKey = ref(initial.key);
const selectedRule = computed(() => commonConstraintScenarios.find(s => s.key === ruleKey.value) ?? initial);
const options = computed(() => commonConstraintScenarios.filter(s => category.value === 'all' || s.category === category.value));
const distribution = ref(initial.distributionType);
const name = ref(String(props.record?.name ?? initial.defaultName));
const required = ref(props.record ? props.record.severity === 'hard' : true);
const penalty = ref(Number(props.record?.weight ?? 100));
const validParameters = ref(true);
function parameters(): Record<string, unknown> {
  const value = props.record?.parameters;
  try { return typeof value === 'string' ? JSON.parse(value) : value as Record<string, unknown> ?? {}; } catch { return {}; }
}
const selectedIds = ref<string[]>(Array.isArray(parameters().lessonIds) ? (parameters().lessonIds as unknown[]).map(String) : []);
const query = ref('');
const teacher = ref('');
const homeroom = ref('');
const subject = ref('');
const taskById = computed(() => new Map(props.tasks.map(t => [t.id, t])));
const lookup = (items: EntityRecord[], id: unknown) => String(items.find(i => i.id === id)?.name ?? '未指定');
const lessonName = (lesson: EntityRecord) => {
  const task = taskById.value.get(String(lesson.teaching_task_id));
  return `${lookup(props.homerooms, task?.homeroom_id)} · ${lookup(props.subjects, task?.subject_id)} · ${lookup(props.teachers, task?.primary_teacher_id)} · 第${Number(lesson.lesson_index ?? 0) + 1}次`;
};
const visibleLessons = computed(() => props.lessons.filter(l => {
  const t = taskById.value.get(String(l.teaching_task_id));
  return (!teacher.value || t?.primary_teacher_id === teacher.value) && (!homeroom.value || t?.homeroom_id === homeroom.value)
    && (!subject.value || t?.subject_id === subject.value) && lessonName(l).includes(query.value.trim());
}));
const selectedLessons = computed(() => selectedIds.value.map(id => props.lessons.find(l => l.id === id)).filter((l): l is EntityRecord => !!l));
const canSave = computed(() => executable.has(selectedRule.value.type) && name.value.trim() && validParameters.value
  && selectedLessons.value.length === selectedIds.value.length && selectedIds.value.length >= selectedRule.value.minimumItems && !props.busy);
function chooseRule(key: unknown) {
  ruleKey.value = String(key); distribution.value = selectedRule.value.distributionType; name.value = selectedRule.value.defaultName;
}
function chooseCategory(value: string) { category.value = value; if (!options.value.some(s => s.key === ruleKey.value)) chooseRule(options.value[0].key); }
function add(id: string) { if (!selectedIds.value.includes(id)) selectedIds.value.push(id); }
function remove(id: string) { selectedIds.value = selectedIds.value.filter(value => value !== id); }
function move(index: number, delta: number) {
  const other = index + delta;
  if (other < 0 || other >= selectedIds.value.length) return;
  [selectedIds.value[index], selectedIds.value[other]] = [selectedIds.value[other], selectedIds.value[index]];
}
function save() {
  if (!canSave.value) return;
  emit('save', {id: props.record?.id, type: distribution.value, name: name.value.trim(), severity: required.value ? 'hard' : 'soft',
    enabled: props.record?.enabled ?? 1, weight: penalty.value, parameters: {lessonIds: [...selectedIds.value], commonScenario: selectedRule.value.key}});
}
</script>

<template>
  <div class="web-workflow web-timetable">
    <div class="modal-mask">
      <section class="modal-panel constraint-editor-modal" role="dialog" aria-modal="true" aria-labelledby="common-constraint-title">
        <header class="modal-header"><h3 id="common-constraint-title">{{ record ? '编辑自定义约束' : '新建自定义约束' }}</h3><button type="button" class="modal-close" aria-label="关闭" @click="emit('close')">×</button></header>
        <div class="modal-body">
          <section class="constraint-editor-panel in-modal">
            <div class="constraint-editor-tabs"><button type="button" class="active">常见约束</button></div>
            <div class="constraint-template-workspace">
              <div class="common-rule-picker">
                <div class="form-field"><span class="field-label">约束分类</span><ConstraintCategoryStrip :model-value="category" @update:model-value="chooseCategory" /></div>
                <label class="form-field"><span class="field-label">约束规则</span><SearchableSelect :model-value="ruleKey" @update:model-value="chooseRule"><option v-for="s in options" :key="s.key" :value="s.key">{{ s.title }}</option></SearchableSelect></label>
              </div>
              <div class="common-rule-description"><strong>{{ selectedRule.title }}</strong><p>{{ selectedRule.description }}</p><p class="common-rule-example">例如：{{ selectedRule.example }}</p></div>
              <p v-if="!executable.has(selectedRule.type)" class="local-rule-warning" role="status">此规则的本地排课支持尚未接入，暂不能保存。请选择其他规则；不会把未生效的规则当作已启用。</p>
              <form class="constraint-form-card" @submit.prevent="save">
                <p v-if="error" class="form-message error-copy" role="alert">{{ error }}</p>
                <label class="form-field"><span class="field-label">约束名称</span><input v-model="name" required /></label>
                <ConstraintParameters :key="ruleKey" v-model="distribution" :show-description="false" @validity="validParameters = $event" />
                <div class="form-field"><span class="field-label">关联课次（至少 {{ selectedRule.minimumItems }} 个{{ selectedRule.ordered ? '，按上课先后排列' : '' }}）</span>
                  <div class="constraint-transfer">
                    <section class="transfer-pane lesson-directory-pane"><header><strong>可选课次</strong><span>{{ visibleLessons.length }} 项</span></header>
                      <div class="local-lesson-filters">
                        <input v-model="query" placeholder="搜索班级、科目或教师" aria-label="搜索课次" />
                        <select v-model="homeroom" aria-label="筛选班级"><option value="">全部班级</option><option v-for="i in homerooms" :value="i.id" :key="i.id">{{ i.name }}</option></select>
                        <select v-model="subject" aria-label="筛选科目"><option value="">全部科目</option><option v-for="i in subjects" :value="i.id" :key="i.id">{{ i.name }}</option></select>
                        <select v-model="teacher" aria-label="筛选教师"><option value="">全部教师</option><option v-for="i in teachers" :value="i.id" :key="i.id">{{ i.name }}</option></select>
                      </div>
                      <button type="button" class="btn-secondary" :disabled="!visibleLessons.length" @click="visibleLessons.forEach(l => add(l.id))">加入筛选结果</button>
                      <div class="local-lesson-list"><button v-for="l in visibleLessons" :key="l.id" type="button" :disabled="selectedIds.includes(l.id)" @click="add(l.id)">{{ lessonName(l) }}<span>{{ selectedIds.includes(l.id) ? '已选' : '＋' }}</span></button><p v-if="!visibleLessons.length" class="transfer-empty">暂无可选课次，请先在课程计划中生成课次。</p></div>
                    </section>
                    <section class="transfer-pane"><header><strong>已选课次</strong><span>{{ selectedIds.length }} 项</span><button type="button" class="btn-secondary" @click="selectedIds = []">清空</button></header>
                      <div class="local-lesson-list"><div v-for="(l,index) in selectedLessons" :key="l.id" class="local-selected-lesson"><span>{{ lessonName(l) }}</span><div>
                        <button v-if="selectedRule.ordered" type="button" aria-label="上移" :disabled="index === 0" @click="move(index,-1)"><ArrowUp :size="16" /></button><button v-if="selectedRule.ordered" type="button" aria-label="下移" :disabled="index === selectedIds.length-1" @click="move(index,1)"><ArrowDown :size="16" /></button><button type="button" aria-label="移除课次" @click="remove(l.id)"><X :size="16" /></button>
                      </div></div><p v-if="!selectedIds.length" class="transfer-empty">尚未选择课次</p></div>
                    </section>
                  </div>
                </div>
                <div class="form-inline-row"><label class="checkbox-row"><input v-model="required" type="checkbox" />硬约束（必须满足）</label><label v-if="!required" class="penalty-row">违反扣分<input v-model.number="penalty" type="number" min="0" /></label></div>
                <div class="constraint-editor-actions"><button type="button" class="btn-secondary" @click="emit('close')">取消</button><button type="submit" class="btn-submit" :disabled="!canSave">{{ busy ? '正在保存…' : record ? '保存修改' : '保存约束' }}</button></div>
              </form>
            </div>
          </section>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.local-rule-warning { padding: 12px; background: #fff8df; color: #805e13; border-radius: 6px; }
.local-lesson-filters { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; padding: 10px; }
.local-lesson-filters input { grid-column: 1 / -1; }
.local-lesson-list { max-height: 300px; overflow: auto; padding: 10px; display: grid; gap: 6px; align-content: start; }
.local-lesson-list > button, .local-selected-lesson { display: flex; align-items: center; justify-content: space-between; padding: 10px; background: #f1f7f4; color: #285e50; text-align: left; font-size: 13px; border-radius: 5px; }
.local-selected-lesson > div { display: flex; }
.local-selected-lesson button { padding: 5px; }
.checkbox-row { display: flex; align-items: center; }
input[type="checkbox"] { appearance: auto; width: 18px; height: 18px; padding: 0; accent-color: #2f7d6d; }
</style>
