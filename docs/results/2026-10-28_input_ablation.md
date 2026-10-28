# Input ablation and schematic transcription (2026-10-28)

Two cheap tests before choosing the next architecture. Frozen prompt a194ad85aaa1, muse-spark-1.3.

## A. What circuit description does the agent need?

Clean holdout (43 faults: 38 visible, 5 latent), reasoning effort low, same tools and policy in all three.

| Input | Visible correct | incl. justified | Latent | Confidently wrong | Meas per case | Turns per case | $ per case |
|---|---|---|---|---|---|---|---|
| netlist + image (README) | 30/38 | 33/38 | 5/5 | 4 | 8.3 | 12.7 | 0.068 |
| netlist only | 30/38 | 33/38 | 5/5 | 3 | 9.8 | 13.6 | 0.077 |
| image only | 31/38 | 34/38 | 5/5 | 2 | 8.7 | 15.0 | 0.082 |

Image-only setup: the netlist text is replaced by "Schematic: see the attached image.", the image is
sent with every request (it is the only circuit description), and get_schematic answers with an
error. The system prompt is unchanged, so it still mentions "nominal resistances are in the
netlist" although the image shows no resistances, timer delay, trip time or rated current. The
agent called get_schematic once in every case (43 errors) and still used the ohmmeter in 35 cases.

Per-case flips: image only is right and netlist only wrong on c06, c12, c15, c18; the reverse on
c01, c05, c07. c01 and c07 (QF1:3-4 open, KM1:5-6 stuck_open, answered insufficient_information)
are wrong only in the image-only run. Earlier reruns of the same configuration flip 2 or 3 cases,
so all three inputs are within noise of each other on this circuit.

Raw: runs/20261028_122742_agent_clean_low_nonetlist (image only), runs/20261028_095705_agent_clean_low_noimage,
runs/20261027_223202_agent_clean_low. Cost of the image-only run: $3.53.

## B. Can Muse Spark transcribe the schematic into our YAML netlist?

scripts/transcribe_schematic.py: the same PNG plus a format spec with an example of a different,
tiny circuit (never the true YAML), reasoning effort medium, 3 independent runs. Connections are
scored as pairs of terminals sharing a net, so net names do not matter. The behaviour check builds
the simulator from the transcription and runs the healthy sequence (power on, forward start, star
to delta, Start Rev while running, stop, reverse start, reverse delta, stop) against the true
circuit; timer delay, trip time and rated current are not drawn and are copied from the true file.

| Run | Components | Parts P/R | Terminals P/R | Connections P/R | Nets exact | Interlocks | Loads | Panel steps same | Volts to N same | $ |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 17/17 | 1.00/1.00 | 1.00/1.00 | 0.915/0.915 | 29/35 | right | yes | 9/9 | 100% | 0.058 |
| 2 | 17/17 | 1.00/1.00 | 1.00/1.00 | 0.915/0.915 | 29/35 | right | yes | 6/9 | 100% | 0.067 |
| 3 | 17/17 | 1.00/1.00 | 1.00/1.00 | 0.901/0.901 | 28/35 | wrong | yes | 9/9 | 100% | 0.082 |

All components, types, labels and the 51 parts (with the right NO/NC kind) are found in every run.
The whole control circuit (wire numbers 1 to 15, N, coils, lamps) is transcribed exactly in every
run. Every wrong net is in the power circuit, at the two places where the drawing crosses wires:

- the reversing crossover after FU2 (KM2 swaps L1 and L3): wired straight through or with the wrong pair
- the delta link KM4 to U2/V2/W2: shifted by one winding

In runs 1 and 3 the wrong delta and reversing links still give a working delta and the correct
direction labels, so the panel sequence matches. In run 2 the delta links short a winding pair and
the motor reads "stopped" in delta. Run 3 also wrote the interlock pairs differently.

Limit of the check: voltage to N is 230 V on every live power net whatever the phase, so it cannot
see phase swaps; the motor state is the only behaviour signal for the power circuit.

Raw replies and scores: runs/20261028_122941_transcribe. Total $0.21.

Spend after both tests: $28.29 of $110.
