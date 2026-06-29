# Agent Cleanup and Idempotency

Every agent-created element should be traceable. For model/detail elements, set Comments to an agent namespace such as AGENT_LELAND_CURRENT, AGENT_TEMP, or AGENT_LOT8_CURRENT. For views, schedules, sheets, and text notes, use a strict AGENT_ or AI_ prefix in the name/text/comments.

Before recreating layout or retrying failed visual work, collect and remove only prior agent-tagged artifacts in the current target view/sheet/model scope. Do not delete user/project elements unless specifically identified and confirmed by RPS output and visual QAQC.

Use small idempotent cycles: identify target, clean only previous agent artifacts, create new work, refresh, export focused QC, report status.
