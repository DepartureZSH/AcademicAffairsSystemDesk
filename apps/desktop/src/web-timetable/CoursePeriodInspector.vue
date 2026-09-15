<script setup lang="ts">
import SearchableSelect from "./SearchableSelect.vue";
import { computed, inject } from "vue";
import { APP_CONTEXT_KEY } from "./appContext";

const {
  beginPeriodTimeEdit,
  commitPeriodTimeDraft,
  commitPeriodTimeOnEnter,
  courseCellExportBottomField,
  courseCellExportLayout,
  courseCellExportTopField,
  deleteSelectedPreviewRow,
  nextPeriodStartTime,
  periodTimeDraftValue,
  periodTimeError,
  previousPeriodEndTime,
  previewPeriodExportStyle,
  previewPeriodMode,
  selectedPeriodMergeSpanCount,
  selectedPreviewPeriod,
  setPreviewPeriodExportStyle,
  setPreviewPeriodMode,
  updatePeriodTimeDraft,
} = inject(APP_CONTEXT_KEY)!;

const cellMode = computed({
  get: () => previewPeriodMode(selectedPreviewPeriod.value),
  set: (mode: "scheduled" | "custom" | "disabled") => {
    if (selectedPreviewPeriod.value) setPreviewPeriodMode(selectedPreviewPeriod.value, mode);
  },
});

const exportStyle = computed({
  get: () => previewPeriodExportStyle(selectedPreviewPeriod.value),
  set: (style: "default" | "custom") => {
    if (selectedPreviewPeriod.value) setPreviewPeriodExportStyle(selectedPreviewPeriod.value, style);
  },
});
</script>

