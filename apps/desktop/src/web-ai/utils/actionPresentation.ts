// @ts-nocheck -- pure display helpers extracted from the web controller.
export function agentActionCountItems(action: AgentAction): Array<{ label: string; value: number }> {
    const counts = agentActionCounts(action);
    const items: Array<[string, unknown]> = [
      ["新增", counts.create],
      ["更新", counts.update],
      ["删除", counts.delete],
      ["跳过", counts.skip],
      ["运行", counts.run],
      ["失败", counts.failed],
    ];
    return items.map(([label, value]) => ({ label, value: Number(value || 0) })).filter((item) => item.value > 0);
  }

function agentActionCounts(action: AgentAction) {
    const counts = agentActionPreview(action).counts;
    return counts && typeof counts === "object" ? (counts as Record<string, unknown>) : {};
  }

function agentActionPreview(action: AgentAction) {
    const preview = action.preview;
    return preview && typeof preview === "object" ? (preview as Record<string, unknown>) : {};
  }

export function agentActionDetailTables(action: AgentAction): AgentActionDetailTable[] {
    const counts = agentActionCounts(action);
    const tables: AgentActionDetailTable[] = [];
    const groupConfigs: Array<{
      key: string;
      title: string;
      tone: AgentActionDetailTable["tone"];
      countKey: string;
      status: string;
      keys: string[];
      emptyReason?: string;
    }> = [
      {
        key: "create",
        title: "新增",
        tone: "create",
        countKey: "create",
        status: "将新增",
        keys: ["create_names", "created_names", "creates", "created"],
      },
      {
        key: "update",
        title: "更新",
        tone: "update",
        countKey: "update",
        status: "将更新",
        keys: ["update_names", "updated_names", "updates", "updated"],
      },
      {
        key: "delete",
        title: "删除",
        tone: "delete",
        countKey: "delete",
        status: "将删除",
        keys: ["delete_names", "deleted_names", "deletes", "deleted"],
      },
      {
        key: "skip",
        title: "跳过",
        tone: "skip",
        countKey: "skip",
        status: "跳过",
        keys: ["skip_names", "skipped_names", "skips", "skipped"],
        emptyReason: "已与现有数据一致或无需写入",
      },
    ];

    for (const config of groupConfigs) {
      const total = Number(counts[config.countKey] || 0);
      if (total <= 0) continue;
      const rows = agentActionRowsFromPreviewList(action, config.keys, config.status, config.emptyReason);
      if (!rows.length) {
        rows.push({
          name: `共 ${total} 项`,
          detail: config.emptyReason || "此旧版记录未提供逐项明细",
          status: config.status,
          reason: "",
        });
      } else {
        appendOverflowRow(rows, total, config.status);
      }
      tables.push({
        key: config.key,
        title: `${config.title} ${total}`,
        tone: config.tone,
        rows,
      });
    }

    const failureRows = agentActionPreviewList(action, ["failures", "failed_items", "errors"]).map((item) => {
      const record = asRecord(item) || {};
      return {
        name: agentActionItemName(item),
        detail: String(record.index !== undefined ? `第 ${Number(record.index) + 1} 项` : agentActionItemDetail(item)),
        status: "失败",
        reason: String(record.reason || record.message || "预检未通过"),
      };
    });
    const failedTotal = Number(counts.failed || 0);
    if (failedTotal > 0 || failureRows.length || action.error_message) {
      if (!failureRows.length && action.error_message) {
        failureRows.push({
          name: "执行失败",
          detail: "请查看错误信息",
          status: "失败",
          reason: String(action.error_message),
        });
      } else {
        appendOverflowRow(failureRows, failedTotal, "失败");
      }
      tables.push({
        key: "failed",
        title: `失败 ${Math.max(failedTotal, failureRows.length)}`,
        tone: "failed",
        rows: failureRows,
      });
    }

    if (!tables.length && agentActionSamples(action).length) {
      tables.push({
        key: "samples",
        title: "影响样例",
        tone: "neutral",
        rows: agentActionSamples(action).map((sample) => ({
          name: sample,
          detail: "样例",
          status: "待确认",
          reason: "",
        })),
      });
    }
    return tables;
  }

function agentActionRowsFromPreviewList(
    action: AgentAction,
    keys: string[],
    status: string,
    reason = "",
  ) {
    const lookup = agentActionNameLookup(action);
    return agentActionPreviewList(action, keys).map((item) => {
      const name = agentActionItemName(item);
      const source = asRecord(item) ? item : lookup.get(name);
      const itemReason = String(asRecord(item)?.reason || reason || "");
      return {
        name,
        detail: agentActionItemDetail(source),
        status,
        reason: itemReason,
      };
    });
  }

function agentActionNameLookup(action: AgentAction) {
    const lookup = new Map<string, unknown>();
    for (const item of agentActionPayloadItems(action)) {
      const name = agentActionItemName(item);
      if (name && !lookup.has(name)) {
        lookup.set(name, item);
      }
    }
    return lookup;
  }

function agentActionPayloadItems(action: AgentAction) {
    const payload = asRecord(action.payload) || {};
    const itemLists = [
      payload.items,
      payload.teachers,
      payload.homerooms,
      payload.subjects,
      payload.rooms,
      payload.lessons,
      payload.constraints,
      payload.ids,
      payload.names,
    ];
    for (const list of itemLists) {
      if (Array.isArray(list)) {
        return list.filter((item) => item !== null && item !== undefined);
      }
    }
    return Object.keys(payload).length ? [payload] : [];
  }

