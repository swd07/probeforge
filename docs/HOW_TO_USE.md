# How to use ProbeForge

ProbeForge shows a motor starter panel (a star-delta reversing starter) with one hidden fault. Someone has to find
the fault by pressing buttons and taking meter readings, like an electrician at a real panel. That someone can be:

- **Agent**: the Muse Spark AI does everything itself.
- **Hybrid**: Muse Spark reads the drawing, a planner program chooses the measurements, Muse Spark explains the result.
- **Engineer**: you do it yourself, with the same tools and the same safety rules.

Nothing in the browser can damage anything: the panel is a simulation.

## 1. Start and stop the server

You need the project set up once (see the README: `uv sync`, and a `.env` file with `META_API_KEY=...`).

1. Build the web page (only after the frontend code changed):
   ```
   cd web
   npm run build
   cd ..
   ```
2. Start the server:
   ```
   python -m uv run python -m probeforge.server
   ```
   (or `uv run python -m probeforge.server` if `uv` is on your PATH). Wait for `Uvicorn running on http://127.0.0.1:8000`.
3. Open **http://127.0.0.1:8000** in a browser.
4. To stop: press **Ctrl+C** in the terminal where the server runs.

Engineer mode works without an API key. Agent, Hybrid and Compare call the Meta Model API and cost money (see
section 6).

## 2. The screen

- **Top bar**: the three mode buttons (Agent, Hybrid, Engineer), the fault list, an extra setting for the mode, and
  **Start** (it becomes **Stop** while a run is going). On the right: status, which fault pool or scenario was run,
  the number of measurements, and blocked actions in red.
- **Front panel** (top left): the lamps **Power** (white), **Fault** (red: the motor overload has tripped),
  **Forward** and **Reverse** (green), the buttons **Stop**, **Start Fwd**, **Start Rev**, the main breaker **QF1**
  (ON / OFF), the motor state (stopped, star, delta, humming...) and the three line currents U, V, W.
- **Schematic** (bottom left): the full drawing. Wires change color after a measurement:
  **red** = measured live (voltage present), **blue** = measured dead (0 V), **purple** = part of a measurement
  (probed). Reading labels appear next to the points that were measured. Use the mouse wheel to zoom, drag to move,
  **Fit** to see everything. **follow probes** moves the view to each new measurement.
- **Right panel**: depends on the mode (hypotheses, candidate faults, or your instruments) and, below it, the list of
  steps. Every step passes the safety policy: a **red** step was blocked, an **amber** step waits for a human answer.
- **Result card** (appears at the top right when a run ends): the verdict, the hidden fault (revealed only now),
  the answer, the numbers, and **Show true live wiring** (paints the wires that really carry voltage).

Verdict colors: **Correct** (green: component, failure mode and pole all right), **Justified** (the fault cannot be
told apart from another one by any measurement, and the answer named that one or said "insufficient information"),
**Pole open** (right component and failure mode, but no pole named), **Wrong** (red), **No diagnosis**.

## 3. Agent mode

1. Click **Agent**.
2. Choose a fault: **Random fault (any of 91)**, **Clean test fault** (from the faults never used in development), or
   one of the scenarios **s01 to s08** (named by their symptom).
3. Leave **effort low**.
4. Click **Start**.
5. Watch: the right panel shows the agent's thinking and each tool call; **Hypotheses** shows its suspects with
   probabilities that change after every measurement; the schematic lights up where it measures.
6. If the agent asks for something that needs approval (for example switching the power back on after a protection
   trip), a card appears: click **Approve** or **Deny**.
7. The result card shows whether it was right. A run takes 20 to 90 seconds and costs about $0.07.

## 4. Hybrid mode

1. Click **Hybrid**.
2. Choose a fault (same list as above).
3. Choose the schematic read:
   - **saved read of a phone photo (has errors)**: a real earlier Muse Spark read of a phone photo of the drawing.
     Recommended for demos: fast and almost free.
   - **saved read (run 2, has errors)**: a real earlier read of the rendered drawing, with crossover errors.
   - **live read by Muse Spark**: Muse Spark reads the drawing three times now (about a minute, about $0.20, done once
     per server start and then reused).
4. Click **Start**.
5. A card lists the **uncertain regions** of the read (places where Muse Spark was unsure, or where its reads
   disagree); they light up on the schematic. Click **Confirm and diagnose**.
6. Watch the planner measure. **Candidate faults** shows the share of simulated faults still consistent with all
   readings. If a reading does not fit the drawing, the step list says so; usually an alternative wiring of an
   uncertain region explains it. If not, Muse Spark proposes a correction, shown as a diff (red lines removed,
   green lines added); a correction that would change what a healthy machine does is shown as rejected.
7. If the answer depends on wiring the read was unsure of, a card asks which wiring the real panel has. Pick the
   option that matches, or **Cannot check now** (then the pole is reported as ambiguous).
8. The result card shows the verdict and Muse Spark's short explanation for the technician.

## 5. Engineer mode

1. Click **Engineer**. The right panel becomes **Your instruments** and **Your steps**.
2. Choose a fault and type your name (the name goes into the saved trace).
3. Click **Start**.

Why the front panel shows **QF1 OFF** before you start: no panel is loaded yet, so everything is dark. After
**Start** the fault is already inside the panel and QF1 is **ON**, like a panel reported faulty. The blue **Next:**
box in Your instruments always suggests a sensible next step.

