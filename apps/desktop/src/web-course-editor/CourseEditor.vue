<script setup lang="ts">
import {X} from 'lucide-vue-next';
import SearchableSelect from './SearchableSelect.vue';
import {useCourseEditor} from './useCourseEditor';
const props = defineProps<{context: Record<string, any>}>();
const emit = defineEmits<{close: []; saved: [revision: number]}>();
const {showGuide,activeGuideStepIndex,guideTargetRect,guideMissingTarget,teachingTaskForm,courseLessonDrafts,defaultRoomSearch,showDefaultRoomOptions,showLessonRoomOptions,loading,courseArrangementSaving,courseArrangementNotice,selectedTeachingTaskId,planningViewMode,selectedLessonImportTaskId,teacherSearch,teacherSearchInput,showTeacherOptions,showCoursePreferredPicker,coursePreferredPickerTitle,showLessonEditorSheet,courseWeekFrequencyCollapsed,coursePreferredRuleForm,coursePreferredPriorityOptions,termWeekOptions,activeGuideSteps,activeGuideStep,guideProgressLabel,guideHighlightStyle,guideCardStyle,startGuide,nextGuideStep,previousGuideStep,restartGuide,skipGuide,weekFrequencyPresets,applyCoursePreferredWeekPreset,closeCoursePreferredPicker,openLessonEditorSheet,closeLessonEditorSheet,toggleCoursePreferredRuleWeek,lessonEditorChanges,lessonEditorHasChanges,toggleCoursePreferredGridCell,toggleCoursePreferredGridRow,clearActiveCoursePreferredRules,clearCourseLessonPreferredTimes,coursePreferredCandidatePresetOptions,applyCoursePreferredCandidatePreset,openCoursePreferredPicker,saveCoursePreferredRule,selectedCourseNotScheduled,selectedSubject,editableCourseLessonDrafts,selectedPlanningHomeroom,selectedCoursePlanTasks,lessonImportTaskOptions,unitsToMinutes,durationText,selectedCoursePreferredSummary,coursePreferredPickerGrid,coursePreferredPickerRows,selectedCoursePreferredRuleCount,coursePreferredCellButtonLabel,coursePreferredPickerHint,coursePreferredPickerSummary,selectedSubjectDurationSlots,addCourseLesson,copyCourseLesson,deleteCourseLesson,activeCoursePreferredLesson,coursePreferredAllPeriodsDisabled,selectedDefaultRooms,filteredDefaultRoomOptions,selectedLessonRooms,filteredLessonRoomOptions,lessonRoomSearchValue,setLessonRoomSearch,hideDefaultRoomOptionsSoon,hideLessonRoomOptionsSoon,addDefaultRoom,removeDefaultRoom,addLessonRoom,removeLessonRoom,setUsesRooms,setLessonRoomMode,defaultRoomSelectionSummary,lessonRoomSelectionSummary,taskTeacherName,filteredTeacherOptions,syncTeacherSearchFromSelection,onTeacherSearchInput,selectTeacherOption,clearTeacherSelection,hideTeacherOptionsSoon,bitsToWeekLabel,taskImportLabel,isTeachingTaskActive,selectTeachingTask,startNewTeachingTask,importLessonSettingsFromSelectedTask,taskLessonCount,markSelectedCourseNotScheduled,resumeSelectedCourseScheduling,saveCourseArrangement,deleteCourseArrangement,recordName,subjectEditorOpen,subjectEditorPanel,courseCandidateScale,markCourseCandidateScaleAdjusted,closeSubjectEditor,handleSubjectEditorKeydown,error} = useCourseEditor(props,emit);
</script>
<template>
    <Teleport to="body"><div class="web-course-editor">
    <div v-if="subjectEditorOpen" class="subject-editor-mask">
    <aside
      ref="subjectEditorPanel"
      class="plan-detail-panel subject-editor-dialog"
      role="dialog" aria-modal="true" aria-label="科目配置"
      data-guide-id="planning-task-editor"
      @keydown="handleSubjectEditorKeydown"
    >
      <header class="subject-editor-dialog-header"><strong>{{ recordName(selectedPlanningHomeroom || {}) }} · 科目配置</strong><button type="button" class="subject-editor-close" aria-label="关闭科目配置" title="关闭" :disabled="courseArrangementSaving" @click="closeSubjectEditor"><X :size="20" /></button></header>
      <form @submit.prevent="saveCourseArrangement" class="detail-form">
        <div class="task-editor-heading">
          <div>
            <h3>{{ recordName(selectedSubject || {}) || '选择科目' }}</h3>
            <span>{{ recordName(selectedPlanningHomeroom || {}) || '未选择班级' }}</span>
          </div>
          <div class="task-editor-actions">
            <button
              v-if="selectedCourseNotScheduled"
              type="button"
              class="btn-secondary"
              :disabled="courseArrangementSaving"
              @click="resumeSelectedCourseScheduling"
            >
              恢复安排
            </button>
            <button
              v-else
              type="button"
              class="btn-secondary"
              :disabled="courseArrangementSaving"
              @click="markSelectedCourseNotScheduled"
            >
              不安排
            </button>
          </div>
        </div>
        <div v-if="selectedCourseNotScheduled" class="course-not-scheduled-callout">
          <strong>本班级不安排这门课程</strong>
          <span>不会生成授课任务和课次，也不会进入排课输入。需要恢复时点击右上方“恢复安排”。</span>
          <p v-if="courseArrangementNotice" class="course-save-notice">{{ courseArrangementNotice }}</p>
        </div>
        <template v-else>
        <div class="task-switcher">
          <div
            v-for="task in selectedCoursePlanTasks"
            :key="String(task.id)"
            class="task-switcher-row"
            :class="{ active: isTeachingTaskActive(task.id) }"
          >
            <button type="button" class="task-switcher-item" @click="selectTeachingTask(task)">
              <strong>{{ taskTeacherName(task) || '未指定教师' }}</strong>
              <span>{{ taskLessonCount(task.id) }} 个课次</span>
            </button>
            <button type="button" class="btn-delete" @click="deleteCourseArrangement(task)">删除</button>
          </div>
          <button
            type="button"
            class="task-switcher-item add"
            :class="{ active: !selectedTeachingTaskId }"
            @click="startNewTeachingTask"
          >
            <strong>{{ selectedTeachingTaskId ? '+ 新增授课老师' : '正在新增授课老师' }}</strong>
            <span>在下方选择教师并保存</span>
          </button>
        </div>
        <label>
          教师
          <div class="search-combobox">
            <div class="search-combobox-input">
              <input
                ref="teacherSearchInput"
                v-model="teacherSearch"
                placeholder="搜索教师姓名或分组标签"
                @focus="showTeacherOptions = true; syncTeacherSearchFromSelection()"
                @input="onTeacherSearchInput"
                @blur="hideTeacherOptionsSoon"
              />
              <button
                v-if="teachingTaskForm.primary_teacher_id"
                type="button"
                class="combo-clear"
                @mousedown.prevent
                @click="clearTeacherSelection"
              >
                清除
              </button>
            </div>
            <div v-if="showTeacherOptions" class="search-combobox-menu">
              <button
                type="button"
                class="combo-option"
                :class="{ active: !teachingTaskForm.primary_teacher_id }"
                @mousedown.prevent
                @click="clearTeacherSelection"
              >
                <strong>未指定教师</strong>
                <span>暂不分配教师</span>
              </button>
              <button
                v-for="teacher in filteredTeacherOptions"
                :key="String(teacher.id)"
                type="button"
                class="combo-option"
                :class="{ active: teachingTaskForm.primary_teacher_id === String(teacher.id) }"
                @mousedown.prevent
                @click="selectTeacherOption(teacher)"
              >
                <strong>{{ recordName(teacher) }}</strong>
                <span>{{ teacher.department || "未分组" }}</span>
              </button>
              <p v-if="!filteredTeacherOptions.length" class="combo-empty">没有匹配的教师</p>
            </div>
          </div>
          <span class="teacher-optional-note">允许保存为“未指定教师”，之后再补充分配，不影响课程计划保存。</span>
        </label>
        <div class="frequency-block">
          <div class="frequency-title">
            <strong>默认教室列表</strong>
            <span>{{ defaultRoomSelectionSummary() }}</span>
          </div>
          <div
            class="horizontal-choice-strip room-mode-strip segmented-strip"
            :class="{ 'is-second-active': !teachingTaskForm.uses_rooms }"
            aria-label="是否使用教室"
          >
            <button
              type="button"
              class="choice-pill"
              :class="{ active: teachingTaskForm.uses_rooms }"
              @click="setUsesRooms(true)"
            >
              使用教室
            </button>
            <button
              type="button"
              class="choice-pill"
              :class="{ active: !teachingTaskForm.uses_rooms }"
              @click="setUsesRooms(false)"
            >
              不使用教室
            </button>
          </div>
          <div class="room-search-block" :class="{ disabled: !teachingTaskForm.uses_rooms }">
            <div class="search-combobox">
              <div class="search-combobox-input">
                <input
                  v-model="defaultRoomSearch"
                  :disabled="!teachingTaskForm.uses_rooms"
                  placeholder="搜索并添加默认教室"
                  @focus="showDefaultRoomOptions = teachingTaskForm.uses_rooms"
                  @input="showDefaultRoomOptions = teachingTaskForm.uses_rooms"
                  @blur="hideDefaultRoomOptionsSoon"
                />
              </div>
              <div v-if="showDefaultRoomOptions && teachingTaskForm.uses_rooms" class="search-combobox-menu">
                <button
                  v-for="room in filteredDefaultRoomOptions"
                  :key="String(room.id)"
                  type="button"
                  class="combo-option"
                  @mousedown.prevent
                  @click="addDefaultRoom(room)"
                >
                  <strong>{{ recordName(room) }}</strong>
                  <span>{{ room.room_type_name || room.type || "未设置类型" }} · 容量 {{ room.capacity || "-" }}</span>
                </button>
                <p v-if="!filteredDefaultRoomOptions.length" class="combo-empty">没有可添加的教室</p>
              </div>
            </div>
            <div class="selected-room-tags">
              <span v-for="room in selectedDefaultRooms" :key="String(room.id)" class="selected-room-tag">
                {{ recordName(room) }}
                <button type="button" @click="removeDefaultRoom(room.id)" aria-label="移除默认教室">×</button>
              </span>
              <em v-if="teachingTaskForm.uses_rooms && !selectedDefaultRooms.length">未添加默认教室时，该课程默认不安排教室</em>
              <em v-if="!teachingTaskForm.uses_rooms">已关闭教室选择</em>
            </div>
          </div>
        </div>
        <div class="lesson-import-card" data-guide-id="planning-lesson-import">
          <div class="frequency-title">
            <strong>从其他课程导入课次设置</strong>
            <span>只导入课次、期望时间和教室设置，不覆盖当前教师。</span>
          </div>
          <div class="import-inline-row">
            <SearchableSelect v-model="selectedLessonImportTaskId" :disabled="!lessonImportTaskOptions.length">
              <option value="">选择已配置课程</option>
              <option
                v-for="task in lessonImportTaskOptions"
                :key="String(task.id)"
                :value="String(task.id)"
              >
                {{ taskImportLabel(task) }}
              </option>
            </SearchableSelect>
            <button
              type="button"
              class="btn-secondary"
              :disabled="!selectedLessonImportTaskId"
              @click="importLessonSettingsFromSelectedTask"
            >
              导入课次设置
            </button>
          </div>
        </div>
        <div class="lesson-summary-card" data-guide-id="planning-lesson-editor">
          <div class="frequency-title">
            <strong>课次</strong>
            <span>{{ courseLessonDrafts.length }} 个课次</span>
          </div>
          <p>课次的期望时间和课次教室在下方弹出栏中集中维护。</p>
          <button type="button" class="btn-secondary" @click="openLessonEditorSheet">
            编辑课次
          </button>
        </div>
        <p class="form-note">默认课长：{{ durationText(selectedSubjectDurationSlots()) }}。</p>
        <p v-if="courseArrangementNotice" class="course-save-notice">{{ courseArrangementNotice }}</p>
        <button class="plan-save-button" :disabled="loading || courseArrangementSaving">
          {{ courseArrangementSaving ? '保存中...' : (selectedTeachingTaskId ? '保存授课任务' : '新增授课任务') }}
        </button>
        </template>
      </form>
    </aside>
    </div>
    </div></Teleport>
