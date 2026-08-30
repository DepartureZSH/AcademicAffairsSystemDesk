# 本地 Supabase 完整历史迁移验收

## 1. 模块结果

本模块将网页版项目的作息分配、用户约束、排课轮次、候选版本和课表项加入既有基础数据迁移。整个导入只读取本机 PostgreSQL 的 `REPEATABLE READ READ ONLY` 快照，并在目标 SQLite 的一个事务中完成；成功时项目 Revision 只增加一次。

历史候选不被伪装成桌面求解器生成的新候选。含硬约束违例的记录以 `invalid` 状态保存，可查看和比较，但不能导出、手工调整或作为下一轮优化的 Warm start。源端失败详情、机构 ID、用户 ID 和连接凭据不迁移。

## 2. 自动验证

- 完整构造快照覆盖作息分配、约束编译、历史轮次、无效候选、XML class ID 课次映射和迁移告警。
- `after_insert` 完成钩子与基础实体共用 SQLite 事务；钩子失败时基础实体、历史数据和 Revision 一并回滚。
- 只读课表 API允许查看 `valid`、`invalid`、`superseded` 候选；手工移动仍只接受 `valid` 候选。
- 前端明确标记只读候选，并禁用导出、手工调整和 Warm start。
- 命令行输出迁移告警，PowerShell 包装脚本强制 Python UTF-8，并在结束后恢复调用者原有环境变量。

## 3. 真实 Docker 数据验收

验收日期：2026-08-31。数据源为正在运行的 `stt-local` 自托管 Supabase PostgreSQL 15，目标为 Git 忽略目录 `.local/legacy-full-import-v2`。

| 项目 | 结果 |
| --- | ---: |
| 目标 Revision | 1 |
| 学期 / 作息 / 时段 | 2 / 9 / 315 |
| 教师 / 班级 / 科目 / 教室 | 165 / 14 / 19 / 23 |
| 课程计划 / 教学任务 / 课次 | 266 / 239 / 488 |
| 有效作息分配 | 64 |
| 约束 | 207 |
| 历史轮次 / 候选 / 课表项 | 7 / 6 / 2,859 |
| 无法关联课次的课表项 | 10 |
| SQLite `integrity_check` | `ok` |
| SQLite 外键问题 | 0 |

207条约束由118条硬 `DifferentDays`、88条硬 `NotOverlap` 和1条软 `NotOverlap` 组成。6个候选全部含硬约束违例，合计83个，因此全部按只读 `invalid` 状态迁移。

源库有65条模板分配，目标迁移64条。唯一跳过项是源库中引用已不存在教师的悬空记录，已通过 `LEGACY_ASSIGNMENT_SKIPPED` 明确记录。另有 `LEGACY_TIME_GRID_NORMALIZED`、`LEGACY_INVALID_CANDIDATES_IMPORTED` 和 `LEGACY_ENTRY_LESSON_UNRESOLVED` 三类汇总告警。

二次兼容验收确认网页版使用8个底层刻度表达一节课。换算后，239个任务和488个课次可编译为17,160个候选位置，运行前预检为0个阻断问题；4个指向无课节作息表的任务安全回退到可用默认作息并给出警告。隔离副本执行10秒本地求解后返回 `infeasible` 且没有伪造候选，与源库6个候选全部含硬约束违例的现状一致。

迁移后重新读取源数据库，模板分配、约束、候选和课表项仍分别为65、207、6和2,859，确认迁移没有回写源库。

## 4. 复验命令

```powershell
.\scripts\import-local-supabase.ps1 `
  -ProjectId '<本地 discover 返回的项目 UUID>' `
  -Workspace '.local\legacy-full-import-recheck'

uv run pytest tests/test_legacy_supabase_importer.py `
  tests/test_project_storage.py `
  tests/test_scheduling.py -q
```

复验应使用新的目标工作区，避免与已有项目混淆。输出中的数据库连接信息不得复制到文档、Issue 或日志附件。