What you can do:

- **Look**: the lamps and the motor on the front panel. **Read panel** records what you see as a step.
- **Press buttons**: click **Start Fwd**, **Start Rev** or **Stop** on the front panel. **Button hold** sets how long the
  button is held.
- **Wait**: lets time pass (for example to see whether the motor switches from star to delta).
- **Measure volts**: choose **V**, click two points on the schematic (the small circles on the terminals or a wire;
  they show up as A and B), then **Measure**. Volts need QF1 **ON**. In a live circuit an open contact shows about
  230 V across it and a closed one 0 V; a point with no path to neutral behind it reads 0 V.
- **Measure ohms**: switch QF1 **OFF** first (click QF1 on the front panel, or **Power off**), choose **Ω**, click two
  points, **Measure**. "OPEN" means no connection.
- **Request a reset**: **Reset KK1** resets the tripped motor overload. It needs approval, and switching the power
  back on after a fuse or breaker trip also needs approval. Type a reason in the **Reason** field first. In engineer
  mode you approve your own request on the card that appears.
- **Diagnose...**: choose the component, the part (pole or contact) and the failure mode, set your confidence, tick
  the steps that prove it, and **Submit**. Or choose **Insufficient information**.

The safety policy blocks what would be unsafe on a real panel: an ohmmeter on a live circuit, more than 3 start presses
in a row, bypassing an interlock or changing the circuit. A blocked step flashes red and is listed in red with the
reason.

After you submit, the result card shows the verdict and saves your trace to `scenarios/engineer_traces/`.
**Compare with agent and baseline** runs the half-split baseline and the agent on the same fault and shows all three
side by side (measurements, blocked attempts, time, cost and every reading). Compare costs about $0.05 to $0.07.

## 6. Costs and limits

| Action | Cost |
|---|---|
| Engineer mode | free |
| Agent run | about $0.07 |
| Hybrid run, saved read | about $0.01 (explanation; more only if Muse Spark has to correct the netlist) |
| Hybrid live read | about $0.20, once per server start |
| Compare | about $0.05 to $0.07 (one agent run) |

Live runs from the browser are capped at $5 per day (setting `PROBEFORGE_DEMO_DAILY_USD`); the whole project at $130.
When a cap is reached, the browser shows an error instead of starting the run.

## 7. Common problems

| Problem | What to do |
|---|---|
| The page does not open | The server is not running, or runs on another port. Start it (section 1) and open http://127.0.0.1:8000. |
| "address already in use" when starting | An old server still runs. Close its terminal, or on Windows: `Get-NetTCPConnection -LocalPort 8000` and stop that process. |
| The page looks old after a code change | Run `npm run build` in `web/` and reload the page (Ctrl+F5). |
| Start is grey | Choose a fault first. After every run the fault list is cleared on purpose. |
| Measure is grey | Click two points on the schematic first (A and B must both be set), and the run must be going. |
| "resistance measurement on a live circuit is not allowed" | Switch QF1 off first, then measure ohms. |
| A voltage reading needs power but QF1 is off after a trip | Switching on after a protection trip needs approval: type a reason and click Power on, then approve. |
| Agent, Hybrid or Compare shows an error about the key | `.env` with `META_API_KEY` is missing or wrong; Engineer mode still works. |
| "daily cap" error | Live runs used today's $5; wait until tomorrow or raise `PROBEFORGE_DEMO_DAILY_USD`. |
| A test session left a trace in `scenarios/engineer_traces/` | Delete that file: the folder is for real engineer traces only. |

## 8. Meeting script (15 minutes)

| Time | What | How |
|---|---|---|
| 0:00 to 1:00 | The problem | Show the screen: one hidden fault in a star-delta reversing starter; find it like an electrician, under safety rules enforced in code. |
| 1:00 to 5:00 | Hybrid run from the phone photo | **Hybrid**, schematic **saved read of a phone photo**, fault **s07** or a **Clean test fault**, **Start**. Point at the uncertain regions on the drawing, confirm them. While the planner measures, show Candidate faults shrinking and the readings lighting up the wires. End on the result card and Muse Spark's explanation. |
| 5:00 to 6:00 | Safety in code | In the step list, show that every step passed the policy; mention that resistance on a live circuit and repeated starts are blocked in code, not in the prompt. |
| 6:00 to 12:00 | The engineer solves 2 or 3 faults | **Engineer**, type the engineer's name. Suggested faults: **s04** (forward does not start, reverse works: press Start Fwd and Start Rev, measure volts across the KM1 coil, switch off, measure ohms), **s03** (Fault lamp on: request Reset KK1 with a reason and approve it), and one **Random fault** if time allows. Let the engineer drive; point out the Next hint, a blocked ohmmeter reading on a live circuit, and the approval card. |
| 12:00 to 14:00 | Compare | After one engineer run, click **Compare with agent and baseline** (about $0.07): engineer, AI agent and baseline side by side, with every reading. |
| 14:00 to 15:00 | Wrap up | **Show true live wiring** on the last result; questions. |

Before the meeting: start the server, open the page once, and do one quick Engineer run to check everything works
(then delete its trace from `scenarios/engineer_traces/`).
