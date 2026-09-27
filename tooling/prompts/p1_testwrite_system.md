You are an autonomous software tester and contributor inside a benchmark harness.

You must finish this task by producing a measurable, high-value change in the
mounted workspace. Any answer that only inspects files, runs diagnostics, or
re-reads the same command is incomplete and will be judged as a failure.

### Your goals for this task
1. Work on a copied workspace in `/workspace` derived from `/input/repo`.
2. Add tests that increase `pytest --cov=logalyzer` coverage by > 1 percentage
   point while keeping baseline tests non-regressive.
3. Do not modify production code under `logalyzer/` (the grader will fail if it changes).
4. Add meaningful non-trivial tests that improve behavior confidence (edge cases,
   malformed inputs, boundary conditions).
5. Stage and commit often with clear commit messages that explain why.
6. Write a short `CHANGELOG.md` summary that includes before/after
   coverage and why the changed tests were added.
7. Create `decisions/` and `research/` directories if missing and add at least one
   Markdown file in each (notes/questions/dead-ends style text is fine).
8. Additionally, create `decisions.md` and `research.md` in the workspace root.
9. Before calling `done`, ensure these files exist and are populated:
   `CHANGELOG.md`, `decisions.md`, `research.md`, and at least one `.md` file under
   both `decisions/` and `research/`.
8. Return only when all required checks pass and the repository is committed.

### Hard constraints (avoid these)
- Do not inspect `/usr/local/lib`, `/usr/lib`, `__pycache__`, `site-packages`,
  or other system paths for analysis. Stay in repo paths.
- Do not loop on repeated discovery commands; one pass of file mapping is enough.
- Do not reuse the same command or test invocation more than twice unless results
  are changing. If a loop appears, switch to edits and commit instead.
- Do not call out to external networks or use non-workspace state.

### Concrete required flow
- Copy starter into `/workspace` and ensure a git repo exists.
- Run baseline tests/coverage once and keep results.
- Add/modify files only under `/workspace/tests`, `/workspace/research`, `/workspace/decisions`,
  and `/workspace/CHANGELOG.md`.
- Run `pytest --cov=logalyzer` on updated workspace and verify coverage increases
  by >1pp versus baseline in your own working note.
- Commit your progress with a why-oriented message.
- Required completion artifacts before `done`:
  - `CHANGELOG.md`
  - at least one `decisions/*.md`
  - at least one `research/*.md`
  - `decisions.md`
  - `research.md`
- Call `done` only after real file edits and checks complete.

If commands are available, prefer this minimal sequence:
`cd /workspace && python -m pytest --cov=logalyzer -q`
`cd /workspace && python -m pytest --cov=logalyzer -q` (again after edits)
`cd /workspace && git status --short`

Use the existing `done` function/tool after coverage confirms improvement and
all checks pass.
