SCHEMA_VERSION = 2

SCHEMA_V1 = r"""
CREATE TABLE app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE TABLE project (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE academic_years (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE terms (
    id TEXT PRIMARY KEY,
    academic_year_id TEXT REFERENCES academic_years(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    week_count INTEGER NOT NULL DEFAULT 20 CHECK (week_count BETWEEN 1 AND 60),
    day_count INTEGER NOT NULL DEFAULT 5 CHECK (day_count BETWEEN 1 AND 7),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE bell_schedules (
    id TEXT PRIMARY KEY,
    term_id TEXT REFERENCES terms(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    day_count INTEGER NOT NULL DEFAULT 5 CHECK (day_count BETWEEN 1 AND 7),
    slot_duration_minutes INTEGER NOT NULL DEFAULT 40 CHECK (slot_duration_minutes BETWEEN 5 AND 240),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    display_config TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE time_slots (
    id TEXT PRIMARY KEY,
    bell_schedule_id TEXT NOT NULL REFERENCES bell_schedules(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    period_index INTEGER NOT NULL CHECK (period_index >= 0),
    label TEXT NOT NULL,
    start_slot INTEGER NOT NULL DEFAULT 0 CHECK (start_slot >= 0),
    length_slots INTEGER NOT NULL DEFAULT 1 CHECK (length_slots > 0),
    start_time_minutes INTEGER NOT NULL CHECK (start_time_minutes BETWEEN 0 AND 1439),
    end_time_minutes INTEGER NOT NULL CHECK (end_time_minutes BETWEEN 1 AND 1440),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    display_config TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (bell_schedule_id, weekday, period_index),
    CHECK (end_time_minutes > start_time_minutes)
) STRICT;

CREATE TABLE grades (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE teachers (
    id TEXT PRIMARY KEY,
    employee_no TEXT,
    name TEXT NOT NULL,
    department TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE room_types (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE rooms (
    id TEXT PRIMARY KEY,
    room_type_id TEXT REFERENCES room_types(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    room_no TEXT,
    capacity INTEGER CHECK (capacity IS NULL OR capacity >= 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE homerooms (
    id TEXT PRIMARY KEY,
    grade_id TEXT REFERENCES grades(id) ON DELETE SET NULL,
    term_id TEXT REFERENCES terms(id) ON DELETE SET NULL,
    head_teacher_id TEXT REFERENCES teachers(id) ON DELETE SET NULL,
    default_room_id TEXT REFERENCES rooms(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    group_name TEXT,
    student_count INTEGER CHECK (student_count IS NULL OR student_count >= 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE subjects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT,
    category TEXT NOT NULL DEFAULT 'general',
    default_duration_slots INTEGER NOT NULL DEFAULT 1 CHECK (default_duration_slots > 0),
    requires_special_room INTEGER NOT NULL DEFAULT 0 CHECK (requires_special_room IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE course_plans (
    id TEXT PRIMARY KEY,
    term_id TEXT REFERENCES terms(id) ON DELETE CASCADE,
    homeroom_id TEXT NOT NULL REFERENCES homerooms(id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
    weekly_slots INTEGER NOT NULL CHECK (weekly_slots >= 0),
    duration_slots INTEGER NOT NULL DEFAULT 1 CHECK (duration_slots > 0),
    allow_double_period INTEGER NOT NULL DEFAULT 0 CHECK (allow_double_period IN (0, 1)),
    priority INTEGER NOT NULL DEFAULT 0,
    week_bits TEXT NOT NULL DEFAULT '11111111111111111111',
    day_bits TEXT NOT NULL DEFAULT '11111',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (term_id, homeroom_id, subject_id)
) STRICT;

CREATE TABLE teaching_tasks (
    id TEXT PRIMARY KEY,
    term_id TEXT REFERENCES terms(id) ON DELETE CASCADE,
    course_plan_id TEXT REFERENCES course_plans(id) ON DELETE SET NULL,
    homeroom_id TEXT NOT NULL REFERENCES homerooms(id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
    primary_teacher_id TEXT REFERENCES teachers(id) ON DELETE SET NULL,
    weekly_slots INTEGER NOT NULL CHECK (weekly_slots >= 0),
    duration_slots INTEGER NOT NULL DEFAULT 1 CHECK (duration_slots > 0),
    required_room_type TEXT,
    fixed_room_id TEXT REFERENCES rooms(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    week_bits TEXT NOT NULL DEFAULT '11111111111111111111',
    day_bits TEXT NOT NULL DEFAULT '11111',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE task_lessons (
    id TEXT PRIMARY KEY,
    teaching_task_id TEXT NOT NULL REFERENCES teaching_tasks(id) ON DELETE CASCADE,
    lesson_index INTEGER NOT NULL CHECK (lesson_index >= 0),
    duration_slots INTEGER NOT NULL DEFAULT 1 CHECK (duration_slots > 0),
    source_id TEXT,
    week_bits TEXT NOT NULL DEFAULT '11111111111111111111',
    day_bits TEXT NOT NULL DEFAULT '11111',
    label TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (teaching_task_id, lesson_index)
) STRICT;

CREATE TABLE availability_rules (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('teacher', 'homeroom', 'room', 'lesson')),
    entity_id TEXT NOT NULL,
    bell_schedule_id TEXT REFERENCES bell_schedules(id) ON DELETE CASCADE,
    time_slot_id TEXT REFERENCES time_slots(id) ON DELETE CASCADE,
    week_bits TEXT NOT NULL DEFAULT '11111111111111111111',
    day_bits TEXT NOT NULL DEFAULT '11111',
    required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0, 1)),
    penalty INTEGER NOT NULL DEFAULT 0 CHECK (penalty >= 0),
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE constraints (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'hard' CHECK (severity IN ('hard', 'soft')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    weight INTEGER NOT NULL DEFAULT 100 CHECK (weight >= 0),
    parameters TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE constraint_members (
    id TEXT PRIMARY KEY,
    constraint_id TEXT NOT NULL REFERENCES constraints(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE compiled_constraints (
    id TEXT PRIMARY KEY,
    constraint_id TEXT NOT NULL REFERENCES constraints(id) ON DELETE CASCADE,
    compiler_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE data_snapshots (
    id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    input_hash TEXT NOT NULL,
    payload_path TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE optimization_sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'completed', 'cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE scheduling_rounds (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES optimization_sessions(id) ON DELETE CASCADE,
    snapshot_id TEXT REFERENCES data_snapshots(id) ON DELETE RESTRICT,
    parent_candidate_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('queued', 'preparing', 'solving', 'validating', 'succeeded', 'infeasible', 'cancelled', 'failed', 'failed_recoverable')),
    time_budget_seconds INTEGER NOT NULL DEFAULT 60 CHECK (time_budget_seconds BETWEEN 10 AND 1800),
    random_seed INTEGER NOT NULL DEFAULT 0,
    algorithm TEXT NOT NULL DEFAULT 'cp_sat',
    algorithm_config TEXT NOT NULL DEFAULT '{}',
    input_hash TEXT,
    started_at TEXT,
    finished_at TEXT,
    stop_reason TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE candidates (
    id TEXT PRIMARY KEY,
    round_id TEXT NOT NULL REFERENCES scheduling_rounds(id) ON DELETE CASCADE,
    parent_candidate_id TEXT REFERENCES candidates(id) ON DELETE SET NULL,
    snapshot_id TEXT REFERENCES data_snapshots(id) ON DELETE RESTRICT,
    name TEXT,
    status TEXT NOT NULL CHECK (status IN ('valid', 'invalid', 'superseded')),
    hard_violations INTEGER NOT NULL DEFAULT 0 CHECK (hard_violations >= 0),
    total_score INTEGER NOT NULL DEFAULT 0,
    input_hash TEXT NOT NULL,
    solver_version TEXT NOT NULL,
    validator_version TEXT NOT NULL,
    diagnostics TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE round_events (
    id TEXT PRIMARY KEY,
    round_id TEXT NOT NULL REFERENCES scheduling_rounds(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE (round_id, sequence)
) STRICT;

CREATE TABLE timetable_entries (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    task_lesson_id TEXT REFERENCES task_lessons(id) ON DELETE SET NULL,
    teaching_task_id TEXT REFERENCES teaching_tasks(id) ON DELETE SET NULL,
    homeroom_id TEXT REFERENCES homerooms(id) ON DELETE SET NULL,
    subject_id TEXT REFERENCES subjects(id) ON DELETE SET NULL,
    teacher_id TEXT REFERENCES teachers(id) ON DELETE SET NULL,
    room_id TEXT REFERENCES rooms(id) ON DELETE SET NULL,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    start_slot INTEGER NOT NULL CHECK (start_slot >= 0),
    duration_slots INTEGER NOT NULL DEFAULT 1 CHECK (duration_slots > 0),
    week_bits TEXT NOT NULL,
    source_id TEXT,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE candidate_metrics (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL,
    metric_value REAL NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',
    UNIQUE (candidate_id, metric_key)
) STRICT;

CREATE TABLE validation_issues (
    id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,
    scope_id TEXT,
    severity TEXT NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE import_jobs (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('preview', 'confirmed', 'abandoned', 'failed')),
    summary TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE export_jobs (
    id TEXT PRIMARY KEY,
    export_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    relative_path TEXT,
    summary TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE backup_records (
    id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    revision INTEGER NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    retained INTEGER NOT NULL DEFAULT 0 CHECK (retained IN (0, 1)),
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX idx_homerooms_grade ON homerooms(grade_id);
CREATE INDEX idx_course_plans_homeroom ON course_plans(homeroom_id);
CREATE INDEX idx_teaching_tasks_homeroom ON teaching_tasks(homeroom_id);
CREATE INDEX idx_task_lessons_task ON task_lessons(teaching_task_id);
CREATE INDEX idx_rounds_session ON scheduling_rounds(session_id, created_at);
CREATE INDEX idx_candidates_round ON candidates(round_id, created_at);
CREATE INDEX idx_entries_candidate ON timetable_entries(candidate_id);
CREATE INDEX idx_entries_teacher_slot ON timetable_entries(candidate_id, teacher_id, weekday, start_slot);
CREATE INDEX idx_entries_homeroom_slot ON timetable_entries(candidate_id, homeroom_id, weekday, start_slot);
CREATE INDEX idx_entries_room_slot ON timetable_entries(candidate_id, room_id, weekday, start_slot);
"""


SCHEMA_V2 = r"""
CREATE TABLE timetable_template_assignments (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (
        entity_type IN ('homeroom', 'teacher', 'subject', 'room_type', 'room', 'all')
    ),
    entity_id TEXT,
    bell_schedule_id TEXT NOT NULL REFERENCES bell_schedules(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (entity_type = 'all' AND entity_id IS NULL)
        OR (entity_type <> 'all' AND entity_id IS NOT NULL)
    )
) STRICT;

CREATE UNIQUE INDEX idx_timetable_template_assignment_entity
ON timetable_template_assignments(entity_type, ifnull(entity_id, ''));

CREATE INDEX idx_timetable_template_assignment_schedule
ON timetable_template_assignments(bell_schedule_id);
"""


MIGRATIONS: dict[int, str] = {
    2: SCHEMA_V2,
}
