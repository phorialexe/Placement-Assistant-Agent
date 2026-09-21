import time  # noqa: F401  (you will time each tool call)
from collections.abc import Callable

from app.memory import ConversationStore
from app.providers import AgentError  # noqa: F401
from app.tools.placement_tools import PlacementTools

MAX_STEPS = 8

SYSTEM = """You are the Placement Assistant for an engineering college's placement cell.
You are talking to the student with roll number {student_id}. Act only for this student.
Use the tools for every fact about drives, eligibility, applications and slots; never guess.
Eligibility is decided by check_eligibility, not by you. Keep replies short and concrete."""


class Agent:
    """A small agent: one student, one conversation, the placement tools."""

    def __init__(self, provider, tools: PlacementTools, student_id: str,
                 memory: ConversationStore | None = None, thread_id: str | None = None,
                 on_step: Callable[[dict], None] | None = None):
        self.provider = provider
        self.tools = tools
        self.system = SYSTEM.format(student_id=student_id)
        self.memory = memory
        self.thread_id = thread_id
        self.on_step = on_step
        self.contents: list[dict] = []     # what the model sees, turn after turn
        self.trace: list[dict] = []        # what happened, step by step
        if self.memory and self.thread_id:
            for m in self.memory.load_history(self.thread_id):
                self.contents.append({"role": m["role"], "text": m["text"]})

    def _log(self, entry: dict) -> None:
        """Add one entry to the trace and tell on_step about it. (Given.)"""
        self.trace.append(entry)
        if self.on_step:
            self.on_step(entry)

    # ------------------------------------------------------------------ Part 2.1

    def run_tool(self, name: str, args: dict) -> dict:
        """Call one tool with self.tools.call(name, args). Never raise.

        A crash becomes information the model can act on: that is self-healing.
        """
        try:
            return self.tools.call(name, args)
        except NotImplementedError:
            return {"error": "not_implemented", "hint": f"The tool {name!r} is not implemented yet."}
        except Exception as exc:
            return {"error": "tool_failed", "hint": f"Tool {name!r} failed: {exc}"}

    # ------------------------------------------------------------------ Part 2.2

    def ask(self, text: str) -> str:
        """One user turn: loop model calls and tool calls until the model answers."""
        self.contents.append({"role": "user", "text": text})
        run_id = None
        if self.memory and self.thread_id:
            self.memory.append_message(self.thread_id, "user", text)
            model_name = getattr(self.provider, "model", "unknown")
            run_id = self.memory.start_run(self.thread_id, model_name)

        step = 0
        try:
            while True:
                step += 1
                if step > MAX_STEPS:
                    raise AgentError("step_limit", f"Exceeded {MAX_STEPS} steps without reaching an answer.")

                turn = self.provider.generate(self.system, self.contents, list(self.tools.functions().values()))
                self._log({
                    "step": step,
                    "kind": "model",
                    "tokens_in": turn.tokens_in,
                    "tokens_out": turn.tokens_out,
                })
                if self.memory and run_id:
                    self.memory.record_model_step(run_id, step, turn.tokens_in, turn.tokens_out)

                if not turn.tool_calls:
                    reply = turn.text or ""
                    self.contents.append({"role": "model", "text": reply, "raw": turn.raw})
                    if self.memory and self.thread_id:
                        self.memory.append_message(self.thread_id, "model", reply)
                    if self.memory and run_id:
                        self.memory.finish_run(run_id, "succeeded")
                    return reply

                self.contents.append({
                    "role": "model",
                    "text": turn.text,
                    "raw": turn.raw,
                    "tool_calls": [{"name": tc.name, "args": tc.args} for tc in turn.tool_calls],
                })

                for tc in turn.tool_calls:
                    step += 1
                    if step > MAX_STEPS:
                        raise AgentError("step_limit", f"Exceeded {MAX_STEPS} steps without reaching an answer.")

                    t0 = time.perf_counter()
                    result = self.run_tool(tc.name, tc.args)
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    ok = "error" not in result

                    self._log({
                        "step": step,
                        "kind": "tool",
                        "tool": tc.name,
                        "args": tc.args,
                        "result": result,
                        "ok": ok,
                        "ms": latency_ms,
                    })
                    if self.memory and run_id:
                        self.memory.record_tool_call(run_id, step, tc.name, tc.args, result, ok, latency_ms)

                    self.contents.append({"role": "tool", "name": tc.name, "result": result})

        except AgentError as e:
            if self.memory and run_id:
                self.memory.finish_run(run_id, "failed", e.code)
            raise
        except BaseException as exc:
            if self.memory and run_id:
                self.memory.finish_run(run_id, "failed", type(exc).__name__)
            raise
