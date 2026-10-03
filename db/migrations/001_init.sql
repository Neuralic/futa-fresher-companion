-- 001_init: core schema for FUTA Fresher Companion (v1).
-- RULE: never edit this file after it has been merged. Add 002_*.sql instead.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TYPE user_role AS ENUM
  ('student', 'class_rep', 'department_admin', 'faculty_admin', 'sug', 'super_admin');
CREATE TYPE verification_status AS ENUM ('unverified', 'verified', 'outdated');
CREATE TYPE building_type AS ENUM
  ('faculty', 'department', 'lecture_hall', 'hostel', 'admin', 'library',
   'sports', 'food', 'health', 'worship', 'gate', 'other');
CREATE TYPE announcement_scope AS ENUM ('university', 'sug', 'faculty', 'department');

CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------- users
CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name     text NOT NULL,
  email         text NOT NULL,
  password_hash text NOT NULL,
  matric_no     text,
  role          user_role NOT NULL DEFAULT 'student',
  faculty_id    uuid,          -- FK added below (scope for faculty_admin)
  department_id uuid,          -- FK added below (student's dept / scope for department_admin)
  level         smallint CHECK (level IS NULL OR level BETWEEN 100 AND 700),
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_users_email ON users (lower(email));
CREATE UNIQUE INDEX uq_users_matric_no ON users (matric_no) WHERE matric_no IS NOT NULL;

-- ------------------------------------------------------------ faculties
CREATE TABLE faculties (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name                text NOT NULL UNIQUE,
  short_name          text,
  verification_status verification_status NOT NULL DEFAULT 'unverified',
  source              text,
  verified_by         uuid REFERENCES users (id),
  verified_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz
);

-- ---------------------------------------------------------- departments
CREATE TABLE departments (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  faculty_id          uuid NOT NULL REFERENCES faculties (id),
  name                text NOT NULL,
  short_name          text,
  hod_name            text,
  office_location     text,
  verification_status verification_status NOT NULL DEFAULT 'unverified',
  source              text,
  verified_by         uuid REFERENCES users (id),
  verified_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz,
  UNIQUE (faculty_id, name)
);
CREATE INDEX idx_departments_faculty ON departments (faculty_id);

ALTER TABLE users
  ADD CONSTRAINT fk_users_faculty FOREIGN KEY (faculty_id) REFERENCES faculties (id),
  ADD CONSTRAINT fk_users_department FOREIGN KEY (department_id) REFERENCES departments (id);

-- ------------------------------------------------------------ lecturers
CREATE TABLE lecturers (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id       uuid NOT NULL REFERENCES departments (id),
  full_name           text NOT NULL,
  title               text,
  rank                text,
  email               text,          -- official school email only
  office_location     text,
  specialization      text,
  verification_status verification_status NOT NULL DEFAULT 'unverified',
  source              text,
  verified_by         uuid REFERENCES users (id),
  verified_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz
);
CREATE INDEX idx_lecturers_department ON lecturers (department_id);
CREATE INDEX idx_lecturers_name_trgm ON lecturers USING gin (full_name gin_trgm_ops);

-- -------------------------------------------------------------- courses
CREATE TABLE courses (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id       uuid NOT NULL REFERENCES departments (id),
  code                text NOT NULL,
  title               text NOT NULL,
  units               smallint NOT NULL CHECK (units BETWEEN 0 AND 12),
  level               smallint NOT NULL CHECK (level BETWEEN 100 AND 700),
  semester            smallint NOT NULL CHECK (semester IN (1, 2)),
  verification_status verification_status NOT NULL DEFAULT 'unverified',
  source              text,
  verified_by         uuid REFERENCES users (id),
  verified_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz,
  UNIQUE (department_id, code)
);

-- ----------------------------------------------------------- class_reps
CREATE TABLE class_reps (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id       uuid NOT NULL REFERENCES departments (id),
  level               smallint NOT NULL CHECK (level BETWEEN 100 AND 700),
  full_name           text NOT NULL,
  contact             text,
  consent_given       boolean NOT NULL DEFAULT false,  -- NDPR: contact is exposed only if true
  verification_status verification_status NOT NULL DEFAULT 'unverified',
  source              text,
  verified_by         uuid REFERENCES users (id),
  verified_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz
);
CREATE INDEX idx_class_reps_department ON class_reps (department_id, level);

-- ------------------------------------------------------------ buildings
CREATE TABLE buildings (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name                text NOT NULL,
  type                building_type NOT NULL DEFAULT 'other',
  description         text,
  location            geography(Point, 4326) NOT NULL,   -- lng/lat (WGS84)
  verification_status verification_status NOT NULL DEFAULT 'unverified',
  source              text,
  verified_by         uuid REFERENCES users (id),
  verified_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz
);
CREATE INDEX idx_buildings_location ON buildings USING gist (location);
CREATE INDEX idx_buildings_name_trgm ON buildings USING gin (name gin_trgm_ops);

-- ---------------------------------------------------------------- paths
-- Campus footpaths/roads for routing (owned by Maps/GIS; pgRouting comes later).
CREATE TABLE paths (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text,
  kind       text NOT NULL DEFAULT 'footpath',  -- footpath | road | stairs | ...
  geom       geography(LineString, 4326) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_paths_geom ON paths USING gist (geom);

-- ---------------------------------------------------- timetable_entries
CREATE TABLE timetable_entries (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id       uuid NOT NULL REFERENCES departments (id),
  level               smallint NOT NULL CHECK (level BETWEEN 100 AND 700),
  semester            smallint NOT NULL CHECK (semester IN (1, 2)),
  course_id           uuid NOT NULL REFERENCES courses (id),
  day_of_week         smallint NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
  start_time          time NOT NULL,
  end_time            time NOT NULL,
  venue_building_id   uuid REFERENCES buildings (id),
  venue_note          text,
  verification_status verification_status NOT NULL DEFAULT 'unverified',
  source              text,
  verified_by         uuid REFERENCES users (id),
  verified_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz,
  CHECK (end_time > start_time)
);
CREATE INDEX idx_timetable_lookup ON timetable_entries (department_id, level, semester);

-- -------------------------------------------------------- announcements
CREATE TABLE announcements (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title               text NOT NULL,
  body                text NOT NULL,
  scope               announcement_scope NOT NULL,
  faculty_id          uuid REFERENCES faculties (id),
  department_id       uuid REFERENCES departments (id),
  author_id           uuid NOT NULL REFERENCES users (id),
  published_at        timestamptz NOT NULL DEFAULT now(),
  expires_at          timestamptz,
  verification_status verification_status NOT NULL DEFAULT 'unverified',
  source              text,
  verified_by         uuid REFERENCES users (id),
  verified_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz,
  CHECK (scope <> 'faculty' OR faculty_id IS NOT NULL),
  CHECK (scope <> 'department' OR department_id IS NOT NULL)
);
CREATE INDEX idx_announcements_published ON announcements (published_at DESC);
CREATE INDEX idx_announcements_scope ON announcements (scope, faculty_id, department_id);

-- ----------------------------------------- updated_at triggers + sync index
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'users', 'faculties', 'departments', 'lecturers', 'courses', 'class_reps',
    'buildings', 'paths', 'timetable_entries', 'announcements'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I
         FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t);
    EXECUTE format('CREATE INDEX idx_%1$s_updated_at ON %1$I (updated_at)', t);
  END LOOP;
END $$;
