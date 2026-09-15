<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, onUpdated, ref, watch } from "vue";

defineOptions({ inheritAttrs: false });

type SelectOption = {
  key: string;
  value: unknown;
  label: string;
  disabled: boolean;
};

const props = withDefaults(defineProps<{
  modelValue?: unknown;
  value?: unknown;
  disabled?: boolean;
  placeholder?: string;
  modelModifiers?: Record<string, boolean>;
}>(), {
  modelValue: undefined,
  value: undefined,
  disabled: false,
  placeholder: "请选择",
  modelModifiers: () => ({}),
});

const emit = defineEmits<{
  (event: "update:modelValue", value: unknown): void;
  (event: "change", value: { target: { value: unknown } }): void;
}>();

const root = ref<HTMLElement | null>(null);
const trigger = ref<HTMLInputElement | null>(null);
const menu = ref<HTMLElement | null>(null);
const optionsContainer = ref<HTMLElement | null>(null);
const sourceSelect = ref<HTMLSelectElement | null>(null);
const open = ref(false);
const query = ref("");
const inputText = ref("");
const activeIndex = ref(0);
const menuStyle = ref<Record<string, string>>({});
const options = ref<SelectOption[]>([]);
let optionSignature = "";
let interactionVersion = 0;
let pointerStartedOnTrigger = false;

function refreshOptions() {
  const nextOptions = Array.from(sourceSelect.value?.options || []).map((option, index) => ({
    key: `${index}-${option.value}`,
    value: option.value,
    label: option.text.replace(/\s+/g, " ").trim(),
    disabled: option.disabled,
  }));
  const nextSignature = nextOptions
    .map((option) => `${String(option.value)}\u0000${option.label}\u0000${option.disabled ? 1 : 0}`)
    .join("\u0001");
  if (nextSignature === optionSignature) return;
  optionSignature = nextSignature;
  options.value = nextOptions;
}

const currentValue = computed(() => props.modelValue !== undefined ? props.modelValue : props.value);
const selectedOption = computed(() => options.value.find((option) => String(option.value ?? "") === String(currentValue.value ?? "")));
const selectedLabel = computed(() => selectedOption.value?.label || props.placeholder);
const filteredOptions = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase("zh-Hans-CN");
  if (!needle) return options.value;
  return options.value.filter((option) => option.label.toLocaleLowerCase("zh-Hans-CN").includes(needle));
});

function updateMenuPosition() {
  if (!trigger.value) return;
  const rect = trigger.value.getBoundingClientRect();
  const availableBelow = Math.max(window.innerHeight - rect.bottom - 16, 140);
  menuStyle.value = {
    top: `${Math.min(rect.bottom + 5, window.innerHeight - 150)}px`,
    left: `${Math.max(8, Math.min(rect.left, window.innerWidth - Math.max(rect.width, 220) - 8))}px`,
    width: `${Math.max(rect.width, 220)}px`,
    maxHeight: `${Math.min(320, availableBelow)}px`,
  };
}

async function openMenu(selectText = true) {
  if (props.disabled) return;
  const version = ++interactionVersion;
  if (!open.value) {
    inputText.value = selectedLabel.value;
    query.value = "";
  }
  open.value = true;
  activeIndex.value = Math.max(options.value.findIndex((option) => option === selectedOption.value), 0);
  await nextTick();
  if (version !== interactionVersion || !open.value || props.disabled) return;
  updateMenuPosition();
  trigger.value?.focus();
  if (selectText) trigger.value?.select();
}

function clearTriggerSelection(blurTrigger = false) {
  const input = trigger.value;
  if (!input) return;
  if (blurTrigger) input.blur();
  const caret = input.value.length;
  input.setSelectionRange(caret, caret);
}

function closeMenu(restoreFocus = false, blurTrigger = false) {
  const version = ++interactionVersion;
  open.value = false;
  query.value = "";
  inputText.value = selectedLabel.value;
  nextTick(() => {
    if (version !== interactionVersion) return;
    if (restoreFocus) trigger.value?.focus();
    clearTriggerSelection(blurTrigger && !restoreFocus);
  });
}

function onTriggerClick() {
  // A wrapping label forwards clicks to its input without a pointerdown on it.
  // Focus restoration and those forwarded clicks must not reopen a dismissed menu.
  if (!pointerStartedOnTrigger) return;
  pointerStartedOnTrigger = false;
  if (!open.value) void openMenu();
}

function normalizedValue(value: unknown) {
  if (!props.modelModifiers?.number) return value;
  if (value === "" || value == null) return value;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? value : parsed;
}

function selectOption(option: SelectOption) {
  if (option.disabled) return;
  const value = normalizedValue(option.value);
  emit("update:modelValue", value);
  emit("change", { target: { value } });
  inputText.value = option.label;
  closeMenu(true);
}

function moveActive(delta: number) {
  const available = filteredOptions.value;
  if (!available.length) return;
  let next = activeIndex.value;
  do {
    next = (next + delta + available.length) % available.length;
  } while (available[next]?.disabled && next !== activeIndex.value);
  activeIndex.value = next;
}

function onTriggerInput(event: Event) {
  if (!open.value) void openMenu(false);
  inputText.value = (event.target as HTMLInputElement).value;
  query.value = inputText.value;
}

