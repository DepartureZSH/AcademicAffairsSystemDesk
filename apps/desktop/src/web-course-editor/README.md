# 网页版课程编辑流程

本目录完整复用 `STT/apps/web-admin/src` 的三个界面，不维护第二套简化弹窗：

- `PlanningView.vue`：科目配置（任务切换、教师搜索、默认教室、导入、停排／恢复）。
- `TimetableSettingsView.vue`：课次编辑、课次期望上课时间。
- `GlobalOverlays.vue`、`SearchableSelect.vue`：新手指导、可搜索选择器。

`CourseEditor.vue`、`useCourseEditor.ts`、`guideSteps.ts`、样式和来源记录由仓库根目录下的 `node scripts/extract-course-editor.cjs` 生成。需要旁边的 `../STT` 源码仓库；正常构建只使用已生成文件，不依赖网页版仓库或网络。

不要直接修改生成的模板或删减组件。交互函数从网页控制器按依赖提取；本地差异集中在 `scripts/course-editor-local-adapter.txt`。只有以下适配：

- 业务读写改为本地 API／SQLite，保留修订号检查、事务保存及删除前备份。
- 网页的课节时间单位转换成本地排课引擎使用的课节序号，旧课次 ID 不重建；失效的时间配置不得静默丢弃。
- Teleport 和 CSS 命名空间隔离；恢复网页弹窗层级并移除工作区第二列定位。
- 按用户要求，三个编辑弹窗不通过点击遮罩关闭。新手指导的行为保持网页版。
- 保留本地新手指导生命周期；不引入 AI 或远程教务数据访问。

`provenance.json` 记录网页源文件和移植模板摘要。`tests/test_course_editor_parity.py` 检查模板完整性、关键组件、教室选择语义、停排恢复和约束引用保护。

## 验证记录

2026-09-12：前端生产构建通过，Python 163 项测试通过。Playwright 实测三层弹窗的打开／保存／取消、候选时间的单周和优先级设置、课次复制及重开、使用／不使用教室、课次导入不覆盖教师、停排恢复、两套新手指导、三个遮罩不关闭弹窗。截图保存在忽略目录 `output/playwright/`。

SQLite schema 升至 4，为授课任务增加默认候选教室配置。旧项目打开前沿用自动备份再迁移；旧版应用不能直接打开迁移后的项目，应使用升级前备份恢复。本次仅更新开发源码和预览，未替换既有发行包。