function asRecord(value: unknown) {
    return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : undefined;
  }

function agentActionItemName(item: unknown) {
    if (typeof item === "string" || typeof item === "number") return String(item);
    const record = asRecord(item) || {};
    const candidates = [
      record.name,
      record.title,
      record.label,
      record.teacher_name,
      record.homeroom_name,
      record.subject_name,
      record.room_name,
      record.class_name,
      record.id,
    ];
    const value = candidates.find((candidate) => typeof candidate === "string" && candidate.trim());
    return typeof value === "string" ? value.trim() : "未命名";
  }

function agentActionPreviewList(action: AgentAction, keys: string[]) {
    const preview = agentActionPreview(action);
    const values: unknown[] = [];
    for (const key of keys) {
      const rawValue = preview[key];
      if (Array.isArray(rawValue)) {
        values.push(...rawValue);
      }
    }
    return values;
  }

function agentActionItemDetail(item: unknown) {
    const record = asRecord(item) || {};
    const tags = Array.isArray(record.tags) ? record.tags.map((tag) => String(tag)).filter(Boolean).join("、") : "";
    const candidates = [
      record.department,
      record.teacher_group,
      record.group,
      record.grade,
      record.type,
      record.room_type,
      tags,
    ]
      .map((value) => String(value || "").trim())
      .filter(Boolean);
    return candidates.length ? candidates.join(" · ") : "待确认";
  }

function appendOverflowRow(rows: AgentActionDetailRow[], total: number, status: string) {
    if (total > rows.length) {
      rows.push({
        name: `还有 ${total - rows.length} 项`,
        detail: "此旧版记录仅保留部分预览明细",
        status,
        reason: "",
      });
    }
    return rows;
  }

function agentActionSamples(action: AgentAction) {
    const preview = agentActionPreview(action);
    const samples = Array.isArray(preview.samples) ? preview.samples : preview.sample_names;
    if (!Array.isArray(samples)) return [];
    return samples.map((item) => String(item)).filter(Boolean).slice(0, 5);
  }

export function agentActionFailures(action: AgentAction) {
    const preview = agentActionPreview(action);
    const failures = preview.failures;
    if (!Array.isArray(failures)) return [];
    return failures.map((item) => agentActionIssueText(item, "预检未通过")).filter(Boolean).slice(0, 8);
  }

function agentActionIssueText(item: unknown, fallback = "") {
    if (typeof item === "string" || typeof item === "number") return String(item);
    const record = asRecord(item) || {};
    const name = agentActionItemName(item);
    const reason = String(record.reason || record.message || record.error || fallback || "").trim();
    if (name && name !== "未命名" && reason) return `${name}：${reason}`;
    if (reason) return reason;
    return name && name !== "未命名" ? name : fallback;
  }

export function agentActionWarnings(action: AgentAction) {
    const preview = agentActionPreview(action);
    const warnings = preview.warnings;
    if (!Array.isArray(warnings)) return [];
    return warnings.map((item) => agentActionIssueText(item, "需要确认")).filter(Boolean).slice(0, 8);
  }

export function agentActionStatusLabel(status: unknown) {
    const statusMap: Record<string, string> = {
      pending_confirmation: "待确认",
      executed: "已执行",
      failed: "失败",
      rejected: "已拒绝",
      executing: "执行中",
      stale: "数据已变化",
      superseded: "已被替代",
    };
    return statusMap[String(status || "pending_confirmation")] || String(status || "待确认");
  }

export function agentActionTargetLabel(action: AgentAction) {
    const preview = agentActionPreview(action);
    const targetLabels: Record<string, string> = {
      teacher: "教师",
      homeroom: "班级",
      subject: "科目",
      room_type: "教室类型",
      room: "教室",
      course_plan: "课程计划",
      task: "授课任务",
      lesson: "课次",
      constraint: "约束",
      run: "排课运行",
      change_set: "跨对象变更集",
    };
    return String(preview.target_label || targetLabels[String(action.target)] || action.target || "数据");
  }

export function agentActionOperationLabel(action: AgentAction) {
    const preview = agentActionPreview(action);
    const operationLabels: Record<string, string> = {
      create: "新增",
      update: "更新",
      delete: "删除",
      bulk_upsert: "批量新增/更新",
      preview: "预览",
      run: "发起",
      change_set: "整批执行",
    };
    return operationLabels[String(action.operation)] || String(preview.operation_label || "操作").slice(0, 20);
  }

export function agentActionTitle(action: AgentAction) {
    if (action.operation === "change_set") {
      const counts = agentActionCounts(action);
      const operations = ["create", "update", "delete", "run"].filter((key) => Number(counts[key] || 0) > 0);
      const titles: Record<string, string> = { create: "批量新增数据", update: "批量更新数据", delete: "批量删除数据", run: "发起排课" };
      return operations.length === 1 ? titles[operations[0]] : "批量数据变更";
    }
    const title = `${agentActionOperationLabel(action)}${agentActionTargetLabel(action)}`;
    return title.length > 36 ? `${title.slice(0, 35)}…` : title;
  }

export function agentActionDisplaySummary(action: AgentAction) {
    const preview = agentActionPreview(action);
    return String(preview.summary || action.human_summary || `${agentActionOperationLabel(action)}${agentActionTargetLabel(action)}`);
  }