<Teleport to="body"><div class="web-course-editor"><div v-if="showLessonEditorSheet" class="bottom-sheet-mask lesson-editor-sheet-mask">
  <section class="bottom-sheet lesson-editor-sheet" aria-label="编辑课次" data-guide-id="lesson-editor-sheet">
    <header class="bottom-sheet-header lesson-editor-sheet-header">
      <div>
        <span>{{ planningViewMode === 'subject' ? '科目默认课次' : '课次编辑' }}</span>
         <h3>{{ coursePreferredPickerTitle || selectedSubject?.name || '当前课程' }}</h3>
        <p class="sheet-context-hint">
          {{
            planningViewMode === 'subject'
              ? '设置该科目的默认课次、启用状态与期望时间。完成后返回课程计划，选择班级并应用。'
              : '在这里集中维护每个课次的期望时间、启用状态和课次教室，完成后可直接保存授课任务。'
          }}
        </p>
      </div>
      <div class="sheet-actions">
        <button v-if="planningViewMode !== 'subject'" type="button" class="btn-secondary guide-sheet-button" @click="startGuide('lesson_editor_sheet', true)">
          新手指导
        </button>
        <button type="button" data-guide-id="lesson-editor-add" @click="addCourseLesson">新增课次</button>
        <!-- <button
          v-if="planningViewMode !== 'subject'"
          type="button"
          :disabled="courseArrangementSaving"
          @click="saveCourseArrangement"
        >
          {{ courseArrangementSaving ? '保存中...' : '保存授课任务' }}
        </button> -->
        <!-- <button type="button" class="btn-secondary" @click="closeLessonEditorSheet">关闭</button> -->
      </div>
    </header>
    <div class="lesson-editor-sheet-body">
      <div class="lesson-editor" data-guide-id="lesson-editor-list">
          <section class="lesson-change-summary" :class="{ empty: !lessonEditorHasChanges }">
            <header>
              <div>
                <strong>本次课次变动</strong>
                <span>{{ lessonEditorHasChanges ? `${lessonEditorChanges.length} 项待保存` : '尚无修改' }}</span>
              </div>
              <small>下列修改只保存在当前草稿中，点击“保存授课任务”后才会写入。</small>
            </header>
            <ul v-if="lessonEditorHasChanges">
              <li v-for="change in lessonEditorChanges" :key="change.key" :class="`tone-${change.tone}`">
                <strong>{{ change.title }}</strong>
                <span>{{ change.detail }}</span>
              </li>
            </ul>
          </section>
          <div class="frequency-title">
            <strong>课次</strong>
            <span>{{ editableCourseLessonDrafts.length }} 个课次</span>
          </div>
          <div v-for="(lesson, index) in editableCourseLessonDrafts" :key="lesson.key" class="lesson-card">
            <div class="lesson-card-head">
              <input v-model="lesson.label" :placeholder="`第${index + 1}课次`" />
              <label class="inline-check">
                <input type="checkbox" v-model="lesson.enabled" />
                启用
              </label>
            </div>
            <div class="lesson-line">
              <strong>期望上课时间</strong>
              <span>{{ selectedCoursePreferredSummary(lesson) }}</span>
            </div>
            <div class="period-select-actions">
              <button type="button" class="btn-secondary" data-guide-id="lesson-editor-time" @click="openCoursePreferredPicker(lesson.key)">
                选择期望时间
              </button>
              <button
                type="button"
                class="btn-secondary"
                @click="clearCourseLessonPreferredTimes(lesson)"
                :disabled="!lesson.preferred_slots.length"
              >
                清空时间
              </button>
            </div>
            <template v-if="planningViewMode !== 'subject'">
              <div class="lesson-line">
                <strong>课次教室</strong>
                <span>{{ lessonRoomSelectionSummary(lesson) }}</span>
              </div>
              <div class="room-choice-block compact" data-guide-id="lesson-editor-room" :class="{ disabled: !teachingTaskForm.uses_rooms }">
              <div
                class="horizontal-choice-strip room-mode-strip segmented-strip"
                :class="{ 'is-second-active': lesson.room_mode === 'custom' }"
                aria-label="课次教室模式"
              >
                <button
                  type="button"
                  class="choice-pill"
                  :class="{ active: lesson.room_mode === 'default' }"
                  :disabled="!teachingTaskForm.uses_rooms"
                  @click="setLessonRoomMode(lesson, 'default')"
                >
                  默认教室
                </button>
                <button
                  type="button"
                  class="choice-pill"
                  :class="{ active: lesson.room_mode === 'custom' }"
                  :disabled="!teachingTaskForm.uses_rooms"
                  @click="setLessonRoomMode(lesson, 'custom')"
                >
                  自定义教室
                </button>
              </div>
              <div
                v-if="lesson.room_mode === 'custom'"
                class="room-search-block compact"
                :class="{ disabled: !teachingTaskForm.uses_rooms }"
              >
                <div class="search-combobox">
                  <div class="search-combobox-input">
                    <input
                      :value="lessonRoomSearchValue(lesson)"
                      :disabled="!teachingTaskForm.uses_rooms"
                      placeholder="搜索并添加课次教室"
                      @focus="showLessonRoomOptions = { ...showLessonRoomOptions, [lesson.key]: teachingTaskForm.uses_rooms }"
                      @input="setLessonRoomSearch(lesson, $event)"
                      @blur="hideLessonRoomOptionsSoon(lesson)"
                    />
                  </div>
                  <div v-if="showLessonRoomOptions[lesson.key] && teachingTaskForm.uses_rooms" class="search-combobox-menu">
                    <button
                      v-for="room in filteredLessonRoomOptions(lesson)"
                      :key="String(room.id)"
                      type="button"
                      class="combo-option"
                      @mousedown.prevent
                      @click="addLessonRoom(lesson, room)"
                    >
                      <strong>{{ recordName(room) }}</strong>
                      <span>{{ room.room_type_name || room.type || "未设置类型" }} · 容量 {{ room.capacity || "-" }}</span>
                    </button>
                    <p v-if="!filteredLessonRoomOptions(lesson).length" class="combo-empty">没有可添加的教室</p>
                  </div>
                </div>
                <div class="selected-room-tags">
                  <span v-for="room in selectedLessonRooms(lesson)" :key="String(room.id)" class="selected-room-tag">
                    {{ recordName(room) }}
                    <button type="button" @click="removeLessonRoom(lesson, room.id)" aria-label="移除课次教室">×</button>
                  </span>
                  <em v-if="teachingTaskForm.uses_rooms && !lesson.room_ids.length">尚未添加自定义教室</em>
                  <em v-if="!teachingTaskForm.uses_rooms">已关闭教室选择</em>
                </div>
              </div>
              </div>
            </template>
            <div class="row-actions lesson-actions">
              <button type="button" @click="copyCourseLesson(lesson.key)">复制课次</button>
              <button type="button" class="danger" @click="deleteCourseLesson(lesson.key)">删除课次</button>
            </div>
          </div>
        </div>
    </div>
    <div class="sheet-footer-actions">
      <button
        v-if="planningViewMode !== 'subject'"
        type="button"
        :disabled="courseArrangementSaving"
        @click="saveCourseArrangement"
      >
        {{ courseArrangementSaving ? '保存中...' : '保存授课任务' }}
      </button>
      <button type="button" class="btn-secondary" @click="closeLessonEditorSheet">
        {{ lessonEditorHasChanges ? '关闭并放弃修改' : '关闭' }}
      </button>
    </div>
  </section>