function onTriggerKeydown(event: KeyboardEvent) {
  if (event.key === "Tab") {
    closeMenu();
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    if (open.value) event.stopPropagation();
    closeMenu(true);
    return;
  }
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    if (!open.value) void openMenu();
    else moveActive(event.key === "ArrowDown" ? 1 : -1);
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    if (!open.value) {
      void openMenu();
      return;
    }
    const option = filteredOptions.value[activeIndex.value];
    if (option) selectOption(option);
  }
}

function onDocumentPointerDown(event: PointerEvent) {
  const target = event.target as Node | null;
  pointerStartedOnTrigger = target === trigger.value && event.button === 0;
  if (!target || root.value?.contains(target) || menu.value?.contains(target)) return;
  closeMenu(false, true);
}

function onDocumentFocusIn(event: FocusEvent) {
  const target = event.target as Node | null;
  if (!open.value || !target || root.value?.contains(target) || menu.value?.contains(target)) return;
  closeMenu();
}

function onMenuWheel(event: WheelEvent) {
  const container = optionsContainer.value;
  if (!container) return;
  event.preventDefault();
  event.stopPropagation();
  const multiplier = event.deltaMode === WheelEvent.DOM_DELTA_LINE
    ? 18
    : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
      ? container.clientHeight
      : 1;
  container.scrollTop += event.deltaY * multiplier;
}

function onViewportChange() {
  if (open.value) updateMenuPosition();
}

watch(filteredOptions, () => {
  activeIndex.value = Math.min(activeIndex.value, Math.max(filteredOptions.value.length - 1, 0));
});

watch(() => props.disabled, (disabled) => {
  if (disabled) closeMenu();
});

watch(selectedLabel, (label) => {
  if (!open.value) inputText.value = label;
}, { immediate: true });

onMounted(() => {
  refreshOptions();
  document.addEventListener("pointerdown", onDocumentPointerDown, true);
  document.addEventListener("focusin", onDocumentFocusIn, true);
  window.addEventListener("resize", onViewportChange);
  window.addEventListener("scroll", onViewportChange, true);
});

onUpdated(refreshOptions);

onBeforeUnmount(() => {
  interactionVersion++;
  document.removeEventListener("pointerdown", onDocumentPointerDown, true);
  document.removeEventListener("focusin", onDocumentFocusIn, true);
  window.removeEventListener("resize", onViewportChange);
  window.removeEventListener("scroll", onViewportChange, true);
});
</script>

<template>
  <div
    ref="root"
    v-bind="$attrs"
    class="searchable-select"
    :class="{ open, disabled }"
  >
    <div class="searchable-select-input">
      <input
        ref="trigger"
        :value="inputText"
        type="search"
        class="searchable-select-trigger"
        role="combobox"
        :aria-label="$attrs['aria-label'] as string | undefined"
        :aria-labelledby="$attrs['aria-labelledby'] as string | undefined"
        :aria-expanded="open"
        aria-haspopup="listbox"
        aria-autocomplete="list"
        :placeholder="placeholder"
        :disabled="disabled"
        @click="onTriggerClick"
        @input="onTriggerInput"
        @keydown="onTriggerKeydown"
      >
      <button
        type="button"
        class="searchable-select-chevron-button"
        :aria-label="open ? '收起选项' : '展开并搜索选项'"
        :disabled="disabled"
        @mousedown.prevent
        @click="open ? closeMenu(true) : openMenu()"
      >
        <svg class="searchable-select-chevron" viewBox="0 0 1024 1024" aria-hidden="true">
          <path
            v-if="open"
            d="M745.376 662.624L512 429.248l-233.376 233.376-45.248-45.248L512 338.752l278.624 278.624z"
          />
          <path
            v-else
            d="M512 685.248l-278.624-278.624 45.248-45.248L512 594.752l233.376-233.376 45.248 45.248z"
          />
        </svg>
      </button>
    </div>
    <select ref="sourceSelect" class="searchable-select-source" tabindex="-1" aria-hidden="true">
      <slot />
    </select>
    <Teleport to="body"><div class="web-course-editor">
      <div
        v-if="open"
        ref="menu"
        class="searchable-select-menu"
        :style="menuStyle"
        role="listbox"
        @wheel="onMenuWheel"
      >
        <div ref="optionsContainer" class="searchable-select-options">
          <button
            v-for="(option, index) in filteredOptions"
            :key="option.key"
            type="button"
            class="searchable-select-option"
            :class="{
              active: index === activeIndex,
              selected: String(option.value ?? '') === String(currentValue ?? ''),
            }"
            :disabled="option.disabled"
            role="option"
            :aria-selected="String(option.value ?? '') === String(currentValue ?? '')"
            @mouseenter="activeIndex = index"
            @click="selectOption(option)"
          >
            <span>{{ option.label }}</span>
            <strong v-if="String(option.value ?? '') === String(currentValue ?? '')" aria-hidden="true">✓</strong>
          </button>
          <p v-if="!filteredOptions.length" class="searchable-select-empty">没有匹配选项</p>
        </div>
      </div>
    </div></Teleport>
  </div>
</template>

<style scoped>
/* The outer shell owns the border, including inside page-specific input layouts. */
.searchable-select .searchable-select-input > .searchable-select-trigger,
.searchable-select .searchable-select-input > .searchable-select-chevron-button {
  border: 0;
  border-radius: 0;
  box-shadow: none;
  outline: none;
}

.searchable-select:not(.disabled) .searchable-select-input:focus-within {
  border-color: #2f8774;
  box-shadow: 0 0 0 3px rgba(47, 135, 116, 0.12);
}
</style>
