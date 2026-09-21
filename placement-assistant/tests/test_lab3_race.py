"""Lab 3 — two runs booking the same slot; one wins cleanly."""
import threading

from app.memory import RunStore
from app.placement_db import PlacementDb
from app.providers import ModelTurn, PositionalMock, ToolCall
from app.worker import Worker


def test_two_workers_two_runs_one_slot(db_files):
    agent_path, place_path = db_files
    store1, store2 = RunStore(agent_path), RunStore(agent_path)
    placement1, placement2 = PlacementDb(place_path), PlacementDb(place_path)

    t1 = store1.create_thread("22IT017")
    t2 = store2.create_thread("22CS045")

    run_id1 = store1.enqueue(t1, "Apply TCS and book slot 3", "mock")
    run_id2 = store2.enqueue(t2, "Apply TCS and book slot 3", "mock")

    mock1 = PositionalMock([
        ModelTurn(text=None, tool_calls=[ToolCall("apply_to_drive", {"student_id": "22IT017", "drive_id": 2})]),
        ModelTurn(text=None, tool_calls=[ToolCall("book_interview_slot", {"student_id": "22IT017", "slot_id": 3})]),
        ModelTurn(text="Finished 22IT017"),
    ])
    mock2 = PositionalMock([
        ModelTurn(text=None, tool_calls=[ToolCall("apply_to_drive", {"student_id": "22CS045", "drive_id": 2})]),
        ModelTurn(text=None, tool_calls=[ToolCall("book_interview_slot", {"student_id": "22CS045", "slot_id": 3})]),
        ModelTurn(text="Finished 22CS045"),
    ])

    w1 = Worker(store1, placement1, mock1, worker_id="w1")
    w2 = Worker(store2, placement2, mock2, worker_id="w2")

    w1.run_once()
    w2.run_once()

    r1 = store1.get_run(run_id1)
    r2 = store1.get_run(run_id2)

    assert r1["status"] == "succeeded"
    assert r2["status"] == "succeeded"

    step_booking1 = next(s["result"] for s in r1["steps"] if s["kind"] == "tool" and s["tool_name"] == "book_interview_slot")
    step_booking2 = next(s["result"] for s in r2["steps"] if s["kind"] == "tool" and s["tool_name"] == "book_interview_slot")

    outcomes = [step_booking1.get("status") or step_booking1.get("error"),
                step_booking2.get("status") or step_booking2.get("error")]
    assert sorted(outcomes) == ["booked", "slot_taken"]

    slot3 = placement1.get_slot(3)
    assert slot3.student_id is not None
    assert slot3.student_id in (1, 2)


def test_truly_concurrent_claims_have_one_winner(tmp_path):
    place_path = str(tmp_path / "placement.db")
    p = PlacementDb(place_path)
    p.migrate()
    p.create_application(1, 2)
    p.create_application(2, 2)

    v0 = p.slot_version(3)
    barrier = threading.Barrier(8)
    results = [None] * 8

    def worker_claim(idx):
        conn = PlacementDb(place_path)
        student_id = 1 if idx % 2 == 0 else 2
        barrier.wait()
        results[idx] = conn.claim_slot(3, student_id, v0)

    threads = [threading.Thread(target=worker_claim, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1
    assert results.count(False) == 7
    assert p.slot_version(3) == v0 + 1
