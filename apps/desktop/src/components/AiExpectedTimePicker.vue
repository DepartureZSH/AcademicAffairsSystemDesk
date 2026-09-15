<script setup lang="ts">
import {X} from 'lucide-vue-next';
import SearchableSelect from '../web-course-editor/SearchableSelect.vue';
import {useCourseEditor} from '../web-course-editor/useCourseEditor';
const props = defineProps<{context: Record<string, any>}>();
const emit = defineEmits<{close: []; saved: [revision: number]}>();
const {showGuide,activeGuideStepIndex,guideTargetRect,guideMissingTarget,teachingTaskForm,courseLessonDrafts,defaultRoomSearch,showDefaultRoomOptions,showLessonRoomOptions,loading,courseArrangementSaving,courseArrangementNotice,selectedTeachingTaskId,planningViewMode,selectedLessonImportTaskId,teacherSearch,teacherSearchInput,showTeacherOptions,showCoursePreferredPicker,coursePreferredPickerTitle,showLessonEditorSheet,courseWeekFrequencyCollapsed,coursePreferredRuleForm,coursePreferredPriorityOptions,termWeekOptions,activeGuideSteps,activeGuideStep,guideProgressLabel,guideHighlightStyle,guideCardStyle,startGuide,nextGuideStep,previousGuideStep,restartGuide,skipGuide,weekFrequencyPresets,applyCoursePreferredWeekPreset,closeCoursePreferredPicker,openLessonEditorSheet,closeLessonEditorSheet,toggleCoursePreferredRuleWeek,lessonEditorChanges,lessonEditorHasChanges,toggleCoursePreferredGridCell,toggleCoursePreferredGridRow,clearActiveCoursePreferredRules,clearCourseLessonPreferredTimes,coursePreferredCandidatePresetOptions,applyCoursePreferredCandidatePreset,openCoursePreferredPicker,saveCoursePreferredRule,selectedCourseNotScheduled,selectedSubject,editableCourseLessonDrafts,selectedPlanningHomeroom,selectedCoursePlanTasks,lessonImportTaskOptions,unitsToMinutes,durationText,selectedCoursePreferredSummary,coursePreferredPickerGrid,coursePreferredPickerRows,selectedCoursePreferredRuleCount,coursePreferredCellButtonLabel,coursePreferredPickerHint,coursePreferredPickerSummary,selectedSubjectDurationSlots,addCourseLesson,copyCourseLesson,deleteCourseLesson,activeCoursePreferredLesson,coursePreferredAllPeriodsDisabled,selectedDefaultRooms,filteredDefaultRoomOptions,selectedLessonRooms,filteredLessonRoomOptions,lessonRoomSearchValue,setLessonRoomSearch,hideDefaultRoomOptionsSoon,hideLessonRoomOptionsSoon,addDefaultRoom,removeDefaultRoom,addLessonRoom,removeLessonRoom,setUsesRooms,setLessonRoomMode,defaultRoomSelectionSummary,lessonRoomSelectionSummary,taskTeacherName,filteredTeacherOptions,syncTeacherSearchFromSelection,onTeacherSearchInput,selectTeacherOption,clearTeacherSelection,hideTeacherOptionsSoon,bitsToWeekLabel,taskImportLabel,isTeachingTaskActive,selectTeachingTask,startNewTeachingTask,importLessonSettingsFromSelectedTask,taskLessonCount,markSelectedCourseNotScheduled,resumeSelectedCourseScheduling,saveCourseArrangement,deleteCourseArrangement,recordName,subjectEditorOpen,subjectEditorPanel,courseCandidateScale,markCourseCandidateScaleAdjusted,closeSubjectEditor,handleSubjectEditorKeydown,error} = useCourseEditor(props,emit);
</script>
<template><Teleport to="body"><div class="web-course-editor"><div v-if="showCoursePreferredPicker" class="bottom-sheet-mask course-preferred-sheet-mask">
  <section class="bottom-sheet room-unavailable-sheet course-preferred-sheet room-rule-sheet" aria-label="选择课次期望上课时间" data-guide-id="course-preferred-sheet">
    <header class="bottom-sheet-header">
      <div>
        <span>{{ coursePreferredPickerTitle ? '时间模板' : '课次期望上课时间' }}</span>
        <h3>{{ coursePreferredPickerTitle || selectedSubject?.name || '当前课程' }}</h3>
        <p class="sheet-context-hint">{{ coursePreferredPickerHint() }}</p>
      </div>
      <div v-if="!coursePreferredPickerTitle" class="sheet-actions">
        <button type="button" class="btn-secondary guide-sheet-button" @click="startGuide('course_preferred_sheet', true)">
          新手指导
        </button>
      </div>
    </header>
    <div class="room-unavailable-body course-preferred-body room-rule-body">
      <div class="room-picker-summary" data-guide-id="course-preferred-summary">
        <strong>候选上课时间</strong>
        <span>{{ coursePreferredPickerSummary() }}</span>
      </div>
      <div class="course-week-frequency" data-guide-id="course-preferred-week" :class="{ collapsed: courseWeekFrequencyCollapsed }">
        <div class="frequency-title">
          <div class="frequency-title-copy">
            <strong>周频率</strong>
            <span>{{ bitsToWeekLabel(coursePreferredRuleForm.week_bits) }}</span>
          </div>
          <button
            type="button"
            class="btn-secondary compact-toggle"
            @click="courseWeekFrequencyCollapsed = !courseWeekFrequencyCollapsed"
          >
            {{ courseWeekFrequencyCollapsed ? '展开' : '收起' }}
          </button>
        </div>
        <div class="preset-chip-row">
          <button
            v-for="preset in weekFrequencyPresets()"
            :key="`course-week-${preset.key}`"
            type="button"
            class="preset-chip"
            @click="applyCoursePreferredWeekPreset(preset.weeks)"
          >
            {{ preset.label }}
          </button>
        </div>
        <div v-if="!courseWeekFrequencyCollapsed" class="week-picker">
          <button
            v-for="week in termWeekOptions"
            :key="week.index"
            type="button"
            :class="{ active: coursePreferredRuleForm.week_bits[week.index] === '1' }"
            @click="toggleCoursePreferredRuleWeek(week.index)"
          >
            {{ week.label }}
          </button>
        </div>
      </div>
      <div class="course-priority-panel" data-guide-id="course-preferred-priority">
        <div class="frequency-title">
          <div class="frequency-title-copy">
            <strong>候选优先级</strong>
            <span>颜色越浅越优先，最浅对应最高优先级</span>
          </div>
        </div>
        <div class="priority-choice-row">
          <button
            v-for="option in coursePreferredPriorityOptions"
            :key="option.penalty"
            type="button"
            class="priority-choice"
            :class="[option.className, { active: coursePreferredRuleForm.penalty === option.penalty }]"
             @click="coursePreferredRuleForm.penalty = option.penalty; coursePreferredRuleForm.forbidden = Boolean(option.forbidden)"
          >
            <strong>{{ option.label }}</strong>
            <small>{{ option.hint }}</small>
          </button>
        </div>
      </div>
      <div class="course-candidate-panel" data-guide-id="course-preferred-grid">
        <div v-if="coursePreferredAllPeriodsDisabled" class="course-preferred-warning">
          <span>该课次课长为 {{ activeCoursePreferredLesson()?.duration_slots ? unitsToMinutes(activeCoursePreferredLesson()?.duration_slots) + ' 分钟' : '未设置' }}，但所有节次的可用时长都不足以容纳，请调整课长或课表节次设置</span>
        </div>
        <div class="frequency-title course-candidate-heading">
          <div class="frequency-title-copy">
            <strong>周候选时间</strong>
            <span>点击格子加入候选；预设会按当前周频率和优先级批量选择</span>
          </div>
          <div class="course-candidate-heading-actions">
            <label class="course-candidate-scale-control">
              <span>表格缩放</span>
              <input
                v-model.number="courseCandidateScale"
                type="range"
                min="60"
                max="100"
                step="5"
                aria-label="候选时间表缩放比例"
                @input="markCourseCandidateScaleAdjusted"
              />
              <output>{{ courseCandidateScale }}%</output>
            </label>
            <button
              type="button"
              class="btn-secondary compact-toggle"
              :disabled="!selectedCoursePreferredRuleCount()"
              @click="clearActiveCoursePreferredRules"
            >
              清空候选
            </button>
          </div>
        </div>
        <div class="candidate-preset-row">
          <button
            v-for="preset in coursePreferredCandidatePresetOptions()"
            :key="preset.key"
            type="button"
            class="candidate-preset"
            @click="applyCoursePreferredCandidatePreset(preset.periodIndexes)"
          >
            <strong>{{ preset.label }}</strong>
            <small>{{ preset.hint }}</small>
          </button>
        </div>
        <div class="course-candidate-table-wrap">
          <table
            class="course-candidate-table"
            :style="{ '--course-candidate-scale': String(courseCandidateScale / 100) }"
          >
            <thead>
              <tr>
                <th>节次</th>
                <th v-for="day in coursePreferredPickerGrid" :key="day.index">{{ day.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in coursePreferredPickerRows" :key="row.period_index">
                <th
                  class="course-candidate-row-heading"
                  role="button"
                  tabindex="0"
                  title="点击全选或取消整行"
                  @click="toggleCoursePreferredGridRow(row.period_index)"
                  @keydown.enter.prevent="toggleCoursePreferredGridRow(row.period_index)"
                  @keydown.space.prevent="toggleCoursePreferredGridRow(row.period_index)"
                >
                  <strong>{{ row.label }}</strong>
                  <small>{{ row.time_range }}</small>
                </th>
                <td v-for="cell in row.cells" :key="`${cell.day.index}-${row.period_index}`">
                  <button
                    type="button"
                    class="candidate-cell"
                    :class="[cell.priority?.className || '', { active: Boolean(cell.rule), disabled: cell.disabled }]"
                    :disabled="cell.disabled"
                    @click="cell.period && toggleCoursePreferredGridCell(cell.period)"
                  >
                    <span>{{ coursePreferredCellButtonLabel(cell.rule) }}</span>
                    <small v-if="cell.show_time && cell.period">{{ cell.time_range }}</small>
                    <small v-if="cell.rule">{{ bitsToWeekLabel(cell.rule.week_bits) }}</small>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="sheet-scroll-spacer" aria-hidden="true"></div>
    </div>
    <div class="sheet-footer-actions">
      <button type="button" class="btn-secondary" @click="closeCoursePreferredPicker">取消</button>
      <button type="button" data-guide-id="course-preferred-save" :disabled="coursePreferredAllPeriodsDisabled" @click="saveCoursePreferredRule">
        保存
      </button>
    </div>
  </section>
</div></div></Teleport></template>
<style src="../web-course-editor/web-course-editor.css"></style>
