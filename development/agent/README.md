# Agent contracts

This directory contains stable contracts for the role-aware Canvas AI agent.
It does not contain prompts, credentials, deployment configuration, or progress
logs.

Read in this order for an agent implementation batch:

1. the active spec;
2. `API_CONTRACT.md`;
3. the relevant rows in `TOOL_CATALOG.md`;
4. ADR-0001 through ADR-0003;
5. only the relevant security, Canvas, design, or evaluation document.

Runtime code remains in `backend/app/` and `frontend/`. These documents define
boundaries; they do not replace executable schemas, authorization, or tests.
