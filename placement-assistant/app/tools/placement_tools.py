import operator
from datetime import datetime, timezone

from app.domain import AlreadyApplied, Rule, Student
from app.data import InMemoryPlacementRepo
from app.tools.dispatch import dispatch

OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "in": lambda actual, allowed: actual in allowed.split(","),
}


def _passes(rule: Rule, student_value) -> bool:
    return OPS[rule.op](student_value, rule.typed_value())


def _unknown_student(roll_no: str) -> dict:
    return {"error": "unknown_student",
            "hint": f"No student with roll number {roll_no!r}. Ask the user for their roll number, e.g. 22CS045."}


def _unknown_drive(drive_id: int) -> dict:
    return {"error": "unknown_drive",
            "hint": f"No drive with id {drive_id}. Call list_open_drives to get valid ids."}


class PlacementTools:
    """Every method named in TOOL_NAMES is exposed to the model. Its docstring IS the prompt.

    Two tools are complete samples: check_eligibility (read-only) and apply_to_drive (side effect).
    Copy their patterns for the tools marked TODO.
    """

    READ_ONLY = ("list_open_drives", "get_student", "check_eligibility", "list_my_applications")
    SIDE_EFFECTS = ("apply_to_drive", "book_interview_slot", "notify_student")
    TOOL_NAMES = READ_ONLY + SIDE_EFFECTS

    def __init__(self, repo: InMemoryPlacementRepo, notifier, clock=lambda: datetime.now(timezone.utc)):
        self.repo = repo
        self.notifier = notifier
        self.clock = clock

    def functions(self) -> dict:
        return {name: getattr(self, name) for name in self.TOOL_NAMES}

    def call(self, name: str, args: dict) -> dict:
        return dispatch(self.functions(), name, args)

    # ================================================================== SAMPLE 1 (given): read-only

    def _evaluate(self, s: Student, drive_id: int) -> list[dict]:
        # The business rule lives in data (placement.eligibility_rule), not in the prompt or an if.
        failed = []
        for rule in self.repo.rules_for_drive(drive_id):
            actual = getattr(s, rule.field)
            if not _passes(rule, actual):
                failed.append({"rule_id": rule.id, "rule": str(rule), "actual": actual})
        return failed

    def check_eligibility(self, student_id: str, drive_id: int) -> dict:
        """Decide whether ONE student may apply to ONE drive, using the drive's eligibility rules.

        Use before apply_to_drive, or when the user asks "can I apply", "am I eligible for
        <company>", or "why can't I apply". Do NOT use to find drives; use list_open_drives.
        Read-only: changes nothing.

        Args:
            student_id: Roll number, e.g. "22CS045".
            drive_id: Integer id returned by list_open_drives. Never a company name.

        Returns:
            {"student_id", "drive_id", "eligible", "failed_rules": [{"rule_id", "rule", "actual"}]}.
            Explain every failed rule to the user; do not invent rules that are not listed.
        """
        # Failures are returned, never raised: a stable code plus a hint telling the model what to do next.
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        if self.repo.get_drive(drive_id) is None:
            return _unknown_drive(drive_id)
        # Every failed rule, not just the first: the model explains the verdict, it never decides it.
        failed = self._evaluate(s, drive_id)
        return {"student_id": s.roll_no, "drive_id": drive_id,
                "eligible": not failed, "failed_rules": failed}

    # ================================================================== SAMPLE 2 (given): side effect

    def apply_to_drive(self, student_id: str, drive_id: int) -> dict:
        """Submit a placement application for ONE student to ONE drive.

        Side effect: creates an application record the placement cell will act on. Call it only
        when the user clearly asks to apply or register ("apply me", "sign me up"), never to
        check or explore. Eligibility is re-checked here, but call check_eligibility first so
        you can explain the result.

        Args:
            student_id: Roll number, e.g. "22CS045".
            drive_id: Integer id returned by list_open_drives.

        Returns:
            {"application_id", "student_id", "drive_id", "status": "applied",
             "available_slots": [{"slot_id", "starts_at"}]}. Offer the slots to the user;
            book one only when they choose.
        """
        # Side effects check in a fixed order and stop at the first failure.
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        d = self.repo.get_drive(drive_id)
        if d is None:
            return _unknown_drive(drive_id)
        if d.status != "open" or d.deadline <= self.clock():
            return {"error": "drive_closed",
                    "hint": f"{d.company} is not accepting applications. Call list_open_drives for open ones."}
        # Re-check even though the description says "call check_eligibility first".
        # An instruction asks; code enforces. The model may have skipped it.
        failed = self._evaluate(s, drive_id)
        if failed:
            return {"error": "not_eligible", "failed_rules": failed,
                    "hint": "Explain the failed rules to the user. Do not retry."}
        try:
            application_id = self.repo.create_application(s.id, drive_id)
        except AlreadyApplied:
            return {"error": "already_applied",
                    "hint": "The student has already applied to this drive. Tell the user; do not retry."}
        # Return what the next step needs: the model will want to offer interview slots.
        slots = self.repo.free_slots(drive_id)
        return {"application_id": application_id, "student_id": s.roll_no, "drive_id": drive_id,
                "status": "applied",
                "available_slots": [{"slot_id": sl.id, "starts_at": sl.starts_at.isoformat()} for sl in slots]}

    # ================================================================== YOUR TOOLS

    # TODO 1 — get_student (5 min)
    def get_student(self, student_id: str) -> dict:
        """Retrieve academic profile and registration details for ONE student by roll number.

        Use when the user asks about a student's branch, CGPA, graduation year,
        or current number of backlogs, or to check student profile info before applying.
        Do NOT use to search for available job drives or to apply to drives.
        Read-only: changes nothing.

        Args:
            student_id: The student roll number, for example "22CS045".

        Returns:
            {"student_id", "name", "branch", "cgpa", "backlogs", "grad_year"} or
            an unknown_student error object if the roll number is not found.
        """
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        return {
            "student_id": s.roll_no,
            "name": s.name,
            "branch": s.branch,
            "cgpa": s.cgpa,
            "backlogs": s.backlogs,
            "grad_year": s.grad_year,
        }

    # TODO 2 — list_open_drives (10 min)
    def list_open_drives(self, branch: str | None = None, grad_year: int | None = None) -> dict:
        """List active and open campus placement drives sorted with soonest deadline first.

        Use when the user asks what drives are currently open, which companies are hiring,
        or wants to see upcoming application deadlines. Optionally filters by branch
        and graduation year eligibility rules. Do NOT use to check an individual student's
        eligibility across all rules; call check_eligibility for that.
        Read-only: changes nothing.

        Args:
            branch: Optional branch name filter (e.g. "CSE", "MECH"). Drives whose branch rule excludes this branch are omitted.
            grad_year: Optional graduation year filter (e.g. 2026). Drives whose grad_year rule excludes this year are omitted.

        Returns:
            {"drives": [{"drive_id", "company", "role", "ctc_lpa", "deadline"}]} where deadline is in YYYY-MM-DD format.
        """
        drives = self.repo.list_open_drives(self.clock())
        filtered = []
        for d in drives:
            rules = self.repo.rules_for_drive(d.id)
            if branch is not None:
                branch_rules = [r for r in rules if r.field == "branch"]
                if branch_rules and not all(_passes(r, branch) for r in branch_rules):
                    continue
            if grad_year is not None:
                grad_rules = [r for r in rules if r.field == "grad_year"]
                if grad_rules and not all(_passes(r, grad_year) for r in grad_rules):
                    continue
            filtered.append({
                "drive_id": d.id,
                "company": d.company,
                "role": d.role,
                "ctc_lpa": d.ctc_lpa,
                "deadline": d.deadline.strftime("%Y-%m-%d"),
            })
        return {"drives": filtered}

    # TODO 3 — book_interview_slot (15 min)
    def book_interview_slot(self, student_id: str, slot_id: int) -> dict:
        """Reserve a confirmed interview time slot for an applied student.

        Side effect: claims an available interview slot in the placement system.
        Call this only after the student has submitted an application for the drive
        and has chosen a specific slot_id from the offered interview slots.
        Do NOT call this to apply to a drive or to browse open drives.

        Args:
            student_id: The student roll number, for example "22CS045".
            slot_id: The integer slot identifier to be reserved.

        Returns:
            {"slot_id", "drive_id", "starts_at", "status": "booked"} on success,
            or an error dict indicating unknown_slot, no_application, or slot_taken.
        """
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        slot = self.repo.get_slot(slot_id)
        if slot is None:
            return {"error": "unknown_slot", "hint": f"No slot with id {slot_id}. Check available slots."}
        if not self.repo.has_application(s.id, slot.drive_id):
            return {"error": "no_application", "hint": "The student has not applied to this drive. Call apply_to_drive first."}
        if not self.repo.claim_slot(slot.id, s.id):
            slots = self.repo.free_slots(slot.drive_id)
            return {
                "error": "slot_taken",
                "available_slots": [{"slot_id": sl.id, "starts_at": sl.starts_at.isoformat()} for sl in slots],
                "hint": "This interview slot was already booked. Offer one of the remaining available slots to the user.",
            }
        return {
            "slot_id": slot.id,
            "drive_id": slot.drive_id,
            "starts_at": slot.starts_at.isoformat(),
            "status": "booked",
        }

    # TODO 4 (lab 1) — notify_student
    def notify_student(self, student_id: str, message: str) -> dict:
        """Queue and send an official SMS notification or reminder to ONE registered student.

        Side effect: enqueues an outbound SMS message in the placement notification system.
        Call this only when the user explicitly requests to send a message, alert, or notice
        to a student. Do NOT call this for general queries, status checks, or profile lookups.

        Args:
            student_id: The student roll number, for example "22CS045".
            message: The message body text to send (must not be empty, max 160 characters).

        Returns:
            {"notification_id", "status": "queued"} or an error dict if validation fails.
        """
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        if not message or len(message) > 160:
            return {"error": "invalid_message", "hint": "Message must be non-empty and at most 160 characters."}
        notification_id = self.notifier.send(student_id, message)
        return {"notification_id": notification_id, "status": "queued"}

    # STRETCH — design a tool of your own: list_my_applications(student_id)
    def list_my_applications(self, student_id: str) -> dict:
        """List all campus placement applications submitted by ONE student, ordered oldest first.

        Use when the student asks "where have I applied", "show my applications",
        "when is my interview", or to check the status of previously submitted applications.
        Do NOT use to browse open drives or apply to drives.
        Read-only: changes nothing.

        Args:
            student_id: The student roll number, for example "22CS045".

        Returns:
            {"applications": [{"application_id", "drive_id", "company", "role", "status", "applied_on", "interview_at"}]}
        """
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        apps = self.repo.list_applications(s.id)
        result = []
        for a in apps:
            result.append({
                "application_id": a["application_id"],
                "drive_id": a["drive_id"],
                "company": a["company"],
                "role": a["role"],
                "status": a["status"],
                "applied_on": a["created_at"].strftime("%Y-%m-%d") if isinstance(a["created_at"], datetime) else str(a["created_at"]),
                "interview_at": a["interview_at"].isoformat() if a["interview_at"] else None,
            })
        return {"applications": result}
