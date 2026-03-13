# Scope-Down Justification

Official task `task_07d7ff58` describes a very broad multi-component backend product surface.  
This environment intentionally evaluates the same core capability through a representative
subset that is still hard and implementation-heavy:

- ORM/client wiring and runtime integration under Prisma/PostgreSQL
- multi-family tenancy and access isolation
- auth + seeded multi-family data consistency
- family-scoped API coherence across tasks/events/feed/lists/reminders
- write-path implementation across tasks/events/feed/lists/reminders with persistence checks
- social metadata integrity (like/comment aggregates)

## Why this scope was narrowed

End-to-end verification must remain deterministic, runtime-bounded, and machine-checkable.
Validating every potential feature from the full product brief (all CRUD, recurring workflows,
location tracking, media/social variants, and a full permission matrix) would create excessive
runtime cost and brittle grading.

## Why this still matches the official capability target

The environment still requires agents to:

1. Diagnose and fix cross-layer backend integration failures.
2. Preserve and enforce tenancy boundaries across authenticated routes.
3. Maintain coherent data model + API behavior in a multi-family architecture.
4. Implement and persist new family-scoped write operations across multiple modules.
5. Progress the backend foundation in a way that supports the larger feature roadmap.

This keeps the task in the same capability class (hard multi-component backend build), while
using a practical and robust verifier surface.
