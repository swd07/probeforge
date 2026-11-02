# How to use ProbeForge

ProbeForge simulates a data center during a utility outage: the generator runs, but the automatic transfer switch
(ASCO Series 300 Group G, our redrawing of wiring diagram 978741) has a hidden fault and does not move the critical
load. The UPS carries it, with minutes left. Someone has to find the fault from the controller, the drawing and a
meter, like a field technician. That someone can be:

- **Agent**: Muse Spark does everything itself, with tool calls.
- **Hybrid**: Muse Spark's reading of the drawing, an information-gain planner that chooses the readings, and Muse
  Spark's explanation for the technician.
- **Engineer**: you, with the same tools and the same safety rules.

Nothing in the browser can damage anything: the switch is a simulation. The first bench, a star-delta motor
starter, is still available (see "Motor starter" at the end).

## 1. Start and stop the server

Set up once (see the README): `uv sync --frozen`, `cd web && npm ci && npm run build`, and a `.env` file with
`META_API_KEY=...`.

1. Start the server: `uv run python -m probeforge.server` (or `python -m uv run python -m probeforge.server` if `uv`
   is not on your PATH). Wait for `Uvicorn running on http://127.0.0.1:8000`.
2. Open **http://127.0.0.1:8000/?bench=ats** (or open http://127.0.0.1:8000 and click **ATS** in the top bar).
3. To stop: **Ctrl+C** in the terminal.

Engineer mode needs no API key; `PROBEFORGE_OFFLINE=1` runs the hybrid on a saved read without model calls (no
explanation). Agent runs and the agent column of Compare cost money (section 8).

## 2. The screen

- **Top bar**: bench (**Motor starter** / **ATS**), mode (**Agent**, **Hybrid**, **Engineer**), the fault list, a
  setting for the mode (effort, drawing read, or your name), **Start** (it becomes **End session** while a run
  goes), **Compare** (after a diagnosis), **Troubleshooting sheet**, and on the right the status.
- **Fault list**: **Random fault** (any of the 49 catalog faults visible on the controller during an outage) or one
  of the 12 dev scenarios **dev-01 to dev-12**, listed by a short symptom (the full symptom is the tooltip). The
  scenario's name (it names the fault) appears with the result, never before.
- **Status column** (left): the **UPS time left** (it drains 30 s per reading or action; at 0 the critical load is
  lost), the sources (utility, generator), the transfer switch position and the critical load, the six controller
  lights, the controller display, the stages from "Fault detected" to "Transfer verified", and folds for the metering
  screen and the event log. **Agent action limits** opens the policy table (generated from the code).
- **Drawing** (middle): our redrawing, not the official drawing (the note under the header says so in every view).
  Wires change color after a reading: **red** live,
  **blue** dead, **purple** probed; reading labels sit next to the points. Mouse wheel zooms, drag pans, **+**, **-**,
  **Home** (the operator circuit), **Fit** (the whole drawing). **follow probes** (on by default) moves the view to
  each new reading. In Hybrid runs the next planned reading is marked **next**. After the diagnosis the view zooms to
  the diagnosed part and outlines it in teal.
- **Right column**: the result card and the instruments, each folded to one line (click to open); the cards of the
  running mode; the top 3 hypotheses or candidate faults; and the **log**, which always keeps at least half of the
  column. The log lists every step with its policy verdict: **red** blocked (with the reason), **amber** waiting for an
  approval. It follows the newest step unless you scroll up. It is a log, not a chat.
- **Result card**: the verdict, the injected fault (revealed only now), the answer, **UPS time left at diagnosis**,
  the numbers (approvals and strong approvals counted apart), and in Hybrid runs the explanation for the technician.
- **Esc** closes the action limits, the troubleshooting sheet, Compare and the diagnosis form; an approval card needs
  an answer.

Verdicts: **Correct** (component, failure mode and part right), **Justified** (no reading can tell the fault from
another one, and the answer named that one or said insufficient information), **Wrong**, **No diagnosis**. A correct
diagnosis made after the UPS ran out is shown as such: critical load lost.

## 3. Agent mode

