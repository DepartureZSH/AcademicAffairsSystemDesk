// Extracted verbatim from web guide steps.
export const localGuideSteps: Record<string, {id:string;section:string;target:string;title:string;body:string;fallbackBody?:string}[]> = {
  "lesson_editor_sheet": [
    {
      "id": "lesson-editor-list",
      "section": "planning",
      "target": "lesson-editor-list",
      "title": "编辑课次",
      "body": "一个授课任务可以包含多个课次。这里集中维护课次名称、启用状态、候选时间和课次教室。"
    },
    {
      "id": "lesson-editor-add",
      "section": "planning",
      "target": "lesson-editor-add",
      "title": "新增课次",
      "body": "需要增加周课次数时，在这里新增课次。每个课次都会成为排课算法里的实际 class。"
    },
    {
      "id": "lesson-editor-time",
      "section": "planning",
      "target": "lesson-editor-time",
      "title": "设置期望上课时间",
      "body": "点击选择期望时间后，可以在周课表格子中选择候选时间和优先级。",
      "fallbackBody": "当前还没有课次。请先点击新增课次，再设置期望上课时间。"
    },
    {
      "id": "lesson-editor-room",
      "section": "planning",
      "target": "lesson-editor-room",
      "title": "设置课次教室",
      "body": "默认教室表示沿用授课任务的默认教室，自定义教室表示只给这一课次指定教室。",
      "fallbackBody": "当前还没有课次。请先新增课次或从其他课程导入课次设置。"
    }
  ],
  "course_preferred_sheet": [
    {
      "id": "course-preferred-summary",
      "section": "planning",
      "target": "course-preferred-summary",
      "title": "选择期望时间",
      "body": "不设置期望时间时，默认全部可行时间都可排；设置后，本课次只会在选中的候选时间内排课。"
    },
    {
      "id": "course-preferred-week",
      "section": "planning",
      "target": "course-preferred-week",
      "title": "选择周频率",
      "body": "先确定候选时间适用于哪些周，例如全学期、单周或双周。"
    },
    {
      "id": "course-preferred-priority",
      "section": "planning",
      "target": "course-preferred-priority",
      "title": "设置候选优先级",
      "body": "颜色越浅优先级越高。最高优先对应时间惩罚 0，算法会优先安排到这些时间。"
    },
    {
      "id": "course-preferred-grid",
      "section": "planning",
      "target": "course-preferred-grid",
      "title": "点击周课表格子",
      "body": "点击格子加入候选时间，再次点击可取消。预设按钮可以快速选择上午、下午或全部可行时间。"
    },
    {
      "id": "course-preferred-save",
      "section": "planning",
      "target": "course-preferred-save",
      "title": "保存候选时间",
      "body": "保存后会回到课次编辑。最后仍需保存授课任务，候选时间才会写入项目数据。"
    }
  ]
};
