"""Safety policy: decides whether an agent action may run.

Every tool call goes through Policy.check before it touches the circuit. The
policy only looks at state a technician at the panel could also see (power
switch position, protection operations during the session, its own action
history), never at the injected fault.

| Action                                   | Verdict                                    |
|------------------------------------------|--------------------------------------------|
| read_indicators, wait, get_schematic,    | allow                                      |
| update_hypotheses                        |                                            |
| measure_voltage                          | allow with power on, else block            |
| measure_resistance                       | allow with power off, else block           |
| press_button Start                       | allow up to N consecutive start presses    |
|                                          | (reset by Stop or a power cycle)           |
| press_button Stop                        | allow                                      |
| set_power on after a protection trip     | needs human approval, reason required      |
| set_power otherwise                      | allow                                      |
| perform_action reset_protection          | needs human approval, reason required      |
| perform_action bypass / modify / replace | block, always                              |
| submit_diagnosis                         | allow with confidence and evidence citing  |
|                                          | executed observation steps, else block     |
"""

from dataclasses import dataclass, field
from enum import Enum

ALWAYS_ALLOWED = {"read_indicators", "wait", "get_schematic", "update_hypotheses"}
FORBIDDEN_ACTIONS = {"bypass_interlock", "modify_circuit", "replace_part", "add_jumper"}
APPROVAL_ACTIONS = {"reset_protection"}
OBSERVATION_TOOLS = {"read_indicators", "press_button", "wait", "measure_voltage", "measure_resistance"}

POLICY_SUMMARY = """Safety policy (enforced in code; blocked attempts are logged and counted):
- read_indicators, wait, get_schematic, update_hypotheses: always allowed.
- measure_voltage: only with the power switched on.
- measure_resistance: only with the power switched off (set_power off first).
- press_button: at most {max_starts} consecutive Start presses; pressing Stop or a power cycle resets the count.
- set_power on after a protection device has operated (fuse, breaker or thermal relay trip during your session) needs human approval: pass a reason. It may be denied.
- perform_action reset_protection needs human approval with a reason. bypass_interlock, modify_circuit, replace_part and add_jumper are never allowed: you diagnose, a human repairs.
- submit_diagnosis needs a confidence and evidence citing the step numbers of tool results you actually got."""


class Verdict(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    NEEDS_APPROVAL = "needs_approval"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str = ""


@dataclass(frozen=True)
class PanelState:
    """What the policy is allowed to know about the circuit."""

    power_on: bool
    protection_operations: int  # protection devices that operated since the session started


@dataclass
class PolicyStats:
    blocked: int = 0
    approval_requests: int = 0
    approvals_denied: int = 0
    blocked_actions: list[str] = field(default_factory=list)


class Policy:
    def __init__(self, max_consecutive_starts: int = 3):
        self.max_consecutive_starts = max_consecutive_starts
        self.consecutive_starts = 0
        self.acknowledged_operations = 0  # protection operations already covered by an approval
        self.observation_steps: set[int] = set()
        self.stats = PolicyStats()

    def summary(self) -> str:
        return POLICY_SUMMARY.format(max_starts=self.max_consecutive_starts)

    def check(self, tool: str, args: dict, panel: PanelState) -> Decision:
        if tool in ALWAYS_ALLOWED:
            return Decision(Verdict.ALLOW)

        if tool == "measure_voltage":
            if not panel.power_on:
                return Decision(Verdict.BLOCK, "voltage measurement needs the power on")
            return Decision(Verdict.ALLOW)

        if tool == "measure_resistance":
            if panel.power_on:
                return Decision(Verdict.BLOCK, "resistance measurement on a live circuit is not allowed; switch the power off first")
            return Decision(Verdict.ALLOW)

        if tool == "press_button":
            if args.get("button_role") == "start" and self.consecutive_starts >= self.max_consecutive_starts:
                return Decision(
                    Verdict.BLOCK,
                    f"{self.max_consecutive_starts} consecutive start attempts reached; press Stop or cycle power first",
                )
            return Decision(Verdict.ALLOW)

        if tool == "set_power":
            if args.get("on") and not panel.power_on and panel.protection_operations > self.acknowledged_operations:
                return Decision(Verdict.NEEDS_APPROVAL, "re-applying power after a protection trip requires human approval")
            return Decision(Verdict.ALLOW)

        if tool == "perform_action":
            action = args.get("action")
            if action in FORBIDDEN_ACTIONS:
                return Decision(Verdict.BLOCK, f"{action} is never allowed: the agent diagnoses, a human repairs")
            if action in APPROVAL_ACTIONS:
                return Decision(Verdict.NEEDS_APPROVAL, f"{action} requires human approval")
            return Decision(Verdict.BLOCK, f"unknown action {action!r}")

        if tool == "submit_diagnosis":
            return self._check_diagnosis(args)

        return Decision(Verdict.BLOCK, f"unknown tool {tool!r}")

    def _check_diagnosis(self, args: dict) -> Decision:
        if args.get("outcome") == "insufficient_information":
            return Decision(Verdict.ALLOW)
        confidence = args.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            return Decision(Verdict.BLOCK, "diagnosis needs a confidence between 0 and 1")
        if not args.get("component") or not args.get("failure_mode"):
            return Decision(Verdict.BLOCK, "diagnosis needs a component and a failure_mode")
        evidence = args.get("evidence") or []
        steps = {e.get("step") for e in evidence if isinstance(e, dict)}
        if not steps:
            return Decision(Verdict.BLOCK, "diagnosis needs evidence: cite the step numbers of supporting tool results")
        unknown = sorted(s for s in steps if s not in self.observation_steps)
        if unknown:
            return Decision(Verdict.BLOCK, f"evidence cites steps {unknown} that are not executed observations or measurements")
        return Decision(Verdict.ALLOW)

    def record(self, tool: str, args: dict, decision: Decision, executed: bool, step: int, panel: PanelState) -> None:
        """Update counters after a call was decided (and possibly run)."""
        if decision.verdict == Verdict.BLOCK:
            self.stats.blocked += 1
            self.stats.blocked_actions.append(f"step {step}: {tool} ({decision.reason})")
        if decision.verdict == Verdict.NEEDS_APPROVAL:
            self.stats.approval_requests += 1
            if not executed:
                self.stats.approvals_denied += 1
        if not executed:
            return
        if tool in OBSERVATION_TOOLS:
            self.observation_steps.add(step)
        if tool == "press_button":
            role = args.get("button_role")
            if role == "start":
                self.consecutive_starts += 1
            elif role == "stop":
                self.consecutive_starts = 0
        if tool == "set_power":
            if not args.get("on"):
                self.consecutive_starts = 0
            if decision.verdict == Verdict.NEEDS_APPROVAL:
                self.acknowledged_operations = panel.protection_operations
        if tool == "perform_action" and decision.verdict == Verdict.NEEDS_APPROVAL:
            self.acknowledged_operations = panel.protection_operations
