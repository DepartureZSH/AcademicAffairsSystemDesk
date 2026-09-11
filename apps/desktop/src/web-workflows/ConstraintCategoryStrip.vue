<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ChevronLeft, ChevronRight } from "lucide-vue-next";
import { commonConstraintCategories, commonConstraintScenarios } from "./itcConstraints";

const props = defineProps<{ modelValue: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const categories = [
  { id: "all", label: "全部", count: commonConstraintScenarios.length },
  ...commonConstraintCategories.map(category => ({ ...category,
    count: commonConstraintScenarios.filter(rule => rule.category === category.id).length,
  })),
];
const rail = ref<HTMLElement | null>(null);
const canScrollLeft = ref(false);
const canScrollRight = ref(false);
let observer: ResizeObserver | undefined;

function updateScroll() {
  const el = rail.value;
  if (!el) return;
  canScrollLeft.value = el.scrollLeft > 1;
  canScrollRight.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
}
function revealSelected() {
  const el = rail.value;
  const selected = el?.querySelector<HTMLElement>('[aria-checked="true"]');
  if (!el || !selected) return;
  const viewport = el.getBoundingClientRect();
  const item = selected.getBoundingClientRect();
  if (item.left < viewport.left) el.scrollLeft -= viewport.left - item.left;
  else if (item.right > viewport.right) el.scrollLeft += item.right - viewport.right;
  updateScroll();
}
function scroll(direction: number) {
  if (rail.value) rail.value.scrollBy({ left: direction * rail.value.clientWidth * .75 });
}
async function choose(index: number, focus = false) {
  emit("update:modelValue", categories[index].id);
  await nextTick();
  if (focus) rail.value?.querySelectorAll<HTMLElement>('[role="radio"]')[index]?.focus({ preventScroll: true });
  revealSelected();
}
function navigate(event: KeyboardEvent, index: number) {
  let next = index;
  if (event.key === "ArrowRight") next = (index + 1) % categories.length;
  else if (event.key === "ArrowLeft") next = (index + categories.length - 1) % categories.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = categories.length - 1;
  else return;
  event.preventDefault();
  void choose(next, true);
}
watch(() => props.modelValue, () => nextTick(revealSelected));
onMounted(() => {
  observer = new ResizeObserver(revealSelected);
  if (rail.value) observer.observe(rail.value);
  revealSelected();
});
onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <div class="category-strip">
    <button type="button" class="category-scroll" title="向左滚动分类" aria-label="向左滚动分类" :disabled="!canScrollLeft" @click="scroll(-1)"><ChevronLeft :size="18" /></button>
    <div ref="rail" class="category-rail" role="radiogroup" aria-label="约束分类" @scroll.passive="updateScroll">
      <button v-for="(category, index) in categories" :key="category.id" type="button" role="radio"
        class="category-option" :aria-checked="modelValue === category.id" :tabindex="modelValue === category.id ? 0 : -1"
        @click="choose(index)" @keydown="navigate($event, index)">
        <span>{{ category.label }}</span><span class="category-count">{{ category.count }}</span>
      </button>
    </div>
    <button type="button" class="category-scroll" title="向右滚动分类" aria-label="向右滚动分类" :disabled="!canScrollRight" @click="scroll(1)"><ChevronRight :size="18" /></button>
  </div>
</template>

<style scoped>
.category-strip { display: grid; grid-template-columns: 30px minmax(0, 1fr) 30px; align-items: center; gap: 4px; min-width: 0; }
.category-rail { display: flex; gap: 6px; min-width: 0; overflow-x: auto; overscroll-behavior-x: contain; scrollbar-width: thin; scrollbar-color: #c0d4cd transparent; padding: 3px 2px 6px; }
.category-option { display: inline-flex; align-items: center; justify-content: center; gap: 8px; flex: 0 0 auto; min-height: 40px; padding: 8px 12px; border: 1px solid transparent; border-radius: 6px; background: #f3f7f5; color: #50675e; font-size: 13px; line-height: 20px; white-space: nowrap; }
.category-option:hover { background: #e6f1eb; }
.category-option[aria-checked="true"] { background: #2b7c6e; color: white; border-color: #2b7c6e; }
.category-count { font-size: 12px; font-variant-numeric: tabular-nums; opacity: .8; }
.category-scroll { display: grid; place-items: center; width: 30px; height: 40px; padding: 0; border: 0; border-radius: 4px; background: transparent; color: #49685f; }
.category-scroll:hover:not(:disabled) { background: #e6f1eb; }
.category-scroll:disabled { opacity: .25; cursor: default; }
.category-option:focus-visible, .category-scroll:focus-visible { outline: 2px solid #2b7c6e; outline-offset: 1px; }
</style>
