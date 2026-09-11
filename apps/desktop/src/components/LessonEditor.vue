<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import type { EntityRecord } from '../lib/sidecar';
import { cloneLessons, draftLesson, fitsLesson, priorities, type LessonDraft, type PreferredTime } from '../lib/lessonPlanning';
const props = defineProps<{ lessons: LessonDraft[]; slots: EntityRecord[]; rooms: EntityRecord[]; weeks: string; days: string; defaultDuration: number; busy: boolean; error: string }>();
const emit = defineEmits<{ apply: [value: LessonDraft[]]; save: [value: LessonDraft[]]; cancel: [] }>();
const drafts = ref(cloneLessons(props.lessons)), picker = ref<LessonDraft | null>(null);
const panel = ref<HTMLElement | null>(null);
watch(picker, async () => { await nextTick(); panel.value?.querySelector<HTMLElement>('button:not(:disabled)')?.focus(); });
const selectedWeeks = ref(props.weeks), priority = ref(0), timeDraft = ref<PreferredTime[]>([]), message = ref('');
const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const periods = computed(() => [...new Set(props.slots.map(item => Number(item.period_index)))].sort((a,b) => a-b));
const changed = computed(() => JSON.stringify(drafts.value) !== JSON.stringify(props.lessons));
function add() { drafts.value.push(draftLesson({ duration_slots: props.defaultDuration }, props.weeks, props.days, drafts.value.length)); }
function copy(lesson: LessonDraft) { const clone = cloneLessons([lesson])[0]; delete clone.id; clone.key = crypto.randomUUID(); clone.label += '（副本）'; drafts.value.push(clone); }
function openTime(lesson: LessonDraft) { picker.value = lesson; selectedWeeks.value = lesson.week_bits; timeDraft.value = JSON.parse(JSON.stringify(lesson.planning_config.preferred_times)); message.value = ''; }
function slotFor(period: number, weekday: number) { return props.slots.find(item => Number(item.period_index) === period && Number(item.weekday) === weekday); }
function canPick(slot?: EntityRecord) { return !!slot && !!picker.value && picker.value.day_bits[Number(slot.weekday) - 1] !== '0' && fitsLesson(slot, props.slots, picker.value.duration_slots); }
function mark(slot: EntityRecord) { return timeDraft.value.find(item => item.time_slot_id === slot.id && item.week_bits === selectedWeeks.value); }
function setTime(slot: EntityRecord, toggle = true) {
  if (!canPick(slot) || !selectedWeeks.value.includes('1')) { message.value = '请至少选择一周，并检查课长是否能放入所选课节。'; return; }
  const existing = mark(slot);
  timeDraft.value = timeDraft.value.filter(item => item !== existing);
  if (!toggle || !existing || existing.penalty !== priority.value) timeDraft.value.push({ time_slot_id: slot.id, week_bits: selectedWeeks.value, penalty: priority.value });
  message.value = '';
}
function preset(kind: 'all' | 'odd' | 'even') { selectedWeeks.value = (picker.value?.week_bits || props.weeks).split('').map((bit, index) => bit === '1' && (kind === 'all' || (index % 2 === 0 ? kind === 'odd' : kind === 'even')) ? '1' : '0').join(''); }
function toggleWeek(index: number) { selectedWeeks.value = selectedWeeks.value.split('').map((bit, i) => i === index ? bit === '1' ? '0' : '1' : bit).join(''); }
function timeLabel(slot: EntityRecord) { const fmt = (n: unknown) => `${String(Math.floor(Number(n)/60)).padStart(2,'0')}:${String(Number(n)%60).padStart(2,'0')}`; return `${fmt(slot.start_time_minutes)}–${fmt(slot.end_time_minutes)}`; }
function ruleSummary(rule: PreferredTime) { const slot = props.slots.find(item => item.id === rule.time_slot_id); const weeks = rule.week_bits.split('').flatMap((bit, i) => bit === '1' ? [i+1] : []); return `${slot ? `${weekdays[Number(slot.weekday)-1]} · ${slot.label}` : '课节已变更，请重新选择'} · 第 ${weeks.join('、')} 周 · ${priorities.find(item => item.value === rule.penalty)?.label}`; }
function finishTime() { if (picker.value) picker.value.planning_config.preferred_times = JSON.parse(JSON.stringify(timeDraft.value)); picker.value = null; }
function finish(save: boolean) {
  if (drafts.value.some(item => !Number.isInteger(item.duration_slots) || item.duration_slots < 1 || item.duration_slots > 1440)) { message.value = '课长应为正整数。'; return; }
  if (save) emit('save', cloneLessons(drafts.value));
  else emit('apply', cloneLessons(drafts.value));
}
function cancel() { if (props.busy) return; if (picker.value) { picker.value = null; return; } if (!changed.value || window.confirm('放弃本次课次修改并返回？')) emit('cancel'); }
defineExpose({ requestClose: cancel });
</script>

