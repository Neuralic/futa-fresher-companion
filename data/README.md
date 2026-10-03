# Campus data collection

You are building the most valuable part of the app: **correct, sourced information.**
Fill the CSVs in `data/templates/` (copy them to `data/collected/<faculty>/` and work there).

## Rules
1. **One row = one fact. Every row needs `source`, `collected_by`, `date_collected`.**
   - `source`: where you got it. Examples: "department notice board", "HOD office", "faculty website", "told by class rep".
   - `date_collected`: `YYYY-MM-DD`.
2. **Never guess.** Leave the cell empty if you don't know.
3. **Use exact names.** `faculty_name` / `department_name` must match the spelling in `faculties.csv` / `departments.csv` exactly. Fill those two files first.
4. **Personal data (NDPR):**
   - Lecturers: official school email and office only. No personal phone numbers.
   - Class reps: only put a `contact` if they agreed. Set `consent_given` to `yes` or `no`. No consent = leave `contact` empty.
5. Save as **CSV UTF-8**. Don't rename or reorder columns. Don't add formatting or merged cells.
6. Do **one faculty at a time** and finish it before starting the next.

## Order
`faculties.csv` → `departments.csv` → `lecturers.csv`, `courses.csv`, `class_reps.csv` → `buildings.csv` → `timetable.csv`

## Column notes
| File | Column | Format / example |
|---|---|---|
| departments | `hod_name` | `Prof. A. B. Surname` |
| lecturers | `title` / `rank` | `Dr.` / `Senior Lecturer` |
| courses | `code` | `CSC 101` (as printed in the course list) |
| courses | `units`, `level`, `semester` | `3`, `100`, `1` (or `2`) |
| class_reps | `level` | `100`, `200`, … |
| buildings | `type` | one of: faculty, department, lecture_hall, hostel, admin, library, sports, food, health, worship, gate, other |
| buildings | `lat`, `lng` | decimals, e.g. `7.3011`, `5.1366` (stand at the entrance when recording) |
| timetable | `day_of_week` | `1` = Monday … `7` = Sunday |
| timetable | `start_time`, `end_time` | 24-hour `HH:MM`, e.g. `08:00` |
| timetable | `venue_name` | must match a `name` in `buildings.csv`, otherwise use `venue_note` |

An import script (CSV → database, with validation) will come next; keep your files clean so it just works.
