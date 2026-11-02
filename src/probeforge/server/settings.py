"""Server settings from the environment. PROBEFORGE_PUBLIC=1 switches on the public-demo behaviour (shorter approval
waits, visitor traces kept apart, the public spend ledger, low effort only, the token limit per call); the Origin
check, the session token and message validation are on in every mode."""

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


PUBLIC = os.environ.get("PROBEFORGE_PUBLIC") == "1"
APPROVAL_TIMEOUT_S = _int("PROBEFORGE_APPROVAL_TIMEOUT_S", 120 if PUBLIC else 600)  # a pending approval card
IDLE_TIMEOUT_S = _int("PROBEFORGE_IDLE_TIMEOUT_S", 600)  # a connection with no message for this long is closed
MAX_CONNECTIONS = _int("PROBEFORGE_MAX_CONNECTIONS", 40)  # browser tabs connected at once, over all visitors
MAX_PER_IP = _int("PROBEFORGE_MAX_PER_IP", 2 if PUBLIC else 10)
# tool calls (Engineer mode, intervention, suggestions): two at most per connection, so this bounds them
TOOL_WORKERS = _int("PROBEFORGE_TOOL_WORKERS", 2 * MAX_CONNECTIONS + 8)
JOB_WORKERS = _int("PROBEFORGE_JOB_WORKERS", 3 if PUBLIC else 4)  # agent, hybrid and Compare runs at once


def agent_effort(requested) -> str:
    """The reasoning effort of a paid agent run, chosen by the server, not the browser (audit S3): the budget rule
    allows low or below; public mode allows low only. Anything else becomes low."""
    allowed = ("low",) if PUBLIC else ("low", "minimal")
    return requested if requested in allowed else "low"


def spend_message(e: Exception) -> str:
    """What a visitor reads when the spend guard refuses a paid run. Engineer mode makes no model calls (no ledger
    check, suggestions come from the planner), so it still works when the budget is used up. Private servers keep
    the ledger's own message."""
    msg = str(e)
    if not PUBLIC:
        return msg
    if "daily cap" in msg:
        return ("Today's model budget for the public demo is used up, so Agent and Hybrid runs are paused until "
                "tomorrow. Engineer mode still works: it makes no model calls.")
    if "demo runs are stopped" in msg:
        return ("The public demo's model budget is used up, so Agent and Hybrid runs are paused. Engineer mode still "
                "works: it makes no model calls.")
    return msg
