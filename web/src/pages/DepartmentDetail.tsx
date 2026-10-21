import { Link, useParams } from 'react-router-dom';
import VerificationNote from '../components/VerificationNote';
import {
  COURSES_EMPTY,
  DEPARTMENT_NOT_FOUND,
  groupCoursesByLevel,
  LECTURERS_EMPTY,
  lecturerDisplayName,
  levelHeading,
  resolveDepartment,
  sectionEmptyMessage,
  sortLecturers,
  unitsText,
} from '../lib/departmentView';
import { readDepartmentScreen } from '../lib/offline';
import { useCachedRows } from '../lib/useCachedRows';

export default function DepartmentDetail() {
  const { facultyId = '', departmentId = '' } = useParams();
  // Keyed by department, so moving to another one starts from loading.
  return <DepartmentPage key={departmentId} facultyId={facultyId} departmentId={departmentId} />;
}

function DepartmentPage({ facultyId, departmentId }: { facultyId: string; departmentId: string }) {
  const { result, retry, progress } = useCachedRows(() => readDepartmentScreen(departmentId));

  const back = (
    <p>
      <Link to={`/academics/${facultyId}`} className="back-link">
        Back to school
      </Link>
    </p>
  );

  if (result.state === 'loading') {
    return (
      <>
        {back}
        <h1>Department</h1>
        <p role="status" className="muted">
          Loading department…
        </p>
      </>
    );
  }

  if (result.state === 'error') {
    return (
      <>
        {back}
        <h1>Department</h1>
        <div role="alert">
          <p>Could not read this department on this device.</p>
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
        {back}
        <h1>Department</h1>
        <p className="muted" role="status">
          {sectionEmptyMessage(progress, DEPARTMENT_NOT_FOUND)}
        </p>
      </>
    );
  }

  const levels = groupCoursesByLevel(result.value.courses);
  const lecturers = sortLecturers(result.value.lecturers);

  return (
    <>
      {back}
      <h1>{department.name}</h1>
      {department.short_name && <p className="muted">{department.short_name}</p>}
      <dl className="facts">
        {department.hod_name && (
          <>
            <dt>Head of department</dt>
            <dd>{department.hod_name}</dd>
          </>
        )}
        {department.office_location && (
          <>
            <dt>Office</dt>
            <dd>{department.office_location}</dd>
          </>
        )}
      </dl>
      <VerificationNote verification={department.verification} updatedAt={department.updated_at} />
      <p>
        <Link to={`/academics/${facultyId}/${departmentId}/timetable`}>Timetable</Link>
      </p>

      <section aria-labelledby="courses-heading">
        <h2 id="courses-heading">Courses</h2>
        {levels.length === 0 ? (
          <p className="muted" role="status">
            {sectionEmptyMessage(progress, COURSES_EMPTY)}
          </p>
        ) : (
          levels.map((group) => (
            <section key={group.level} aria-labelledby={`level-${group.level}`}>
              <h3 id={`level-${group.level}`}>{levelHeading(group.level)}</h3>
              <ul className="items">
                {group.courses.map((course) => (
                  <li key={course.id}>
                    <strong>{course.code}</strong> {course.title}
                    <p className="muted">
                      {unitsText(course.units)} · Semester {course.semester}
                    </p>
                    <VerificationNote
                      verification={course.verification}
                      updatedAt={course.updated_at}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </section>

      <section aria-labelledby="lecturers-heading">
        <h2 id="lecturers-heading">Lecturers</h2>
        {lecturers.length === 0 ? (
          <p className="muted" role="status">
            {sectionEmptyMessage(progress, LECTURERS_EMPTY)}
          </p>
        ) : (
          <ul className="items">
            {lecturers.map((lecturer) => (
              <li key={lecturer.id}>
                <strong>{lecturerDisplayName(lecturer)}</strong>
                {lecturer.rank && <p className="muted">{lecturer.rank}</p>}
                {lecturer.office_location && <p>Office: {lecturer.office_location}</p>}
                {lecturer.email && <p>Email: {lecturer.email}</p>}
                <VerificationNote
                  verification={lecturer.verification}
                  updatedAt={lecturer.updated_at}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
