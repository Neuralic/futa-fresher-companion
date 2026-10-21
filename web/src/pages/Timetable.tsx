import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import type { Building, Course, TimetableEntry } from '../api/types';
import { levelHeading, liveRows, resolveDepartment, DEPARTMENT_NOT_FOUND } from '../lib/departmentView';
import { readTimetableScreen } from '../lib/offline';
import {
  browserLocalStorage,
  buildingsById,
  chooseLevel,
  COURSE_MISSING,
  courseText,
  entriesForLevel,
  groupByDay,
  isToday,
  LEVEL_EMPTY,
  levelsWithEntries,
  loadRememberedLevel,
  rememberLevel,
  TIMETABLE_EMPTY,
  timeRange,
  timetableEmptyMessage,
  venueText,
} from '../lib/timetableView';
import { useCachedRows } from '../lib/useCachedRows';

export default function Timetable() {
  const { facultyId = '', departmentId = '' } = useParams();
  // Keyed by department, so moving to another one starts from loading.
  return <TimetablePage key={departmentId} facultyId={facultyId} departmentId={departmentId} />;
}

// Reads only the offline cache. Everything shown is plain text.
function TimetablePage({ facultyId, departmentId }: { facultyId: string; departmentId: string }) {
  const { result, retry, progress } = useCachedRows(() => readTimetableScreen(departmentId));
  const [picked, setPicked] = useState<number | null>(() =>
    loadRememberedLevel(browserLocalStorage()),
  );
  // Fixed for this visit, so "today" does not change under the reader at midnight.
  const [now] = useState(() => new Date());

  if (result.state === 'loading') {
    return (
      <>
        <Back facultyId={facultyId} departmentId={departmentId} />
        <h1>Timetable</h1>
        <p role="status" className="muted">
          Loading timetable…
        </p>
      </>
    );
  }

  if (result.state === 'error') {
    return (
      <>
        <Back facultyId={facultyId} departmentId={departmentId} />
        <h1>Timetable</h1>
        <div role="alert">
          <p>Could not read the saved timetable on this device.</p>
          <button type="button" onClick={retry}>
            Try again
          </button>
        </div>
      </>
    );
  }

  const department = resolveDepartment(result.value.department, facultyId);
  if (!department) {
    return (
      <>
        <Link to={`/academics/${facultyId}`} className="back-link">
          Back to school
        </Link>
        <h1>Timetable</h1>
        <p className="muted" role="status">
          {timetableEmptyMessage(progress, DEPARTMENT_NOT_FOUND)}
        </p>
      </>
    );
  }

  return (
    <TimetableBody
      facultyId={facultyId}
      departmentId={departmentId}
      departmentName={department.name}
      value={result.value}
      picked={picked}
      onPick={(level) => {
        setPicked(level);
        rememberLevel(browserLocalStorage(), level);
      }}
      now={now}
      progress={progress}
    />
  );
}

function Back({ facultyId, departmentId }: { facultyId: string; departmentId: string }) {
  return (
    <p>
      <Link to={`/academics/${facultyId}/${departmentId}`} className="back-link">
        Back to department
      </Link>
    </p>
  );
}

function TimetableBody({
  facultyId,
  departmentId,
  departmentName,
  value,
  picked,
  onPick,
  now,
  progress,
}: {
  facultyId: string;
  departmentId: string;
  departmentName: string;
  value: { entries: TimetableEntry[]; courses: Course[]; buildings: Building[] };
  picked: number | null;
  onPick: (level: number) => void;
  now: Date;
  progress: { running: boolean; firstRun: boolean };
}) {
  const levels = levelsWithEntries(value.entries);
  const level = chooseLevel(levels, picked);
  const courses = useMemo(
    () => new Map(liveRows(value.courses).map((course) => [course.id, course])),
    [value.courses],
  );
  const buildings = useMemo(() => buildingsById(value.buildings), [value.buildings]);
  const groups = level === null ? [] : groupByDay(entriesForLevel(value.entries, level));

  return (
    <>
      <p>
        <Link to={`/academics/${facultyId}/${departmentId}`} className="back-link">
          Back to department
        </Link>
      </p>
      <h1>Timetable</h1>
      <p className="muted">{departmentName}</p>

      {levels.length === 0 ? (
        <p className="muted" role="status">
          {timetableEmptyMessage(progress, TIMETABLE_EMPTY)}
        </p>
      ) : (
        <>
          <label className="level-picker">
            Level{' '}
            <select
              value={level ?? ''}
              onChange={(event) => onPick(Number(event.target.value))}
            >
              {levels.map((option) => (
                <option key={option} value={option}>
                  {levelHeading(option)}
                </option>
              ))}
            </select>
          </label>

          {groups.length === 0 ? (
            <p className="muted" role="status">
              {timetableEmptyMessage(progress, LEVEL_EMPTY)}
            </p>
          ) : (
            groups.map((group) => (
              <section key={group.day} aria-labelledby={`day-${group.day}`}>
                <h2 id={`day-${group.day}`}>
                  {group.label}
                  {isToday(group, now) && <span className="today"> · Today</span>}
                </h2>
                <ul className="items">
                  {group.entries.map((entry) => {
                    const course = courseText(courses.get(entry.course_id));
                    return (
                      <li key={entry.id}>
                        {course ? (
                          <>
                            <strong>{course.code}</strong> {course.title}
                          </>
                        ) : (
                          <span className="muted">{COURSE_MISSING}</span>
                        )}
                        <p className="muted">
                          {timeRange(entry)} · Semester {entry.semester}
                        </p>
                        <p>{venueText(entry, buildings)}</p>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))
          )}
        </>
      )}
    </>
  );
}
