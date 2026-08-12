AutoEvalOps Development Guidelines
Golden Rule

Do not move to next phase until current phase is 100% complete and tested.
I'm using powerhsell terminal, so all commands must be given that can be pasted to powershell.

Phase Completion Gate (Must Pass All)
 Code compiles/runs without errors
 All tests pass (95%+ coverage)
 No console errors or warnings
 Feature works per phase spec
 Code reviewed (self-review minimum)
 No TODOs in production code
 No hardcoded secrets/localhost
Bug Containment

If Phase N breaks Phase N-1, stop immediately. Fix Phase N-1 first, re-test, then resume.

Module Isolation
Phase 1 → /backend/src/autoeval_ops/core/
Phase 2 → /backend/src/autoeval_ops/github/
Phase 3 → /backend/src/autoeval_ops/api/
Phase 4 → /dashboard/
Phase 5 → /backend/src/autoeval_ops/observability/

No cross-phase dependencies except via interfaces.

Commit Format
[PHASE N] Feature: X

- What changed
- Test coverage: Y%
- Breaking changes: NO
Self-Review Checklist
 Matches phase spec
 Tests added & passing
 No hardcoded values
 Clear error messages
 Documentation updated
When Stuck
Debug for 30 min (logs, prints, docs)
Document the problem exactly
Ask for help with full context
Don't hack around it—fix root cause
Quality > Speed

A working project is better than a fast broken one.