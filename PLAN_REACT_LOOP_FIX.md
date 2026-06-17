# Plan – Fix ReAct loop & repeated writes

**Goal**: Prevent the ReAct V2 core from endlessly re‑executing the same steps after a tool failure (e.g. `fetch_url`) or after a successful `write_file` that triggers a forced quality‑review instruction.

## 1️⃣ Analyse current problem
- `ReActCoreMiddleware` injects `ctx.forced_instructions` after a successful `write_file` (lines ~438‑456). This forces the step to stay *pending* until the review is completed.
- `plan_manager.update_step_status` checks `ctx.forced_instructions` and **never marks the step as `done`** while it is non‑empty (lines 241‑246). The loop therefore keeps calling `write_file` repeatedly.
- When a tool (e.g. `fetch_url`) fails, the step is not marked `failed` in the plan – only a warning flag is set. `replan_failed` is never triggered, so the same failing tool call is retried ad‑infinitum.
- `LoopDetectionMiddleware` only hashes **the last tool call** (`ctx.tool_results[-1:]`) and uses a relatively high hard limit (5) for file writes, so repeated writes are not stopped.

## 2️⃣ Desired behaviour
| Situation | Desired outcome |
|-----------|-----------------|
| `write_file` succeeds and a forced review is injected | The step becomes **`done`** after the review finishes (i.e. after `read_file` → `edit_file` → `write_file` sequence) and the forced instruction is cleared.
| A tool fails (e.g. `fetch_url` cannot parse) | The step is marked **`failed`**, the error is recorded, and `replan_failed` is invoked immediately to generate a new plan for the remaining work.
| Repeated identical tool calls (especially `write_file`) | Loop detection should abort after **3** identical writes (file‑basename based) and issue a clear error.

## 3️⃣ Implementation steps
1. **Add a review‑completion flag**
   - Extend `RunContext` with `review_pending: bool = False`.
   - In `ReActCoreMiddleware` when injecting `forced_instructions`, also set `ctx.review_pending = True`.
   - After a successful `read_file`/`edit_file`/`write_file` that satisfies the review, clear `ctx.forced_instructions` **and** set `ctx.review_pending = False`.
   - Modify `plan_manager.update_step_status`:
     - Only block `done` while `ctx.review_pending` is true *and* the current step tool is `write_file`.
     - Once the review sequence finishes (detect by seeing the three tools executed in order), mark the step as `done`.
2. **Mark failed steps explicitly**
   - In `plan_manager.update_step_status`, when `has_error` is true, set `current_step.status = "failed"` (already does) **and** set `ctx.last_error`.
   - Immediately after marking failed, call `await replan_failed(ctx)` (make `update_step_status` async or extract logic to a new helper) so the loop re‑generates the plan without waiting for the next round.
3. **Improve LoopDetectionMiddleware**
   - Replace `last_results = ctx.tool_results[-1:]` with a sliding window of the last `self.window_size` results (`ctx.tool_results[-self.window_size:]`).
   - Reduce hard limit for file writes to **3** (instead of 5) and make it configurable.
   - Use full absolute path as part of the write‑key (e.g., `path_key = f"write:{os.path.abspath(path)}"`).
4. **Add unit tests** (optional but recommended) to verify:
   - A successful `write_file` followed by a forced review results in a single `write_file` execution.
   - A failing `fetch_url` causes the step to be marked failed and a new plan is generated.
   - LoopDetection aborts after three identical `write_file` calls.
5. **Commit workflow**
   - Add the plan file (`PLAN_REACT_LOOP_FIX.md`).
   - Apply code changes in the following order:
     a. `RunContext` new fields.
     b. `ReActCoreMiddleware` injection changes.
     c. `plan_manager.update_step_status` adjustments.
     d. `LoopDetectionMiddleware` enhancements.
   - Run existing test suite (`pytest -q`) to ensure no regressions.
   - Commit each logical group with a clear message.

## 4️⃣ Timeline (estimated)
- **0 – 15 min** – Add plan file and initial commit.
- **15 – 45 min** – Implement context/review flag and adjust `ReActCoreMiddleware`.
- **45 – 75 min** – Update `plan_manager.update_step_status` and add async replanning call.
- **75 – 95 min** – Refine `LoopDetectionMiddleware` logic.
- **95 – 115 min** – Run full test suite, fix any failures.
- **115 – 130 min** – Final commit with all changes, push (if remote), and add a short changelog.

---

*All steps will be performed locally; no external network calls are required.*