</div>

<div v-if="showCoursePreferredPicker" class="bottom-sheet-mask course-preferred-sheet-mask">
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
</div>
<div v-if="showGuide" class="guide-mask" @click.self="skipGuide">
  <div v-if="guideTargetRect" class="guide-highlight" :style="guideHighlightStyle"></div>
  <article class="guide-card" :class="{ fallback: guideMissingTarget }" :style="guideCardStyle">
    <span>{{ guideProgressLabel }}</span>
    <h3>{{ activeGuideStep?.title || "新手指引" }}</h3>
    <p>
      {{
        guideMissingTarget
          ? activeGuideStep?.fallbackBody || activeGuideStep?.body || "当前页面还没有这个组件，请先完成前面的配置。"
          : activeGuideStep?.body
      }}
    </p>
    <button type="button" class="btn-link" @click="restartGuide">重新开始</button>
  </article>
  <div class="guide-controls">
    <button type="button" class="btn-secondary" @click="previousGuideStep" :disabled="activeGuideStepIndex === 0">
      上一步
    </button>
    <button type="button" class="btn-secondary" @click="skipGuide">跳过</button>
    <button type="button" @click="nextGuideStep">
      {{ activeGuideStepIndex >= activeGuideSteps.length - 1 ? "完成" : "下一步" }}
    </button>
  </div>
</div>
</div></Teleport>
</template>
<style src="./web-course-editor.css"></style>
