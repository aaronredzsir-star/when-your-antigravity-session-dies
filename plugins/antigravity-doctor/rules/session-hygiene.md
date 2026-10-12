---
trigger: always_on
---

# Session Trajectory & Context Hygiene

To prevent ephemeral prompt cache expiration, monolithic prefill delays, and gateway connection timeouts:
1. **Targeted Inspections**: When viewing files or inspecting repositories, specify concise line ranges (`StartLine` and `EndLine`) instead of reading massive entire files when only localized context is needed.
2. **Output Discipline**: Limit verbose shell commands or build logs to necessary head/tail excerpts.
3. **Context Preservation**: Avoid repeating raw multi-thousand-line payloads across multi-turn exchanges.