<template>
  <section ref="panel" class="local-lesson-editor" @keydown.esc.stop.prevent="cancel">
    <header class="lesson-sheet-heading"><div><h3>{{ picker ? '选择期望上课时间' : '课次编辑' }}</h3><p>{{ picker ? '选择周频率和优先级，再点击周候选时间。算法从候选中选择一组时间安排。' : '集中维护每个课次的启用状态、课长、期望时间和教室。保存授课任务后生效。' }}</p></div><button v-if="!picker" type="button" class="secondary-button" :disabled="busy" @click="add">新增课次</button></header>
    <fieldset :disabled="busy" class="lesson-sheet-content">
      <template v-if="!picker">
        <div class="lesson-draft-notice"><strong>本次课次变动</strong><span>{{ changed ? '有待保存的修改' : '尚无修改' }} · {{ drafts.length }} 个课次</span></div>
        <article v-for="(lesson, index) in drafts" :key="lesson.key" class="local-lesson-card">
          <div class="lesson-card-title"><label>课次名称<input v-model="lesson.label" :aria-label="`第${index+1}课次名称`" /></label><label class="lesson-enabled"><input v-model="lesson.enabled" type="checkbox" />启用</label><label>连续节数<input v-model.number="lesson.duration_slots" type="number" min="1" max="1440" step="1" :aria-label="`第${index+1}课次连续节数`" /></label></div>
          <p class="lesson-detail-line"><strong>期望上课时间</strong><span>{{ lesson.planning_config.preferred_times.length ? `${lesson.planning_config.preferred_times.length} 组候选／禁排时间` : '全部可行时间 · 最高优先' }}</span></p>
          <div class="lesson-inline-actions"><button type="button" class="secondary-button" @click="openTime(lesson)">选择期望时间</button><button type="button" class="secondary-button" :disabled="!lesson.planning_config.preferred_times.length" @click="lesson.planning_config.preferred_times = []">清空时间</button></div>
          <div class="lesson-room-choice"><label>课次教室<select v-model="lesson.planning_config.room_mode"><option value="default">默认教室（沿用授课任务）</option><option value="custom">自定义教室</option></select></label><div v-if="lesson.planning_config.room_mode === 'custom'" class="lesson-room-options"><label v-for="room in rooms" :key="room.id"><input v-model="lesson.planning_config.room_ids" type="checkbox" :value="room.id" />{{ room.name }}</label><p>可选多间候选教室，由排课选择一间；未选择时不安排教室。</p></div></div>
          <div class="lesson-inline-actions"><button type="button" class="secondary-button" @click="copy(lesson)">复制课次</button><button type="button" class="danger-button" @click="drafts.splice(index, 1)">删除课次</button></div>
        </article>
        <p v-if="!drafts.length" class="class-list-empty">尚无课次，点击“新增课次”开始配置。</p>
      </template>
      <template v-else>
        <section class="lesson-preference-section"><h4>周频率</h4><div class="lesson-inline-actions"><button type="button" class="secondary-button" @click="preset('all')">全部周</button><button type="button" class="secondary-button" @click="preset('odd')">单周</button><button type="button" class="secondary-button" @click="preset('even')">双周</button></div><div class="lesson-week-picker"><button v-for="(bit, index) in picker.week_bits" :key="index" type="button" :disabled="bit !== '1'" :class="{active: selectedWeeks[index] === '1'}" :aria-pressed="selectedWeeks[index] === '1'" @click="toggleWeek(index)">第{{ index+1 }}周</button></div></section>
        <section class="lesson-preference-section"><h4>候选优先级</h4><div class="lesson-priority-picker"><button v-for="option in priorities" :key="option.value" type="button" :class="[`priority-${option.value}`, {active: priority === option.value}]" :aria-pressed="priority === option.value" @click="priority = option.value">{{ option.label }}</button></div></section>
        <section class="lesson-preference-section"><div class="lesson-sheet-heading"><h4>周候选时间</h4><button type="button" class="secondary-button" @click="slots.filter(canPick).forEach(slot => setTime(slot, false))">按当前优先级全选</button></div><p>未选择任何候选时默认全部可行时间；“绝对不排”始终优先。连续课次需有足够相邻课节。</p><p v-if="!slots.length" role="alert">暂无可用课节，请先在课表设置中保存模板。</p><div class="lesson-time-scroll"><table class="lesson-time-grid"><thead><tr><th>节次</th><th v-for="day in weekdays" :key="day">{{ day }}</th></tr></thead><tbody><tr v-for="period in periods" :key="period"><th>第{{ period+1 }}节</th><td v-for="day in 7" :key="day"><template v-for="slot in [slotFor(period, day)].filter(Boolean) as EntityRecord[]" :key="slot.id"><button type="button" :disabled="!canPick(slot)" :class="mark(slot) ? `priority-${mark(slot)!.penalty}` : ''" :aria-label="`${weekdays[day-1]}第${period+1}节`" :aria-pressed="!!mark(slot)" @click="setTime(slot)"><strong>{{ slot.label }}</strong><small>{{ timeLabel(slot) }}</small><span>{{ mark(slot) ? priorities.find(item => item.value === mark(slot)!.penalty)?.label : canPick(slot) ? '点击选择' : '课长不适用' }}</span></button></template></td></tr></tbody></table></div></section>
        <section class="lesson-preference-section"><h4>已选时间 · {{ timeDraft.length }} 组</h4><div v-for="(rule, index) in timeDraft" :key="`${rule.time_slot_id}-${rule.week_bits}`" class="lesson-rule-row"><span>{{ ruleSummary(rule) }}</span><button type="button" class="danger-button" @click="timeDraft.splice(index, 1)">移除</button></div></section>
      </template>
    </fieldset>
    <p v-if="message || error" role="alert" class="error-copy">{{ message || error }}</p>
    <footer class="lesson-sheet-footer"><template v-if="picker"><button type="button" class="primary-button" @click="finishTime">确认期望时间</button><button type="button" class="secondary-button" @click="picker = null">取消</button></template><template v-else><button type="button" class="primary-button" :disabled="busy" @click="finish(true)">{{ busy ? '保存中…' : '保存授课任务' }}</button><button type="button" class="secondary-button" :disabled="busy" @click="finish(false)">完成并返回</button><button type="button" class="secondary-button" :disabled="busy" @click="cancel">{{ changed ? '放弃本次修改' : '返回' }}</button></template></footer>
  </section>
</template>
