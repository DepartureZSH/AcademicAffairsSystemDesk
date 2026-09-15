<script setup lang="ts">
import {computed, inject, watch, onBeforeUnmount} from 'vue';
import { APP_CONTEXT_KEY } from './appContext';
import CoursePeriodInspector from './CoursePeriodInspector.vue';
import TemplateMarketplacePreviewTable from './TemplateMarketplacePreviewTable.vue';
import TemplatePlanningMode from './TemplatePlanningMode.vue';
import SearchableSelect from './SearchableSelect.vue';
const props = defineProps<{embedded?:boolean}>();
const {activeSection,addPreviewBlankColumn,addPreviewBlankRow,addPreviewHeaderRow,addPreviewRow,applySelectedBlankColumnCellMerge,applySelectedBlankRowCellMerge,applySelectedHeaderCellMerge,blankRowRenderedCells,canDeleteCurrentRow,canMovePreviewBlankColumn,canMovePreviewBlankRow,canMovePreviewHeaderRow,cancelNewTimetableTemplate,courseCellExportBottomField,courseCellExportLayout,courseCellExportTopField,courseCellSampleLines,courseCellTemplatePreviewLayout,courseCellTemplatePreviewLines,createNewTimetableTemplate,deletePreviewBlankColumn,deletePreviewBlankRow,deletePreviewHeaderRow,deleteSelectedPreviewRow,deleteTimetableTemplate,exportTimetableTemplateExcel,isPreviewBlankColumnCellSelected,isPreviewBlankColumnSelected,isPreviewBlankRowCellSelected,isPreviewBlankRowSelected,isPreviewCellSelected,isPreviewHeaderCellSelected,isTemplateWeekdayEnabled,allClassesTemplateVariant,fullTablePreviewColumnCount,fullTablePreviewDayGroups,fullTablePreviewPeriods,hasTimetableTemplateEditor,irregularPreviewColumnCount,irregularPreviewDayGroups,irregularPreviewHomerooms,loading,movePreviewBlankColumn,movePreviewBlankRow,movePreviewHeaderRow,newTemplateConfirmDescription,newTemplateConfirmStep,newTemplateConfirmTitle,previewBlankColumnCell,previewBodyColumnCount,previewHeaderCellText,previewHeaderRowRenderedCells,previewHeaderRows,previewPeriodMode,saveTimetableTemplate,schoolData,schoolDataSummary,selectNumberValue,selectPreviewBlankColumn,selectPreviewBlankColumnCell,selectPreviewBlankRow,selectPreviewBlankRowCell,selectPreviewCell,selectPreviewHeaderCell,selectTimetableTemplate,selectedPreviewBlankColumn,selectedPreviewBlankColumnCell,selectedPreviewBlankColumnCellMaxColspan,selectedPreviewBlankColumnCellMaxRowspan,selectedPreviewBlankRow,selectedPreviewBlankRowCell,selectedPreviewBlankRowCellMaxColspan,selectedPreviewBlankRowCellMaxRowspan,selectedPreviewCell,selectedPreviewHeaderCell,selectedPreviewHeaderCellMaxColspan,selectedPreviewHeaderCellMaxRowspan,selectedPreviewPeriod,selectedTemplateId,setTemplateWeekdayEnabled,showNewTimetableTemplateConfirm,showTimetableTimeAxis,splitSelectedBlankColumnCell,splitSelectedBlankRowCell,splitSelectedHeaderCell,specialTimetableTemplatePresetsLoading,templateDisplayConfig,termForm,timetable,timetablePresetLibraryLoading,timetablePreviewColumns,timetablePreviewDays,timetablePreviewRowFlow,timetableTemplateForm,timetableTemplateKind,timetableTemplateLayoutKind,templateCreatePlanningMode,templateMarketplaceSearch,templateMarketplaceFilters,filteredTemplateMarketplaceItems,selectedTemplateMarketplaceKey,previewTemplateMarketplaceItem,chooseTemplatePlanningMode,backNewTemplateStep,selectTemplateMarketplaceItem,openTemplateMarketplacePreview,closeTemplateMarketplacePreview,continueTemplateMarketplace,confirmNewTemplateFromMarketplace,updateActiveTerm,error,localNotice} = inject(APP_CONTEXT_KEY)!;
const selectedTemplateIsPersistedDefault = computed(() => schoolData.value.weekly_timetable_templates.some(t => String(t.id) === selectedTemplateId.value && Boolean(t.is_default)));
let timer: ReturnType<typeof setTimeout> | undefined;
watch(() => termForm.value.week_count, value => { if(loading.value || value === Number(schoolData.value.active_term?.week_count) || value < 1 || value > 60) return; clearTimeout(timer); timer = setTimeout(updateActiveTerm, 500); });
onBeforeUnmount(() => clearTimeout(timer));
</script>
<template>
<section v-show="props.embedded || activeSection === 'timetable'" class="master-data-panel" data-guide-id="timetable-page">
  <header v-if="!props.embedded" class="section-heading">
    <div>
      <h2 title="设置学期范围、课次规划和候选课表导出样式">课表设置</h2>
    </div>
    <div class="master-summary">
      <div class="term-summary-editor" data-guide-id="timetable-term">
        <label title="设置当前项目的总周数">
          <span class="term-summary-label">学期周数</span>
          <input
            v-model.number="termForm.week_count"
            aria-label="学期周数"
            type="number"
            min="1"
            max="60"
            :disabled="loading"
          />
          <span class="term-summary-unit">周</span>
        </label>
      </div>
      <span>每周 7 天</span>
      <span>模板 {{ schoolDataSummary.templates }}</span>
      <span>节次 {{ schoolDataSummary.periods }}</span>
    </div>
  </header>

  <p v-if="localNotice && !error" class="muted" role="status">{{ localNotice }}</p>
  <p v-if="error" class="error local-editor-notice" role="alert">{{ error }}</p>
  <div class="timetable-settings-layout">
    <div class="template-editor settings-card" data-guide-id="timetable-template">
      <div class="settings-editor-header">
        <div>
          <h3 title="课次规划会用于课程计划、排课运行和课表导出">周课程表模板</h3>
        </div>
        <div class="template-actions">
          <button v-if="!props.embedded" type="button" class="btn-secondary" @click="createNewTimetableTemplate">新建</button>
          <button
            v-if="hasTimetableTemplateEditor"
            type="button"
            class="btn-secondary"
            @click="exportTimetableTemplateExcel"
          >导出Excel预览</button>
          <button
            v-if="hasTimetableTemplateEditor && !props.embedded"
            type="button"
            class="btn-secondary danger"
            :disabled="loading || !selectedTemplateId"
            @click="deleteTimetableTemplate"
          >删除当前模板</button>
          <button
            v-if="hasTimetableTemplateEditor"
            type="button"
            :disabled="loading"
            @click="saveTimetableTemplate"
          >保存</button>
        </div>
      </div>

      <div v-if="!hasTimetableTemplateEditor" class="template-empty-state">
        <strong>暂无课表模板</strong>
      </div>

      <div v-if="!props.embedded && schoolData.weekly_timetable_templates.length" class="template-project-list">
        <div class="template-project-list-heading">
          <strong title="选择模板后，下方编辑器会切换到对应的课次规划和导出样式">本项目模板</strong>
          <span class="template-project-count">{{ schoolData.weekly_timetable_templates.length }} 个模板</span>
        </div>
        <div class="project-template-stack" aria-label="本项目模板">
          <button
            v-for="template in schoolData.weekly_timetable_templates"
            :key="String(template.id)"
            type="button"
            class="project-template-card"
            :class="{
              active: String(template.id) === selectedTemplateId,
              'is-default': template.is_default,
              'is-special': !template.is_default && template.template_kind === 'special'
            }"
            :aria-current="String(template.id) === selectedTemplateId ? 'true' : undefined"
            :title="template.is_default
              ? '项目基准课表，未单独指定导出模板时自动使用'
              : (template.template_kind === 'special'
                ? '专用导出布局'
                : (template.periods_locked
                  ? '复用默认模板的课次规划，默认课次变动时会同步更新'
                  : '使用独立课次规划，可单独调整课次时间和导出样式'))"
            @click="selectTimetableTemplate(String(template.id))"
          >
            <span class="project-template-marker" aria-hidden="true">
              {{ template.is_default ? "默" : (template.template_kind === "special" ? "特" : "模") }}
            </span>
            <span class="project-template-copy">
              <span class="project-template-title-row">
                <strong>{{ template.name }}</strong>
                <span class="project-template-badges">
                  <small v-if="template.is_default">项目默认模板</small>
                  <small v-else-if="template.template_kind === 'special'">特殊模板</small>
                  <small v-else>普通模板</small>
                  <small v-if="!template.is_default && template.template_kind === 'special'">全课表导出</small>
                  <small v-else-if="!template.is_default && template.periods_locked">复用默认课次</small>
                  <small v-else-if="!template.is_default">独立课次</small>
                </span>
              </span>
            </span>
            <span class="project-template-open-state">
              {{ String(template.id) === selectedTemplateId ? "当前编辑" : "打开编辑" }}
            </span>
          </button>
        </div>
      </div>

      <form
        v-if="hasTimetableTemplateEditor"
        class="template-form template-details-form"
        @submit.prevent="saveTimetableTemplate"
      >
        <label>
          模板名称
          <input v-model="timetableTemplateForm.name" placeholder="默认周课程表" />
        </label>
        <div class="template-form-options single-option template-default-option">
          <div
            v-if="selectedTemplateIsPersistedDefault"
            class="template-default-status"
            title="当前模板是本项目的默认模板"
          >
            <span aria-hidden="true">✓</span>
            <strong>当前默认模板</strong>
          </div>
          <label
            v-else
            class="checkbox-row"
            :class="{ disabled: timetableTemplateKind === 'special' }"
            :title="timetableTemplateKind === 'special'
              ? '特殊模板不能设为默认模板'
              : '保存后，本项目原默认模板会自动失效'"
          >
            <input
              v-model="timetableTemplateForm.is_default"
              type="checkbox"
              :disabled="timetableTemplateKind === 'special'"
            />
            <span>
              {{ timetableTemplateKind === 'special' ? '特殊模板不可设默认' : '设为默认模板' }}
            </span>
          </label>
        </div>
      </form>

      <div
        v-if="showNewTimetableTemplateConfirm"
        class="template-time-preset-mask"
      >
        <section
          class="template-new-confirm-modal"
          :class="{ 'template-marketplace-modal': newTemplateConfirmStep === 'marketplace' }"
          role="dialog"
          aria-modal="true"
          aria-labelledby="template-new-confirm-title"
        >
          <header class="template-create-header">
            <div>
              <h3 id="template-new-confirm-title">{{ newTemplateConfirmTitle }}</h3>
              <p>{{ newTemplateConfirmDescription }}</p>
            </div>
            <ol class="template-create-steps" aria-label="新建模板步骤">
              <li :class="{ active: newTemplateConfirmStep === 'planning', complete: newTemplateConfirmStep !== 'planning' }"><span>1</span><strong>规划方式</strong></li>
              <li :class="{ active: newTemplateConfirmStep === 'marketplace', complete: newTemplateConfirmStep === 'details' }"><span>2</span><strong>模板库</strong></li>
              <li :class="{ active: newTemplateConfirmStep === 'details' }"><span>3</span><strong>模板信息</strong></li>
            </ol>
          </header>

          <TemplatePlanningMode v-if="newTemplateConfirmStep === 'planning'" :model-value="templateCreatePlanningMode" :can-reuse="Boolean(schoolData.default_weekly_timetable_template)" @update:model-value="chooseTemplatePlanningMode" />

          <div v-else-if="newTemplateConfirmStep === 'marketplace'" class="template-marketplace-body">
            <div class="template-marketplace-search">
              <input v-model="templateMarketplaceSearch" type="search" placeholder="搜索模板名称或描述" aria-label="搜索模板" />

              <span>{{ filteredTemplateMarketplaceItems.length }} 个结果</span>
            </div>
            <div class="template-marketplace-filters">
              <fieldset>
                <legend>本机模板</legend>
                <div class="segmented-control">
                  <button v-for="option in [{ value: 'all', label: '全部' }, { value: 'yes', label: '是' }, { value: 'no', label: '否' }]" :key="option.value" type="button" :class="{ active: templateMarketplaceFilters.owned === option.value }" @click="templateMarketplaceFilters.owned = option.value">{{ option.label }}</button>
                </div>
              </fieldset>
              <fieldset>
                <legend>横轴星期、纵轴时间</legend>
                <div class="segmented-control">
                  <button v-for="option in [{ value: 'all', label: '全部' }, { value: 'yes', label: '是' }, { value: 'no', label: '否' }]" :key="option.value" type="button" :class="{ active: templateMarketplaceFilters.regular === option.value }" @click="templateMarketplaceFilters.regular = option.value">{{ option.label }}</button>
                </div>
              </fieldset>
              <fieldset>
                <legend>每天课次时间固定</legend>
                <div class="segmented-control">
                  <button v-for="option in [{ value: 'all', label: '全部' }, { value: 'yes', label: '是' }, { value: 'no', label: '否' }]" :key="option.value" type="button" :class="{ active: templateMarketplaceFilters.fixed === option.value }" @click="templateMarketplaceFilters.fixed = option.value">{{ option.label }}</button>
                </div>
              </fieldset>
            </div>
            <p v-if="templateCreatePlanningMode === 'reuse'" class="template-marketplace-compatibility">
              已按默认模板的{{ templateDisplayConfig(schoolData.default_weekly_timetable_template).time_mode === 'variable' ? '不固定时段' : '固定时段' }}规则筛选兼容模板。
            </p>
            <p v-if="timetablePresetLibraryLoading || specialTimetableTemplatePresetsLoading" class="empty">正在加载模板库...</p>
            <div v-else-if="filteredTemplateMarketplaceItems.length" class="template-marketplace-grid">
              <article v-for="item in filteredTemplateMarketplaceItems" :key="item.key" :class="{ selected: selectedTemplateMarketplaceKey === item.key }">
                <button type="button" class="template-marketplace-select" @click="selectTemplateMarketplaceItem(item.key)">
                  <span class="template-marketplace-thumbnail" :class="{ special: item.layoutKind !== 'weekly', variable: item.timeMode === 'variable' }" aria-hidden="true"><i v-for="index in 20" :key="index"></i></span>
                  <span class="template-marketplace-card-copy">
                    <strong>{{ item.name }}</strong>
                    <small>{{ item.description }}</small>
                    <span><b>{{ item.isOwned ? '本机模板' : item.organizationName }}</b><b>{{ item.layoutKind === 'weekly' ? '普通模板' : '特殊模板' }}</b><b>{{ item.timeMode === 'fixed' ? '固定时段' : '不固定时段' }}</b></span>
                  </span>
                </button>
                <button type="button" class="btn-secondary template-marketplace-preview-button" @click="openTemplateMarketplacePreview(item.key)">示例预览</button>
              </article>
            </div>
            <p v-else class="empty">没有符合当前条件的模板。</p>
          </div>

          <form v-else class="template-create-details" @submit.prevent="confirmNewTemplateFromMarketplace">
            <label>模板名称<input v-model="timetableTemplateForm.name" maxlength="80" required placeholder="请输入模板名称" /></label>
            <div class="template-create-summary"><span>课次规划</span><strong>{{ templateCreatePlanningMode === 'reuse' ? '复用默认安排' : '独立课次安排' }}</strong></div>
          </form>

          <footer>
            <button v-if="newTemplateConfirmStep === 'planning'" type="button" @click="chooseTemplatePlanningMode(templateCreatePlanningMode)">下一步</button>
            <button
              v-if="newTemplateConfirmStep !== 'planning'"
              type="button"
              class="btn-secondary"
              @click="backNewTemplateStep"
            >返回</button>
            <button type="button" class="btn-secondary" :disabled="loading" @click="cancelNewTimetableTemplate">
              取消
            </button>
            <button v-if="newTemplateConfirmStep === 'marketplace'" type="button" :disabled="!selectedTemplateMarketplaceKey" @click="continueTemplateMarketplace">下一步</button>
            <button v-if="newTemplateConfirmStep === 'details'" type="button" :disabled="loading || !timetableTemplateForm.name.trim()" @click="confirmNewTemplateFromMarketplace">确认并创建</button>
          </footer>
        </section>

        <div v-if="previewTemplateMarketplaceItem" class="template-preview-mask">
          <section class="template-marketplace-preview-modal" role="dialog" aria-modal="true" aria-label="模板示例预览">
            <header><div><span>示例预览</span><h3>{{ previewTemplateMarketplaceItem.name }}</h3></div><button type="button" class="btn-secondary" @click="closeTemplateMarketplacePreview">关闭</button></header>
            <div class="template-marketplace-preview-table-wrap">
              <TemplateMarketplacePreviewTable :item="previewTemplateMarketplaceItem" />
            </div>
          </section>
        </div>
      </div>

      <div v-if="hasTimetableTemplateEditor" class="template-inline-preview">
        <div class="inline-preview-toolbar">
          <div>
            <strong title="直接点击表格中的星期、课次或自定义单元格进行编辑">周课程表编辑</strong>
          </div>
          <div class="sheet-actions">
            <button class="btn-secondary" @click="addPreviewHeaderRow">新建自定义表头</button>
            <button class="btn-secondary" @click="addPreviewRow">新建课程行</button>
            <button class="btn-secondary" @click="addPreviewBlankRow">新建自定义行</button>
            <button class="btn-secondary" @click="addPreviewBlankColumn">新建自定义列</button>
            <button class="btn-delete" @click="deleteSelectedPreviewRow" :disabled="!canDeleteCurrentRow">删除当前行</button>
          </div>
        </div>

        <div class="weekday-visibility-strip" data-guide-id="timetable-weekdays" aria-label="选择周课程表显示的星期">
          <div>
            <strong title="隐藏的星期不会出现在课表和导出文件中">显示星期</strong>
          </div>
          <div class="weekday-toggle-list">
            <button
              v-for="day in timetablePreviewDays"
              :key="day.index"
              type="button"
              class="weekday-toggle-chip"
              :class="{ active: isTemplateWeekdayEnabled(day.index + 1) }"
              @click="setTemplateWeekdayEnabled(day.index + 1, !isTemplateWeekdayEnabled(day.index + 1))"
            >
              <span>{{ day.label }}</span>
              <small>{{ isTemplateWeekdayEnabled(day.index + 1) ? '已显示' : '已隐藏' }}</small>
            </button>
          </div>
        </div>

        <div class="template-preview-workbench" data-guide-id="timetable-preview">
          <div class="time-axis-restore-bar">
            <span>{{ showTimetableTimeAxis ? '时间轴已显示' : '时间轴已隐藏' }}</span>
            <button type="button" class="btn-secondary" @click="showTimetableTimeAxis = !showTimetableTimeAxis">
              {{ showTimetableTimeAxis ? '隐藏时间轴' : '显示时间轴' }}
            </button>
          </div>
          <div class="course-cell-style-card">
            <div class="course-cell-style-copy">
              <strong title="设置候选课表导出时一个课次在单元格中的显示方式">课程单元格导出样式</strong>
            </div>
            <div class="course-cell-style-controls">
              <label>
                呈现方式
                <SearchableSelect v-model="courseCellExportLayout">
                  <option value="single_line">一个单元格仅一行</option>
                  <option value="two_line">一个单元格内两行</option>
                  <option value="split_rows">拆成上下两行</option>
                </SearchableSelect>
              </label>
              <label>
                第一行
                <SearchableSelect v-model="courseCellExportTopField">
                  <option value="subject">课程名</option>
                  <option value="teacher">教师名</option>
                  <option value="time">时间</option>
                  <option value="room">教室</option>
                  <option value="homeroom">班级</option>
                </SearchableSelect>
              </label>
              <label>
                第二行
                <SearchableSelect v-model="courseCellExportBottomField" :disabled="courseCellExportLayout === 'single_line'">
                  <option value="teacher">教师名</option>
                  <option value="subject">课程名</option>
                  <option value="time">时间</option>
                  <option value="room">教室</option>
                  <option value="homeroom">班级</option>
                </SearchableSelect>
              </label>
            </div>
            <div class="course-cell-preview" :class="{ split: courseCellExportLayout === 'split_rows' }">
              <div v-for="line in courseCellSampleLines" :key="line">{{ line }}</div>
            </div>
          </div>
          <div class="preview-table-scroll">
            <table v-if="timetableTemplateLayoutKind === 'weekly'" class="weekly-preview-table">
              <thead>
                <tr v-for="headerRow in previewHeaderRows" :key="headerRow.id" class="preview-custom-header-row">
                  <th
                    v-for="cell in previewHeaderRowRenderedCells(headerRow)"
                    :key="`${headerRow.id}-${cell.columnKey}`"
                    :colspan="cell.colspan"
                    :rowspan="cell.rowspan"
                    class="preview-custom-heading"
                    :class="{
                      selected: isPreviewHeaderCellSelected(headerRow, cell.columnKey),
                      left: cell.cell.align === 'left',
                      inactive: cell.cell.active === false,
                    }"
                    @click="selectPreviewHeaderCell(headerRow, cell.columnKey)"
                  >
                    {{ cell.label }}
                  </th>
                </tr>
                <tr>
                  <th v-if="showTimetableTimeAxis" class="preview-time-heading">时间</th>
                  <template v-for="column in timetablePreviewColumns" :key="column.id">
                    <th v-if="column.kind === 'weekday'">
                      <div class="preview-column-header">
                        <span>{{ column.day.label }}</span>
                      </div>
                    </th>
                    <th
                      v-else
                      :colspan="Math.max(Number(column.column.colspan || 1), 1)"
                      class="blank-column-heading"
                      :class="{ selected: isPreviewBlankColumnSelected(column.column), left: column.column.align === 'left' }"
                      @click="selectPreviewBlankColumn(column.column)"
                    >
                      {{ column.column.label || '' }}
                    </th>
                  </template>
                </tr>
              </thead>
              <tbody>
                <template v-for="flowRow in timetablePreviewRowFlow" :key="flowRow.id">
                  <tr v-if="flowRow.kind === 'period'" class="timeline-interval-row">
                    <th v-if="showTimetableTimeAxis" class="period-row-heading preview-time-axis">
                      <span class="time-axis-start">{{ flowRow.row.timeLabel }}</span>
                      <span
                        v-if="flowRow.row.terminalTimeLabel"
                        class="time-axis-end"
                      >
                        {{ flowRow.row.terminalTimeLabel }}
                      </span>
                    </th>
                    <td
                      v-for="cell in flowRow.row.renderedCells"
                      :key="cell.kind === 'period' ? `${flowRow.id}-${cell.dayIndex}` : `${flowRow.id}-${cell.column.id}`"
                      :colspan="cell.colspan"
                      :rowspan="cell.rowspan"
                      :class="{
                        inactive: cell.kind === 'period'
                          ? !cell.period || previewPeriodMode(cell.period) === 'disabled'
                          : previewBlankColumnCell(cell.column, cell.rowKey).active === false,
                        'custom-content-cell': cell.kind === 'period' && previewPeriodMode(cell.period) === 'custom',
                        'empty-time-slot': cell.kind === 'period' && !cell.period,
                        left: cell.kind === 'period'
                          ? cell.period?.align === 'left'
                          : previewBlankColumnCell(cell.column, cell.rowKey).align === 'left',
                        selected: cell.kind === 'period'
                          ? isPreviewCellSelected(Number(cell.period?.period_index), cell.dayIndex)
                          : isPreviewBlankColumnCellSelected(cell.column, cell.rowKey),
                        'blank-column-cell': cell.kind === 'blank',
                        'period-time-block': cell.kind === 'period' && Boolean(cell.period),
                      }"
                      @click="cell.kind === 'period'
                        ? (cell.period
                          ? selectPreviewCell(Number(cell.period.period_index), cell.dayIndex, cell.period)
                          : undefined)
                        : selectPreviewBlankColumnCell(cell.column, cell.rowKey)"
                    >
                      <template v-if="cell.kind === 'period' && cell.period">
                        <div
                          class="template-course-cell-preview"
                          :class="{ split: courseCellTemplatePreviewLayout(cell.period) === 'split_rows' }"
                        >
                          <div
                            v-for="(line, lineIndex) in courseCellTemplatePreviewLines(cell.period)"
                            :key="lineIndex"
                            class="template-course-cell-line"
                          >
                            {{ line }}
                          </div>
                        </div>
                      </template>
                      <template v-else-if="cell.kind === 'blank'">
                        {{ previewBlankColumnCell(cell.column, cell.rowKey).label }}
                      </template>
                      <span v-else class="time-slot-placeholder" aria-hidden="true"></span>
                    </td>
                  </tr>
                  <tr v-else class="blank-preview-row">
                    <td
                      v-if="showTimetableTimeAxis"
                      class="preview-time-axis blank-row-time"
                      :class="{ selected: isPreviewBlankRowSelected(flowRow.row) }"
                      @click="selectPreviewBlankRow(flowRow.row)"
                    >
                      <span>{{ flowRow.row.label || '' }}</span>
                    </td>
                    <td
                      v-for="cell in blankRowRenderedCells(flowRow.row)"
                      :key="`${flowRow.row.id}-${cell.columnKey}`"
                      :colspan="cell.colspan"
                      :rowspan="cell.rowspan"
                      class="blank-row-cell"
                      :class="{
                        selected: isPreviewBlankRowCellSelected(flowRow.row, cell.columnKey),
                        left: cell.align === 'left',
                        inactive: cell.active === false,
                      }"
                      @click="selectPreviewBlankRowCell(flowRow.row, cell.columnKey)"
                    >
                      {{ cell.label }}
                    </td>
                  </tr>
                </template>
                <tr v-if="timetablePreviewRowFlow.length === 0">
                  <td :colspan="previewBodyColumnCount + (showTimetableTimeAxis ? 1 : 0)" class="empty">暂无时段</td>
                </tr>
              </tbody>
            </table>
            <table v-else-if="allClassesTemplateVariant === 'homeroom_rows'" class="weekly-preview-table irregular-template-preview-table">
              <thead>
                <tr v-for="headerRow in previewHeaderRows" :key="headerRow.id" class="preview-custom-header-row">
                  <th
                    v-for="cell in previewHeaderRowRenderedCells(headerRow)"
                    :key="`${headerRow.id}-${cell.columnKey}`"
                    :colspan="Math.min(cell.colspan, irregularPreviewColumnCount + 1)"
                    :rowspan="cell.rowspan"
                    class="preview-custom-heading"
                    :class="{ selected: isPreviewHeaderCellSelected(headerRow, cell.columnKey), left: cell.cell.align === 'left' }"
                    @click="selectPreviewHeaderCell(headerRow, cell.columnKey)"
                  >{{ cell.label }}</th>
                </tr>
                <tr>
                  <th rowspan="2" class="irregular-class-heading">班级</th>
                  <th v-for="group in irregularPreviewDayGroups" :key="group.weekday" :colspan="group.periods.length">{{ group.label }}</th>
                </tr>
                <tr>
                  <template v-for="group in irregularPreviewDayGroups" :key="`periods-${group.weekday}`">
                    <th v-for="period in group.periods" :key="`${group.weekday}-${period.period_index}`">第{{ period.period_index }}节</th>
                  </template>
                </tr>
              </thead>
              <tbody>
                <tr v-for="homeroom in irregularPreviewHomerooms" :key="homeroom.id">
                  <th class="irregular-homeroom-heading">{{ homeroom.name }}</th>
                  <td v-for="index in irregularPreviewColumnCount" :key="`${homeroom.id}-${index}`" class="irregular-subject-cell">
                    <span v-if="homeroom.id === 'sample-homeroom' && index === 1">课程名</span>
                  </td>
                </tr>
              </tbody>
            </table>
            <table v-else class="weekly-preview-table full-school-template-table">
              <thead>
                <tr v-for="headerRow in previewHeaderRows" :key="headerRow.id" class="preview-custom-header-row">
                  <th
                    v-for="cell in previewHeaderRowRenderedCells(headerRow)"
                    :key="`${headerRow.id}-${cell.columnKey}`"
                    :colspan="Math.min(cell.colspan, fullTablePreviewColumnCount)"
                    :rowspan="cell.rowspan"
                    class="preview-custom-heading"
                    :class="{ selected: isPreviewHeaderCellSelected(headerRow, cell.columnKey), left: cell.cell.align === 'left' }"
                    @click="selectPreviewHeaderCell(headerRow, cell.columnKey)"
                  >{{ cell.label }}</th>
                </tr>
                <tr>
                  <th rowspan="3">时段</th>
                  <th rowspan="3">时间</th>
                  <th rowspan="3">节次</th>
                  <th v-for="group in fullTablePreviewDayGroups" :key="group.weekday" :colspan="group.homerooms.length">{{ group.label }}</th>
                </tr>
                <tr>
                  <template v-for="group in fullTablePreviewDayGroups" :key="`preview-grades-${group.weekday}`">
                    <th v-for="grade in group.gradeGroups" :key="`${group.weekday}-${grade.label}`" :colspan="grade.homerooms.length">{{ grade.label }}</th>
                  </template>
                </tr>
                <tr>
                  <template v-for="group in fullTablePreviewDayGroups" :key="`preview-classes-${group.weekday}`">
                    <th v-for="homeroom in group.homerooms" :key="`${group.weekday}-${homeroom.id}`">{{ homeroom.classLabel }}</th>
                  </template>
                </tr>
              </thead>
              <tbody>
                <template v-for="period in fullTablePreviewPeriods" :key="period.period_index">
                  <tr>
                    <th v-if="period.segmentStart" :rowspan="period.segmentRowspan" class="full-school-segment-cell">{{ period.segment }}</th>
                    <th rowspan="2" class="full-school-time-cell">{{ period.start_time }}-{{ period.end_time }}</th>
                    <th rowspan="2" class="full-school-period-cell">{{ period.label || `第${period.period_index}节` }}</th>
                    <template v-for="group in fullTablePreviewDayGroups" :key="`preview-subjects-${period.period_index}-${group.weekday}`">
                      <td v-for="homeroom in group.homerooms" :key="`${period.period_index}-${group.weekday}-${homeroom.id}-subject`" class="full-school-course-cell subject-line">
                        {{ period.period_index === 1 ? '课程名' : '' }}
                      </td>
                    </template>
                  </tr>
                  <tr>
                    <template v-for="group in fullTablePreviewDayGroups" :key="`preview-teachers-${period.period_index}-${group.weekday}`">
                      <td v-for="homeroom in group.homerooms" :key="`${period.period_index}-${group.weekday}-${homeroom.id}-teacher`" class="full-school-course-cell teacher-line">
                        {{ period.period_index === 1 ? '教师名' : '' }}
                      </td>
                    </template>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>

          <aside class="preview-inspector inline-inspector">
            <template v-if="selectedPreviewHeaderCell">
              <h4>编辑表头单元格</h4>
              <div class="inspector-actions">
                <button class="btn-secondary" @click="movePreviewHeaderRow(selectedPreviewHeaderCell.row.id, -1)" :disabled="!canMovePreviewHeaderRow(selectedPreviewHeaderCell.row.id, -1)">上移表头</button>
                <button class="btn-secondary" @click="movePreviewHeaderRow(selectedPreviewHeaderCell.row.id, 1)" :disabled="!canMovePreviewHeaderRow(selectedPreviewHeaderCell.row.id, 1)">下移表头</button>
              </div>
              <label>
                内容来源
                <SearchableSelect v-model="selectedPreviewHeaderCell.cell.binding">
                  <option value="template_name">模板名称</option>
                  <option value="school_name">学校名</option>
                  <option value="project_name">项目名</option>
                  <option value="owner_name">归属主体名称</option>
                  <option value="custom">自定义内容</option>
                </SearchableSelect>
              </label>
              <label v-if="selectedPreviewHeaderCell.cell.binding === 'custom'">
                表头内容
                <input v-model="selectedPreviewHeaderCell.cell.label" placeholder="输入表头文字" />
              </label>
              <label v-else>
                当前内容
                <div class="fixed-value">{{ previewHeaderCellText(selectedPreviewHeaderCell.cell) }}</div>
              </label>
              <label>
                对齐
                <SearchableSelect v-model="selectedPreviewHeaderCell.cell.align">
                  <option value="center">居中</option>
                  <option value="left">左对齐</option>
                </SearchableSelect>
              </label>
              <strong class="merge-editor-title">合并单元格</strong>
              <div class="inspector-grid">
                <label>
                  纵向
                  <SearchableSelect
                    :value="selectedPreviewHeaderCell.cell.rowspan"
                    @change="applySelectedHeaderCellMerge(selectNumberValue($event), Number(selectedPreviewHeaderCell.cell.colspan || 1))"
                  >
                    <option v-for="span in selectedPreviewHeaderCellMaxRowspan" :key="span" :value="span">{{ span }} 行</option>
                  </SearchableSelect>
                </label>
                <label>
                  横向
                  <SearchableSelect
                    :value="Math.min(Number(selectedPreviewHeaderCell.cell.colspan || 1), selectedPreviewHeaderCellMaxColspan)"
                    @change="applySelectedHeaderCellMerge(Number(selectedPreviewHeaderCell.cell.rowspan || 1), selectNumberValue($event))"
                  >
                    <option v-for="span in selectedPreviewHeaderCellMaxColspan" :key="span" :value="span">{{ span }} 列</option>
                  </SearchableSelect>
                </label>
              </div>
              <button
                v-if="Number(selectedPreviewHeaderCell.cell.colspan || 1) > 1 || Number(selectedPreviewHeaderCell.cell.rowspan || 1) > 1"
                class="btn-secondary"
                @click="splitSelectedHeaderCell"
              >
                拆分单元格
              </button>
              <button class="btn-delete full-width" @click="deletePreviewHeaderRow(selectedPreviewHeaderCell.row.id)">删除该表头</button>
            </template>
            <template v-else-if="selectedPreviewPeriod">
              <CoursePeriodInspector />
            </template>
            <template v-else-if="selectedPreviewBlankRow">
              <h4>编辑自定义行</h4>
              <div class="inspector-actions">
                <button class="btn-secondary" @click="movePreviewBlankRow(selectedPreviewBlankRow.id, -1)" :disabled="!canMovePreviewBlankRow(selectedPreviewBlankRow.id, -1)">上移</button>
                <button class="btn-secondary" @click="movePreviewBlankRow(selectedPreviewBlankRow.id, 1)" :disabled="!canMovePreviewBlankRow(selectedPreviewBlankRow.id, 1)">下移</button>
              </div>
              <label>
                行标题
                <input v-model="selectedPreviewBlankRow.label" placeholder="例如：午休 / 课间操" />
              </label>
              <button class="btn-delete full-width" @click="deletePreviewBlankRow(selectedPreviewBlankRow.id)">删除自定义行</button>
            </template>
            <template v-else-if="selectedPreviewBlankColumn">
              <h4>编辑自定义列</h4>
              <div class="inspector-actions">
                <button class="btn-secondary" @click="movePreviewBlankColumn(selectedPreviewBlankColumn.id, -1)" :disabled="!canMovePreviewBlankColumn(selectedPreviewBlankColumn.id, -1)">左移</button>
                <button class="btn-secondary" @click="movePreviewBlankColumn(selectedPreviewBlankColumn.id, 1)" :disabled="!canMovePreviewBlankColumn(selectedPreviewBlankColumn.id, 1)">右移</button>
              </div>
              <label>
                列标题
                <input v-model="selectedPreviewBlankColumn.label" placeholder="例如：时间 / 备注" />
              </label>
              <label>
                对齐
                <SearchableSelect v-model="selectedPreviewBlankColumn.align">
                  <option value="center">居中</option>
                  <option value="left">左对齐</option>
                </SearchableSelect>
              </label>
              <button class="btn-delete full-width" @click="deletePreviewBlankColumn(selectedPreviewBlankColumn.id)">删除自定义列</button>
            </template>
            <template v-else-if="selectedPreviewBlankRowCell">
              <h4>编辑自定义单元格</h4>
              <strong class="merge-editor-title">所在自定义行</strong>
              <div class="inspector-actions">
                <button class="btn-secondary" @click="movePreviewBlankRow(selectedPreviewBlankRowCell.row.id, -1)" :disabled="!canMovePreviewBlankRow(selectedPreviewBlankRowCell.row.id, -1)">上移</button>
                <button class="btn-secondary" @click="movePreviewBlankRow(selectedPreviewBlankRowCell.row.id, 1)" :disabled="!canMovePreviewBlankRow(selectedPreviewBlankRowCell.row.id, 1)">下移</button>
              </div>
              <button class="btn-delete full-width" @click="deletePreviewBlankRow(selectedPreviewBlankRowCell.row.id)">删除自定义行</button>
              <label>
                占位文字
                <input v-model="selectedPreviewBlankRowCell.cell.label" placeholder="输入该格显示文字" />
              </label>
              <label>
                对齐
                <SearchableSelect v-model="selectedPreviewBlankRowCell.cell.align">
                  <option value="center">居中</option>
                  <option value="left">左对齐</option>
                </SearchableSelect>
              </label>
              <label class="checkbox-row">
                <input v-model="selectedPreviewBlankRowCell.cell.active" type="checkbox" />
                启用此单元格
              </label>
              <strong class="merge-editor-title">合并单元格</strong>
              <div class="inspector-grid">
                <label>
                  纵向
                  <SearchableSelect :value="selectedPreviewBlankRowCell.cell.rowspan" @change="applySelectedBlankRowCellMerge(selectNumberValue($event), Number(selectedPreviewBlankRowCell.cell.colspan || 1))">
                    <option v-for="span in selectedPreviewBlankRowCellMaxRowspan" :key="span" :value="span">{{ span }} 行</option>
                  </SearchableSelect>
                </label>
                <label>
                  横向
                  <SearchableSelect :value="selectedPreviewBlankRowCell.cell.colspan" @change="applySelectedBlankRowCellMerge(Number(selectedPreviewBlankRowCell.cell.rowspan || 1), selectNumberValue($event))">
                    <option v-for="span in selectedPreviewBlankRowCellMaxColspan" :key="span" :value="span">{{ span }} 列</option>
                  </SearchableSelect>
                </label>
              </div>
              <button v-if="Number(selectedPreviewBlankRowCell.cell.colspan || 1) > 1 || Number(selectedPreviewBlankRowCell.cell.rowspan || 1) > 1" class="btn-secondary" @click="splitSelectedBlankRowCell">拆分单元格</button>
            </template>
            <template v-else-if="selectedPreviewBlankColumnCell">
              <h4>编辑自定义单元格</h4>
              <label>
                占位文字
                <input v-model="selectedPreviewBlankColumnCell.cell.label" placeholder="输入该格显示文字" />
              </label>
              <label>
                对齐
                <SearchableSelect v-model="selectedPreviewBlankColumnCell.cell.align">
                  <option value="center">居中</option>
                  <option value="left">左对齐</option>
                </SearchableSelect>
              </label>
              <label class="checkbox-row">
                <input v-model="selectedPreviewBlankColumnCell.cell.active" type="checkbox" />
                启用此单元格
              </label>
              <strong class="merge-editor-title">合并单元格</strong>
              <div class="inspector-grid">
                <label>
                  纵向
                  <SearchableSelect :value="selectedPreviewBlankColumnCell.cell.rowspan" @change="applySelectedBlankColumnCellMerge(selectNumberValue($event), Number(selectedPreviewBlankColumnCell.cell.colspan || 1))">
                    <option v-for="span in selectedPreviewBlankColumnCellMaxRowspan" :key="span" :value="span">{{ span }} 行</option>
                  </SearchableSelect>
                </label>
                <label>
                  横向
                  <SearchableSelect :value="selectedPreviewBlankColumnCell.cell.colspan" @change="applySelectedBlankColumnCellMerge(Number(selectedPreviewBlankColumnCell.cell.rowspan || 1), selectNumberValue($event))">
                    <option v-for="span in selectedPreviewBlankColumnCellMaxColspan" :key="span" :value="span">{{ span }} 列</option>
                  </SearchableSelect>
                </label>
              </div>
              <button v-if="Number(selectedPreviewBlankColumnCell.cell.colspan || 1) > 1 || Number(selectedPreviewBlankColumnCell.cell.rowspan || 1) > 1" class="btn-secondary" @click="splitSelectedBlankColumnCell">拆分单元格</button>
            </template>
            <p v-else class="preview-empty">点击左侧表格的列、行或单元格进行编辑。</p>
          </aside>
        </div>

        <div v-if="selectedPreviewCell" class="template-inspector-mask">
          <aside class="template-inspector-drawer preview-inspector">
            <header class="template-inspector-header">
              <div>
                <span>编辑</span>
                <strong v-if="selectedPreviewHeaderCell">表头单元格</strong>
                <strong v-else-if="selectedPreviewPeriod">课程单元格</strong>
                <strong v-else-if="selectedPreviewBlankRow">自定义行</strong>
                <strong v-else-if="selectedPreviewBlankColumn">自定义列</strong>
                <strong v-else>自定义单元格</strong>
              </div>
              <button class="btn-secondary" @click="selectedPreviewCell = null">关闭</button>
            </header>
            <template v-if="selectedPreviewHeaderCell">
              <h4>编辑表头单元格</h4>
              <div class="inspector-actions">
                <button class="btn-secondary" @click="movePreviewHeaderRow(selectedPreviewHeaderCell.row.id, -1)" :disabled="!canMovePreviewHeaderRow(selectedPreviewHeaderCell.row.id, -1)">上移表头</button>
                <button class="btn-secondary" @click="movePreviewHeaderRow(selectedPreviewHeaderCell.row.id, 1)" :disabled="!canMovePreviewHeaderRow(selectedPreviewHeaderCell.row.id, 1)">下移表头</button>
              </div>
              <label>
                内容来源
                <SearchableSelect v-model="selectedPreviewHeaderCell.cell.binding">
                  <option value="template_name">模板名称</option>
                  <option value="school_name">学校名</option>
                  <option value="project_name">项目名</option>
                  <option value="owner_name">归属主体名称</option>
                  <option value="custom">自定义内容</option>
                </SearchableSelect>
              </label>
              <label v-if="selectedPreviewHeaderCell.cell.binding === 'custom'">
                表头内容
                <input v-model="selectedPreviewHeaderCell.cell.label" placeholder="输入表头文字" />
              </label>
              <label v-else>
                当前内容
                <div class="fixed-value">{{ previewHeaderCellText(selectedPreviewHeaderCell.cell) }}</div>
              </label>
              <label>
                对齐
                <SearchableSelect v-model="selectedPreviewHeaderCell.cell.align">
                  <option value="center">居中</option>
                  <option value="left">左对齐</option>
                </SearchableSelect>
              </label>
              <strong class="merge-editor-title">合并单元格</strong>
              <div class="inspector-grid">
                <label>
                  纵向
                  <SearchableSelect
                    :value="selectedPreviewHeaderCell.cell.rowspan"
                    @change="applySelectedHeaderCellMerge(selectNumberValue($event), Number(selectedPreviewHeaderCell.cell.colspan || 1))"
                  >
                    <option v-for="span in selectedPreviewHeaderCellMaxRowspan" :key="span" :value="span">{{ span }} 行</option>
                  </SearchableSelect>
                </label>
                <label>
                  横向
                  <SearchableSelect
                    :value="Math.min(Number(selectedPreviewHeaderCell.cell.colspan || 1), selectedPreviewHeaderCellMaxColspan)"
                    @change="applySelectedHeaderCellMerge(Number(selectedPreviewHeaderCell.cell.rowspan || 1), selectNumberValue($event))"
                  >
                    <option v-for="span in selectedPreviewHeaderCellMaxColspan" :key="span" :value="span">{{ span }} 列</option>
                  </SearchableSelect>
                </label>
              </div>
              <button
                v-if="Number(selectedPreviewHeaderCell.cell.colspan || 1) > 1 || Number(selectedPreviewHeaderCell.cell.rowspan || 1) > 1"
                class="btn-secondary"
                @click="splitSelectedHeaderCell"
              >
                拆分单元格
              </button>
              <button class="btn-delete full-width" @click="deletePreviewHeaderRow(selectedPreviewHeaderCell.row.id)">删除该表头</button>
            </template>
            <template v-else-if="selectedPreviewPeriod">
              <CoursePeriodInspector />
            </template>
            <template v-else-if="selectedPreviewBlankRow">
              <div class="inspector-actions">
                <button class="btn-secondary" @click="movePreviewBlankRow(selectedPreviewBlankRow.id, -1)" :disabled="!canMovePreviewBlankRow(selectedPreviewBlankRow.id, -1)">上移</button>
                <button class="btn-secondary" @click="movePreviewBlankRow(selectedPreviewBlankRow.id, 1)" :disabled="!canMovePreviewBlankRow(selectedPreviewBlankRow.id, 1)">下移</button>
              </div>
              <label>
                行标题
                <input v-model="selectedPreviewBlankRow.label" placeholder="例如：午休 / 课间操" />
              </label>
              <button class="btn-delete full-width" @click="deletePreviewBlankRow(selectedPreviewBlankRow.id)">删除自定义行</button>
            </template>
            <template v-else-if="selectedPreviewBlankColumn">
              <div class="inspector-actions">
                <button class="btn-secondary" @click="movePreviewBlankColumn(selectedPreviewBlankColumn.id, -1)" :disabled="!canMovePreviewBlankColumn(selectedPreviewBlankColumn.id, -1)">左移</button>
                <button class="btn-secondary" @click="movePreviewBlankColumn(selectedPreviewBlankColumn.id, 1)" :disabled="!canMovePreviewBlankColumn(selectedPreviewBlankColumn.id, 1)">右移</button>
              </div>
              <label>
                列标题
                <input v-model="selectedPreviewBlankColumn.label" placeholder="例如：时间 / 备注" />
              </label>
              <label>
                对齐
                <SearchableSelect v-model="selectedPreviewBlankColumn.align">
                  <option value="center">居中</option>
                  <option value="left">左对齐</option>
                </SearchableSelect>
              </label>
              <button class="btn-delete full-width" @click="deletePreviewBlankColumn(selectedPreviewBlankColumn.id)">删除自定义列</button>
            </template>
            <template v-else-if="selectedPreviewBlankRowCell">
              <strong class="merge-editor-title">所在自定义行</strong>
              <div class="inspector-actions">
                <button class="btn-secondary" @click="movePreviewBlankRow(selectedPreviewBlankRowCell.row.id, -1)" :disabled="!canMovePreviewBlankRow(selectedPreviewBlankRowCell.row.id, -1)">上移</button>
                <button class="btn-secondary" @click="movePreviewBlankRow(selectedPreviewBlankRowCell.row.id, 1)" :disabled="!canMovePreviewBlankRow(selectedPreviewBlankRowCell.row.id, 1)">下移</button>
              </div>
              <button class="btn-delete full-width" @click="deletePreviewBlankRow(selectedPreviewBlankRowCell.row.id)">删除自定义行</button>
              <label>
                占位文字
                <input v-model="selectedPreviewBlankRowCell.cell.label" placeholder="输入该格显示文字" />
              </label>
              <label>
                对齐
                <SearchableSelect v-model="selectedPreviewBlankRowCell.cell.align">
                  <option value="center">居中</option>
                  <option value="left">左对齐</option>
                </SearchableSelect>
              </label>
              <label class="checkbox-row">
                <input v-model="selectedPreviewBlankRowCell.cell.active" type="checkbox" />
                启用此单元格
              </label>
              <strong class="merge-editor-title">合并单元格</strong>
              <div class="inspector-grid">
                <label>
                  纵向
                  <SearchableSelect :value="selectedPreviewBlankRowCell.cell.rowspan" @change="applySelectedBlankRowCellMerge(selectNumberValue($event), Number(selectedPreviewBlankRowCell.cell.colspan || 1))">
                    <option v-for="span in selectedPreviewBlankRowCellMaxRowspan" :key="span" :value="span">{{ span }} 行</option>
                  </SearchableSelect>
                </label>
                <label>
                  横向
                  <SearchableSelect :value="selectedPreviewBlankRowCell.cell.colspan" @change="applySelectedBlankRowCellMerge(Number(selectedPreviewBlankRowCell.cell.rowspan || 1), selectNumberValue($event))">
                    <option v-for="span in selectedPreviewBlankRowCellMaxColspan" :key="span" :value="span">{{ span }} 列</option>
                  </SearchableSelect>
                </label>
              </div>
              <button v-if="Number(selectedPreviewBlankRowCell.cell.colspan || 1) > 1 || Number(selectedPreviewBlankRowCell.cell.rowspan || 1) > 1" class="btn-secondary" @click="splitSelectedBlankRowCell">拆分单元格</button>
            </template>
            <template v-else-if="selectedPreviewBlankColumnCell">
              <label>
                占位文字
                <input v-model="selectedPreviewBlankColumnCell.cell.label" placeholder="输入该格显示文字" />
              </label>
              <label>
                对齐
                <SearchableSelect v-model="selectedPreviewBlankColumnCell.cell.align">
                  <option value="center">居中</option>
                  <option value="left">左对齐</option>
                </SearchableSelect>
              </label>
              <label class="checkbox-row">
                <input v-model="selectedPreviewBlankColumnCell.cell.active" type="checkbox" />
                启用此单元格
              </label>
              <strong class="merge-editor-title">合并单元格</strong>
              <div class="inspector-grid">
                <label>
                  纵向
                  <SearchableSelect :value="selectedPreviewBlankColumnCell.cell.rowspan" @change="applySelectedBlankColumnCellMerge(selectNumberValue($event), Number(selectedPreviewBlankColumnCell.cell.colspan || 1))">
                    <option v-for="span in selectedPreviewBlankColumnCellMaxRowspan" :key="span" :value="span">{{ span }} 行</option>
                  </SearchableSelect>
                </label>
                <label>
                  横向
                  <SearchableSelect :value="selectedPreviewBlankColumnCell.cell.colspan" @change="applySelectedBlankColumnCellMerge(Number(selectedPreviewBlankColumnCell.cell.rowspan || 1), selectNumberValue($event))">
                    <option v-for="span in selectedPreviewBlankColumnCellMaxColspan" :key="span" :value="span">{{ span }} 列</option>
                  </SearchableSelect>
                </label>
              </div>
              <button v-if="Number(selectedPreviewBlankColumnCell.cell.colspan || 1) > 1 || Number(selectedPreviewBlankColumnCell.cell.rowspan || 1) > 1" class="btn-secondary" @click="splitSelectedBlankColumnCell">拆分单元格</button>
            </template>
          </aside>
        </div>

      </div>
    </div>
  </div>
</section>


</template>