1. **Agent**, choose a fault, leave **effort low**, **Start**.
2. Watch the log (the agent's short notes, every tool call and its result) and the hypotheses.
3. **Approval** card: an action of the approval tier (for example isolating the sources while the load is not
   powered). **Approve** or **Deny**.
4. **Strong approval** card: isolating a powered load, or restoring the sources after a Transfer Failure (a repeat
   transfer attempt). The card shows the readings the agent cites and the policy's own facts (for example "the load
   is powered from the Emergency source"); tick the confirmation, then approve or deny. A request without a cited
   meter reading is refused in code before it reaches you.
5. A run takes 1 to 4 minutes and costs about $0.12 (up to $0.30 in the recorded runs).

## 4. Hybrid mode

1. **Hybrid**, choose a fault and the drawing read: one of the two **saved reads** (real earlier Muse Spark reads of
   the drawing, labelled by kind, repairs and date, for example "Saved read, 2 repairs (Oct 31)"; the full description
   is the tooltip and is on the drawing-read card). A live re-read is offered only on a machine that has the drawing
   crops (its cost is the tooltip and the confirmation on Start); on a public demo it is shown disabled.
2. **Start**. The drawing-read card shows the read and the model check: the transcription must reproduce the
   documented ASCO transfer sequence before any planning.
3. The planner shows each next reading on the drawing (**next**), then takes it. Candidate faults shrink after each
   reading. Approval cards work as in Agent mode.
4. The result card has Muse Spark's explanation: what failed, the readings that show it, a fixed isolation sentence
   added by code, then what to do. A run costs about $0.01 (the explanation call; $0.009 on average over the 22
   browser runs of Nov 2). When the explanation is the fixed template instead (always for insufficient information;
   otherwise when the Muse Spark call failed or its answers failed the check), the label says "fixed template" and why.
   The page tidies the text for display (a repeated step prefix removed, readings as numbers with units, hyphens
   restored in compounds); the run record keeps the model's text unchanged.

## 5. Engineer mode

1. **Engineer**, choose a fault, type your name, **Start**. Open **Your instruments** in the right column.
2. **Meter**: choose **V** or **Ω**, click two points on the drawing (A and B), **Measure**. Resistance needs both
   sources isolated.
3. **Look**: **Read panel**, **Event log**, **Metering**, **Position indicator** (the mechanism flag), **Wait**.
4. **Actions**: **Isolate sources** (approval; strong approval if the load is powered), **Restore sources**,
   **Manual operation check** (sources isolated; pressed under load, the safety policy blocks it as never allowed),
   **Repeat transfer** (strong approval, cite a reading).
5. **Suggest the next reading** (optional): the planner proposes a reading from your own readings (shadow mode); your
   trace is then marked assisted.
6. **Diagnose...**: component, part, failure mode, confidence, the steps that prove it; or **Insufficient
   information**.

In Engineer mode you answer your own approval cards. The policy blocks what would be unsafe on a real switch: an
ohmmeter on a live circuit, paralleling the sources, bypassing an interlock, operating the handle under load.

## 6. After the diagnosis: the intervention

The session stays open for the authorized person, in every mode. Open **Authorized intervention**: isolate the
sources, repair the part, restore the sources (strong approval, citing at least one executed reading from this
session; the policy checks that the reading was executed, not when it was taken). The stages
end at **Transfer verified** only when the simulator confirms the load on Emergency with the position confirmed by
the controller; the UPS clock then stops. Each part an approved repair changed is outlined on the drawing with a pill
(**adjusted**, **replaced**), and a recommendation a tool returns (the coil replacement: relubricate the operator) is
shown in the log.

While the repair is under way (sources isolated, or restored and not yet verified), **Start** asks first: the
button turns into "End the repair and start new?" and only a second click within 5 s starts a new run.

## 7. Compare and the troubleshooting sheet

- **Compare** shows four columns on the same fault: this run in its own column (you, the agent or the hybrid), a
  recorded engineer trace if one exists, Hybrid v2 on the default saved read, the agent and the info-gain baseline.
  Re-runs use the batch approval rules. After an agent run that run is the agent column and Compare is free; after a
  Hybrid or Engineer run the agent is re-run (about $0.12); the other re-runs are free.
- **Troubleshooting sheet**: symptom, causes, checks in a safe order and the separating reading for families A and B,
  generated from the simulator (not reviewed by an electrical engineer).

## 8. Costs and limits

| Action | Cost |
|---|---|
| Engineer mode | free |
| Agent run | about $0.12 (up to $0.30) |
| Hybrid run on a saved read | about $0.01 |
| Compare | free after an agent run; about $0.12 after a Hybrid or Engineer run (the agent re-run) |

Every model call reserves budget in a local ledger first. Live runs are capped per day (`PROBEFORGE_DEMO_DAILY_USD`,
default $5) and in total. On a public demo (`PROBEFORGE_PUBLIC=1`): a separate ledger with its own total
(`PROBEFORGE_PUBLIC_TOTAL_USD`), runs stopped at $0.75, approval cards time out after 2 minutes, no live re-read,
two open sessions per address, and visitors' Engineer traces are kept apart (they never appear in Compare). Whoever
uses the page answers the approval cards. A model call that gets no answer within 120 s (360 s with a live drawing
read) stops the run with that reason.

## 9. Common problems

| Problem | What to do |
|---|---|
| The page does not open | Start the server (section 1) and open http://127.0.0.1:8000/?bench=ats. |
| "address already in use" | An old server still runs. On Windows: `Get-NetTCPConnection -LocalPort 8000`, stop that process. |
| The page looks old after a code change | `npm run build` in `web/`, then reload (Ctrl+F5). |
| Start is grey | Choose a fault first; the list is cleared after every run on purpose. |
| "Connection lost: the session ended" | The server stopped or the network dropped; the session ends with the connection. Pick a fault and press Start. |
| "The session token is missing or expired" | Reload the page. |
| "The server is busy with other runs" | Other runs use every run slot; try again in a minute. |
| "A step is still pending" | Answer the approval card, or wait for the previous step. |
| Measure is grey | Set A and B on the drawing first. |
| An error about the key | `.env` with `META_API_KEY` is missing; Engineer mode still works. |
| "daily cap" | Today's live runs used the cap; wait until tomorrow or raise `PROBEFORGE_DEMO_DAILY_USD`. |
| "The public demo's model budget is used up" | The public ledger reached its total: Agent and Hybrid runs are paused; Engineer mode still works (no model calls). |
| "This address already has 2 open ProbeForge sessions" | Close another tab of the page, then press Start. |
| "The run stopped before a diagnosis: the Meta API ..." | The Meta API failed or did not answer in time; try again later. Engineer mode does not need it. |
| A test session left a trace in `scenarios/engineer_traces/ats/` | Delete it: the folder is for real engineer traces only. |

## 10. Meeting script (15 minutes)

| Time | What | How |
|---|---|---|
| 0:00 to 1:00 | The problem | Utility lost, generator running, the switch did not transfer, the UPS clock draining. |
| 1:00 to 4:00 | Hybrid run | **Hybrid**, a saved read, **dev-06**, **Start**. Point at the model check, the **next** marks, the candidate faults shrinking; end on the zoom to the diagnosed part and the explanation. |
| 4:00 to 7:00 | Agent run | **Agent**, **Random fault**, **Start** (about $0.12). Show a strong approval card with its cited readings and the policy's facts. |
| 7:00 to 12:00 | The engineer solves a fault | **Engineer**, **dev-01**: voltage across the coil during the command, isolate, resistance; then the intervention to **Transfer verified**. |
| 12:00 to 14:00 | Compare | **Compare** on the engineer's result: four columns, every reading. |
| 14:00 to 15:00 | Wrap up | The UPS time left at diagnosis on each result; questions. |

Before the meeting: start the server, do one quick Engineer run, and delete its trace from
`scenarios/engineer_traces/ats/`.

## Motor starter (Level 1)

The first bench: a star-delta reversing motor starter with one hidden fault among 91. Click **Motor starter** in the
top bar. The front panel (lamps **Power**, **Fault**, **Forward**, **Reverse**; buttons **Stop**, **Start Fwd**,
**Start Rev**; breaker **QF1**; motor state and line currents) replaces the status column.

- **Agent**: choose **Random fault**, **Clean test fault** or a scenario **s01 to s08**, effort low, **Start**
  (about $0.07). Approvals appear for switching power back on after a protection trip.
- **Hybrid**: choose a saved read (of the rendered drawing or of a phone photo; both have known errors) or a live read
  (about $0.20 once per server start). Confirm the uncertain regions, then the planner measures; when the answer
  depends on uncertain wiring, a card asks which wiring the panel has.
- **Engineer**: press the panel's buttons, **Wait**, measure volts with QF1 on and ohms with QF1 off, request **Reset
  KK1** with a reason, then **Diagnose...**. Traces go to `scenarios/engineer_traces/`. **Compare with agent and
  baseline** runs the half-split baseline and the agent on the same fault.

Results and the design of this stage: [LEVEL1.md](LEVEL1.md).
