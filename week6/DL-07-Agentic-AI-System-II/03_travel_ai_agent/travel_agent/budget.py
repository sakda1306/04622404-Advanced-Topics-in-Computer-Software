from dataclasses import dataclass


class AgentError(Exception):
    """Ends a run without a result. `code` is sent to Module 02 (docs/02_api_spec.md 9.3)."""

    def __init__(self, code: str, message: str, http_status: int) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.http_status = http_status


def budget_exceeded(message: str) -> AgentError:
    return AgentError("BUDGET_EXCEEDED", message, 504)


@dataclass
class Budget:
    """Step and tool-call limits for one run. Time is enforced separately by the deadline."""

    max_steps: int
    max_tool_calls: int
    steps: int = 0
    tool_calls: int = 0

    def step(self) -> None:
        if self.steps >= self.max_steps:
            raise budget_exceeded(f"step limit {self.max_steps} reached")
        self.steps += 1

    def reserve_tool_calls(self, count: int = 1) -> None:
        if self.tool_calls + count > self.max_tool_calls:
            raise budget_exceeded(f"tool-call limit {self.max_tool_calls} reached")
        self.tool_calls += count