<template>
  <template v-if="selectedPreviewPeriod">
    <div class="period-cell-mode-field">
      <span>单元格用途</span>
      <div class="period-cell-mode-switch" :class="`is-${cellMode}`">
        <button type="button" :class="{ active: cellMode === 'scheduled' }" @click="cellMode = 'scheduled'">安排课次</button>
        <button type="button" :class="{ active: cellMode === 'custom' }" @click="cellMode = 'custom'">自定义内容</button>
        <button type="button" :class="{ active: cellMode === 'disabled' }" @click="cellMode = 'disabled'">不安排</button>
      </div>
    </div>

    <template v-if="cellMode === 'scheduled'">
      <section class="period-inspector-section">
        <strong>示例内容</strong>
        <div class="inspector-grid">
          <label>
            示例课程名
            <input v-model="selectedPreviewPeriod.sample_subject" placeholder="数学" />
          </label>
          <label>
            示例教师名
            <input v-model="selectedPreviewPeriod.sample_teacher" placeholder="张三" />
          </label>
          <label>
            示例教室名
            <input v-model="selectedPreviewPeriod.sample_room" placeholder="一号教室" />
          </label>
          <label>
            示例班级名
            <input v-model="selectedPreviewPeriod.sample_homeroom" placeholder="一年级1班" />
          </label>
        </div>
      </section>

      <section class="period-inspector-section">
        <strong>课次时间</strong>
        <div class="inspector-grid">
          <label>
            开始
            <input
              :value="periodTimeDraftValue(selectedPreviewPeriod, 'start_time')"
              type="time"
              :min="previousPeriodEndTime(selectedPreviewPeriod)"
              :max="periodTimeDraftValue(selectedPreviewPeriod, 'end_time')"
              @focus="beginPeriodTimeEdit(selectedPreviewPeriod)"
              @input="updatePeriodTimeDraft(selectedPreviewPeriod, 'start_time', $event)"
              @change="commitPeriodTimeDraft(selectedPreviewPeriod)"
              @blur="commitPeriodTimeDraft(selectedPreviewPeriod)"
              @keydown.enter.prevent="commitPeriodTimeOnEnter(selectedPreviewPeriod, $event)"
            />
          </label>
          <label>
            结束
            <input
              :value="periodTimeDraftValue(selectedPreviewPeriod, 'end_time')"
              type="time"
              :min="periodTimeDraftValue(selectedPreviewPeriod, 'start_time')"
              :max="nextPeriodStartTime(selectedPreviewPeriod)"
              @focus="beginPeriodTimeEdit(selectedPreviewPeriod)"
              @input="updatePeriodTimeDraft(selectedPreviewPeriod, 'end_time', $event)"
              @change="commitPeriodTimeDraft(selectedPreviewPeriod)"
              @blur="commitPeriodTimeDraft(selectedPreviewPeriod)"
              @keydown.enter.prevent="commitPeriodTimeOnEnter(selectedPreviewPeriod, $event)"
            />
          </label>
        </div>
        <p v-if="periodTimeError(selectedPreviewPeriod)" class="period-time-error">
          {{ periodTimeError(selectedPreviewPeriod) }}
        </p>
        <label>
          对齐
          <SearchableSelect v-model="selectedPreviewPeriod.align">
            <option value="center">居中</option>
            <option value="left">左对齐</option>
          </SearchableSelect>
        </label>
      </section>

      <section class="period-inspector-section">
        <strong>课程单元格导出样式</strong>
        <div class="period-export-style-switch">
          <button type="button" :class="{ active: exportStyle === 'default' }" @click="exportStyle = 'default'">默认</button>
          <button type="button" :class="{ active: exportStyle === 'custom' }" @click="exportStyle = 'custom'">自定义</button>
        </div>
        <p v-if="exportStyle === 'default'" class="period-inspector-hint">
          使用模板默认设置：{{ courseCellExportLayout === 'single_line' ? '单行' : courseCellExportLayout === 'split_rows' ? '上下分行' : '两行' }}。
        </p>
        <template v-else>
          <label>
            呈现方式
            <SearchableSelect v-model="selectedPreviewPeriod.export_layout">
              <option value="single_line">一个单元格内单行</option>
              <option value="two_line">一个单元格内两行</option>
              <option value="split_rows">上下拆分为两行</option>
            </SearchableSelect>
          </label>
          <div class="inspector-grid">
            <label>
              第一行
              <SearchableSelect v-model="selectedPreviewPeriod.export_top_field">
                <option value="subject">课程名</option>
                <option value="teacher">教师名</option>
                <option value="room">教室</option>
                <option value="time">时间</option>
                <option value="homeroom">班级</option>
              </SearchableSelect>
            </label>
            <label>
              第二行
              <SearchableSelect v-model="selectedPreviewPeriod.export_bottom_field" :disabled="selectedPreviewPeriod.export_layout === 'single_line'">
                <option value="subject">课程名</option>
                <option value="teacher">教师名</option>
                <option value="room">教室</option>
                <option value="time">时间</option>
                <option value="homeroom">班级</option>
              </SearchableSelect>
            </label>
          </div>
        </template>
      </section>
    </template>

    <template v-else-if="cellMode === 'custom'">
      <section class="period-inspector-section">
        <strong>自定义单元格</strong>
        <label>
          显示内容
          <textarea v-model="selectedPreviewPeriod.custom_content" rows="4" maxlength="200" placeholder="输入该单元格显示和导出的内容"></textarea>
        </label>
        <div class="inspector-grid">
          <label>
            对齐
            <SearchableSelect v-model="selectedPreviewPeriod.align">
              <option value="center">居中</option>
              <option value="left">左对齐</option>
            </SearchableSelect>
          </label>
          <label>
            横向合并
            <SearchableSelect v-model.number="selectedPreviewPeriod.colspan">
              <option v-for="span in selectedPeriodMergeSpanCount" :key="span" :value="span">{{ span }} 列</option>
            </SearchableSelect>
          </label>
        </div>
      </section>
    </template>

    <div v-else class="period-cell-disabled-state">
      <strong>该单元格不安排课次</strong>
      <p>单元格内容已清空，不参与排课，也不会在导出结果中显示内容。</p>
    </div>

    <button class="btn-delete full-width" @click="deleteSelectedPreviewRow">删除这一节整行</button>
  </template>
</template>
