import { Link, useParams } from 'react-router-dom';
import VerificationNote from '../components/VerificationNote';
import { emptyMessage } from '../lib/academicsView';
import { readDepartments, readFaculty } from '../lib/offline';
import { useCachedRows } from '../lib/useCachedRows';

export default function FacultyDepartments() {
  const { facultyId = '' } = useParams();
  // Keyed by school, so moving to another school starts from loading, not the old list.
  return <SchoolDepartments key={facultyId} facultyId={facultyId} />;
}

function SchoolDepartments({ facultyId }: { facultyId: string }) {
  const { result, retry, progress } = useCachedRows(async () => ({
    faculty: await readFaculty(facultyId),
    departments: await readDepartments(facultyId),
  }));

  const back = (
    <p>
      <Link to="/academics" className="back-link">
        Back to schools
      </Link>
    </p>
  );

  if (result.state === 'loading') {
    return (
      <>
        {back}
        <h1>School</h1>
        <p role="status" className="muted">
          Loading departments…
        </p>
      </>
    );
  }

  if (result.state === 'error') {
    return (
      <>
        {back}
        <h1>School</h1>
        <div role="alert">
          <p>Could not read the saved departments on this device.</p>
          <button type="button" onClick={retry}>
            Try again
          </button>
        </div>
      </>
    );
  }

  const { faculty, departments } = result.value;
  if (!faculty) {
    return (
      <>
        {back}
        <h1>School</h1>
        <p className="muted" role="status">
          {emptyMessage(progress, 'This school is not saved on this device.')}
        </p>
      </>
    );
  }

  return (
    <>
      {back}
      <h1>{faculty.name}</h1>
      {faculty.short_name && <p className="muted">{faculty.short_name}</p>}
      <VerificationNote verification={faculty.verification} updatedAt={faculty.updated_at} />

      <h2>Departments</h2>
      {departments.length === 0 ? (
        <p className="muted" role="status">
          {emptyMessage(progress, 'No departments saved for this school yet')}
        </p>
      ) : (
        <ul className="items">
          {departments.map((department) => (
            <li key={department.id}>
              <strong>{department.name}</strong>
              {department.short_name && <span className="muted"> ({department.short_name})</span>}
              {department.hod_name && <p>Head of department: {department.hod_name}</p>}
              {department.office_location && <p>Office: {department.office_location}</p>}
              <VerificationNote
                verification={department.verification}
                updatedAt={department.updated_at}
              />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
