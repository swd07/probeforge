"""Schematic SVG generated from the netlist.

The `layout` section of the circuit YAML only places parts. Every wire is drawn
from `nets`, so the picture cannot disagree with the netlist the simulator and
the agent use. Each part is an SVG group with data-part, each terminal a circle
with data-terminal and each wire a path with data-net, so the web UI can
highlight probe points.

Power circuit: blocks of vertical poles. A net is drawn as a horizontal trunk
just below its topmost terminal with vertical drops to the other terminals.
Control circuit: ladder rows between the left rail (control supply) and the
right rail (neutral). A net is a vertical bus at its leftmost terminal with a
horizontal branch on every row that uses it. Rails are optional (the ATS bench
has none: its rows run between source terminals); a row item ending in "~" is
drawn mirrored (terminal B on the left). A terminal shared by two parts (TS-17
for the two position contacts, for example) is drawn at both places and joined
by its net. Optional per layout: control nets listed in "stub_nets", and with
"stub_power_nets" every control net that continues in the power circuit, are
drawn as a short labelled stub at each terminal instead of a bus; "short_labels"
in the power layout names such nets "<net> to control".
"""

from xml.sax.saxutils import escape

from probeforge.sim.netlist import Netlist, Part

STYLE = """
.wire, .sym { stroke: #1d2430; stroke-width: 2; fill: none; stroke-linecap: round; }
.link { stroke: #1d2430; stroke-width: 1.2; stroke-dasharray: 5 4; fill: none; }
.dot { fill: #1d2430; }
.terminal { fill: #ffffff; stroke: #1d2430; stroke-width: 1.2; }
text { font-family: Arial, Helvetica, sans-serif; fill: #1d2430; }
.id { font-size: 15px; font-weight: bold; }
.lbl { font-size: 12px; fill: #4a5568; }
.tn { font-size: 11px; fill: #4a5568; }
.net { font-size: 12px; fill: #2b6cb0; font-weight: bold; }
.title { font-size: 20px; font-weight: bold; }
.region { font-size: 14px; fill: #4a5568; font-weight: bold; }
"""


def render_svg(netlist: Netlist) -> str:
    return _Renderer(netlist).render()


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


class _Renderer:
    def __init__(self, netlist: Netlist):
        self.n = netlist
        self.parts_svg: list[str] = []
        self.wires_svg: list[str] = []
        self.labels_svg: list[str] = []
        self.points: dict[str, list[tuple[float, float, str]]] = {}  # terminal -> every place it is drawn
        self.sides: dict[tuple[str, float, float], int] = {}  # control terminal placement -> -1 left end, +1 right end
        self.drawn: set[str] = set()
        self.max_x = 0.0
        self.max_y = 0.0

    # ----------------------------------------------------------------- helpers

    def _grow(self, x: float, y: float) -> None:
        self.max_x, self.max_y = max(self.max_x, x), max(self.max_y, y)

    def line(self, out: list[str], x1, y1, x2, y2, cls="sym", extra="") -> None:
        out.append(f'<line class="{cls}" x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}"{extra}/>')
        self._grow(max(x1, x2), max(y1, y2))

    def text(self, x, y, s, cls, anchor="middle") -> None:
        self.labels_svg.append(
            f'<text class="{cls}" x="{_f(x)}" y="{_f(y)}" text-anchor="{anchor}">{escape(s)}</text>'
        )
        self._grow(x + (len(s) * 7 if anchor == "start" else 0), y)

    def terminal(self, out: list[str], t: str, x, y, region: str, side: int = 0) -> None:
        self.points.setdefault(t, []).append((x, y, region))
        if side:
            self.sides[(t, x, y)] = side
        out.append(f'<circle class="terminal" data-terminal="{escape(t)}" cx="{_f(x)}" cy="{_f(y)}" r="2.6"/>')

    def _start_part(self, p: Part) -> list[str]:
        if p.id in self.drawn:
            raise ValueError(f"layout places {p.id} twice")
        self.drawn.add(p.id)
        return [f'<g class="part kind-{p.kind}" data-part="{escape(p.id)}">']

    # ---------------------------------------------------------- power circuit

    def power(self) -> None:
        lay = self.n.layout["power"]
        ox, oy = lay["origin"]
        pitch = lay.get("pole_pitch", 44)
        h = lay.get("pole_height", 50)
        self.text(ox - 90, oy - 72, lay.get("title", "Power circuit"), "region", "start")
        links: dict[str, tuple[float, float, float]] = {}  # contactor -> x_left, x_right, y of its linkage line
        for block in lay["blocks"]:
            bx, by = block["at"]
            x0, y0 = ox + bx, oy + by
            parts = [self.n.parts[pid] for pid in block["parts"]]
            comp = self.n.components[parts[0].component]
            for i, p in enumerate(parts):
                self.vpart(p, x0 + i * pitch, y0, y0 + h)
            x_last = x0 + (len(parts) - 1) * pitch
            if comp.type in ("contactor", "breaker", "transfer_switch"):
                self.line(self.parts_svg, x0 - 9, y0 + h / 2, x_last - 9, y0 + h / 2, "link")
                links[comp.id] = (x0 - 9, x_last - 9, y0 + h / 2)
            if comp.type == "motor":
                self.parts_svg.append(
                    f'<rect class="link" x="{_f(x0 - 16)}" y="{_f(y0 + 4)}" '
                    f'width="{_f(x_last - x0 + 32)}" height="{_f(h - 8)}" rx="6"/>'
                )
            self.text(x0 - 22, y0 + h / 2, comp.id, "id", "end")
            self.text(x0 - 22, y0 + h / 2 + 14, comp.label, "lbl", "end")
        for a, b in self.n.interlocks:
            if a in links and b in links:
                self.interlock(links[a], links[b])

    def interlock(self, la: tuple, lb: tuple) -> None:
        """Mechanical interlock (IEC 60617 style): a dashed linkage joining the two contactors' linkage
        lines, marked with an inverted triangle. Side by side, it runs above the right block's label;
        when the left block is lower, it runs along its own linkage line and up into the right block."""
        if la[0] > lb[0]:
            la, lb = lb, la
        xa, ya, xb, yb = la[1], la[2], lb[0], lb[2]
        if ya > yb:
            pts = [(xa, ya), (xb, ya), (xb, yb)]
            mx, my = (xa + 9 + xb) / 2, ya
        else:
            xv, yt = xa + 23, yb - 20
            pts = [(xa, ya), (xv, ya), (xv, yt), (xb, yt), (xb, yb)]
            mx, my = (xv + xb) / 2, yt
        self.parts_svg.append('<polyline class="link" points="' + " ".join(f"{_f(x)},{_f(y)}" for x, y in pts) + '"/>')
        self.parts_svg.append(f'<polygon class="sym interlock" fill="#ffffff" points="{_f(mx - 6)},{_f(my - 5)} '
                              f'{_f(mx + 6)},{_f(my - 5)} {_f(mx)},{_f(my + 5)}"/>')

    def vpart(self, p: Part, x, y1, y2) -> None:
        g = self._start_part(p)
        ym = (y1 + y2) / 2
        k = p.kind
        if k == "breaker_pole":
            self.line(g, x, y1, x, y1 + 14)
            self.line(g, x, y2, x, y2 - 14)
            self.line(g, x, y2 - 14, x - 11, y1 + 16)
            self.line(g, x - 4, y1 + 10, x + 4, y1 + 18)
            self.line(g, x - 4, y1 + 18, x + 4, y1 + 10)
        elif k == "fuse_pole":
            self.line(g, x, y1, x, y2)
            g.append(f'<rect class="sym" x="{_f(x - 6)}" y="{_f(y1 + 11)}" width="12" height="{_f(y2 - y1 - 22)}"/>')
        elif k in ("main", "contact_no", "contact_nc", "main_n", "main_e"):
            self.line(g, x, y1, x, ym - 9)
            self.line(g, x, ym + 9, x, y2)
            self.line(g, x, ym + 9, x - 10, ym - 10)
            if k in ("contact_nc", "main_n"):  # main_n: closed with the switch on Normal (as drawn on 978741)
                self.line(g, x, ym - 9, x - 12, ym - 9)
        elif k == "heater":
            self.line(g, x, y1, x, y1 + 11)
            self.line(g, x, y2, x, y2 - 11)
            g.append(
                f'<polyline class="sym" points="{_f(x)},{_f(y1 + 11)} {_f(x + 7)},{_f(y1 + 11)} '
                f'{_f(x + 7)},{_f(ym)} {_f(x - 7)},{_f(ym)} {_f(x - 7)},{_f(y2 - 11)} {_f(x)},{_f(y2 - 11)}"/>'
            )
        elif k == "winding":
            self.line(g, x, y1, x, y1 + 9)
            self.line(g, x, y2, x, y2 - 9)
            g.append(f'<rect class="sym" x="{_f(x - 6)}" y="{_f(y1 + 9)}" width="12" height="{_f(y2 - y1 - 18)}"/>')
        else:
            raise ValueError(f"cannot draw {p.id} ({k}) in the power circuit")
        ta, tb = p.name.split("-")
        self.terminal(g, p.a, x, y1, "power")
        self.terminal(g, p.b, x, y2, "power")
        g.append("</g>")
        self.parts_svg.extend(g)
        self.text(x + 5, y1 - 4, ta, "tn", "start")
        self.text(x + 5, y2 + 12, tb, "tn", "start")

    # -------------------------------------------------------- control circuit

    def control(self) -> None:
        lay = self.n.layout["control"]
        ox, oy = lay["origin"]
        w = lay.get("col_width", 112)
        rh = lay.get("row_height", 64)
        cols = lay.get("columns", 9)
        rows = lay["rows"]
        self.left_x = ox
        self.right_x = ox + 40 + cols * w
        self.left_rail = lay.get("left_rail")
        self.right_rail = lay.get("right_rail")
        self.text(ox, oy - 72, lay.get("title", "Control circuit"), "region", "start")

        for r, row in enumerate(rows):
            y = oy + r * rh
            for item in row:
                flip = item.endswith("~")
                pid, _, col = item.rstrip("~").rpartition("@")
                col = int(col)
                xl = ox + 20 + col * w + 26
                self.hpart(self.n.parts[pid], xl, xl + w - 52, y, flip)

        bottom = oy + (len(rows) - 1) * rh + 16
        if self.left_rail:
            self.line(self.wires_svg, self.left_x, oy - 40, self.left_x, bottom, "wire", f' data-net="{self.left_rail}"')
        if self.right_rail:
            self.line(self.wires_svg, self.right_x, oy - 40, self.right_x, bottom, "wire", f' data-net="{self.right_rail}"')

    def hpart(self, p: Part, xl, xr, y, flip: bool = False) -> None:
        g = self._start_part(p)
        comp = self.n.components[p.component]
        xm = (xl + xr) / 2
        k = p.kind
        if k in ("cutoff_n", "cutoff_e", "aux_n", "aux_e"):  # transfer switch contacts: closed on N / on E
            k = "contact_nc" if k.endswith("_n") else "contact_no"
        if k in ("wire", "pin", "solenoid", "input", "point"):
            return self.ats_part(p, comp, g, xl, xr, y, flip)
        if k in ("contact_no", "contact_nc", "main", "delayed_no", "delayed_nc"):
            self.line(g, xl, y, xm - 8, y)
            self.line(g, xm + 8, y, xr, y)
            self.line(g, xm - 8, y - 13, xm - 8, y + 13)
            self.line(g, xm + 8, y - 13, xm + 8, y + 13)
            if k.endswith("nc"):
                self.line(g, xm - 15, y + 15, xm + 15, y - 15)
            if k.startswith("delayed"):
                g.append(f'<path class="sym" d="M {_f(xm - 8)} {_f(y - 19)} A 8 6 0 0 1 {_f(xm + 8)} {_f(y - 19)}"/>')
            if comp.type == "button":
                self.line(g, xm, y - 13, xm, y - 23, "link")
                self.line(g, xm - 6, y - 23, xm + 6, y - 23)
        elif k == "coil":
            self.line(g, xl, y, xl + 8, y)
            self.line(g, xr - 8, y, xr, y)
            g.append(f'<rect class="sym" x="{_f(xl + 8)}" y="{_f(y - 13)}" width="{_f(xr - xl - 16)}" height="26"/>')
            if comp.type == "timer":
                self.line(g, xl + 8, y - 13, xl + 18, y + 13)
        elif k == "lamp":
            self.line(g, xl, y, xm - 13, y)
            self.line(g, xm + 13, y, xr, y)
            g.append(f'<circle class="sym" cx="{_f(xm)}" cy="{_f(y)}" r="13"/>')
            self.line(g, xm - 9, y - 9, xm + 9, y + 9)
            self.line(g, xm - 9, y + 9, xm + 9, y - 9)
        elif k == "fuse_pole":
            self.line(g, xl, y, xr, y)
            g.append(f'<rect class="sym" x="{_f(xl + 10)}" y="{_f(y - 7)}" width="{_f(xr - xl - 20)}" height="14"/>')
        else:
            raise ValueError(f"cannot draw {p.id} ({k}) in the control circuit")
        xa, xb = (xr, xl) if flip else (xl, xr)
        self.terminal(g, p.a, xa, y, "control", 1 if flip else -1)
        self.terminal(g, p.b, xb, y, "control", -1 if flip else 1)
        g.append("</g>")
        self.parts_svg.extend(g)

        label = comp.id
        if comp.type in ("button", "lamp") or k == "coil":
            label = f"{comp.id} {comp.label}"
        if p.kind.startswith("aux"):
            label = f"{comp.id} {'14A' if p.kind == 'aux_n' else '14B'}"
        self.text(xm, y - 31, label, "id")
        ta, tb = p.name.split("-")
        if flip:
            ta, tb = tb, ta
        self.text(xl + 3, y + 25, ta, "tn", "start")
        self.text(xr - 3, y + 25, tb, "tn", "end")

    def ats_part(self, p: Part, comp, g: list[str], xl, xr, y, flip: bool) -> None:
        """Harness wires, connector pins, the TS solenoid assembly, controller inputs and terminal-block points."""
        xm = (xl + xr) / 2
        k = p.kind
        xa, xb = (xr, xl) if flip else (xl, xr)
        if k == "wire":  # a harness wire: its number from the part name ("W3_TS6-W3_P3" -> 3)
            self.line(g, xl, y, xr, y)
            self.text(xm, y - 6, "wire " + p.name.split("_")[0].lstrip("W"), "tn")
        elif k == "pin":  # plug P / jack J contact
            self.line(g, xl, y, xm - 6, y)
            self.line(g, xm + 6, y, xr, y)
            for dx in (-6, 2):
                g.append(f'<polyline class="sym" points="{_f(xm + dx)},{_f(y - 6)} {_f(xm + dx + 5)},{_f(y)} '
                         f'{_f(xm + dx)},{_f(y + 6)}"/>')
            self.text(xm, y - 10, p.name.replace("-", "/"), "tn")
        elif k == "solenoid":  # bridge rectifier CR feeding the coil
            g.append(f'<rect class="link" x="{_f(xl + 6)}" y="{_f(y - 22)}" width="{_f(xr - xl - 12)}" height="44"/>')
            self.line(g, xl, y, xm - 22, y)
            self.line(g, xm + 22, y, xr, y)
            g.append(f'<polygon class="sym" points="{_f(xm - 22)},{_f(y)} {_f(xm - 11)},{_f(y - 11)} '
                     f'{_f(xm)},{_f(y)} {_f(xm - 11)},{_f(y + 11)}"/>')
            g.append(f'<circle class="sym" cx="{_f(xm + 12)}" cy="{_f(y)}" r="9"/>')
            self.line(g, xm, y, xm + 3, y)
            self.line(g, xm + 21, y, xm + 22, y)
            self.text(xm - 11, y + 4, "CR", "tn")
            self.text(xm, y - 31, f"{comp.id} solenoid assembly", "id")
            self.text(xa + (3 if not flip else -3), y + 25, p.name.split("-")[0], "tn", "start" if not flip else "end")
            self.text(xb - (3 if not flip else -3), y + 25, p.name.split("-")[1], "tn", "end" if not flip else "start")
        elif k == "input":  # a controller input: the jack pin it arrives on
            self.line(g, xl, y, xl + 14, y)
            g.append(f'<rect class="sym" x="{_f(xl + 14)}" y="{_f(y - 11)}" width="{_f(xr - xl - 14)}" height="22"/>')
            self.text(xl + 18, y + 4, comp.id, "tn", "start")
            self.terminal(g, p.a, xl, y, "control", -1)
            g.append("</g>")
            self.parts_svg.extend(g)
            return
        elif k == "point":  # terminal-block point
            g.append(f'<rect class="sym" x="{_f(xm - 9)}" y="{_f(y - 9)}" width="18" height="18"/>')
            self.line(g, xl, y, xm - 9, y)
            self.text(xm, y - 14, f"{comp.label} {p.name}", "tn")
            self.terminal(g, p.a, xl, y, "control", -1)
            g.append("</g>")
            self.parts_svg.extend(g)
            return
        self.terminal(g, p.a, xa, y, "control", 1 if flip else -1)
        self.terminal(g, p.b, xb, y, "control", -1 if flip else 1)
        g.append("</g>")
        self.parts_svg.extend(g)

    # ------------------------------------------------------------------ wires

    def path(self, net: str, d: str) -> None:
        self.wires_svg.append(f'<path class="wire" data-net="{escape(net)}" d="{d}"/>')

    def dot(self, x, y) -> None:
        self.wires_svg.append(f'<circle class="dot" cx="{_f(x)}" cy="{_f(y)}" r="3.6"/>')

    def route(self) -> None:
        missing = sorted(set(self.n.parts) - self.drawn)
        if missing:
            raise ValueError(f"layout does not place {missing}")
        trunk_slots: dict[float, int] = {}
        for net, members in self.n.nets.items():
            pts = [(t, *pl) for t in members for pl in self.points[t]]
            power = [(t, x, y) for t, x, y, region in pts if region == "power"]
            control = [(t, x, y) for t, x, y, region in pts if region == "control"]
            lay_c = self.n.layout.get("control", {})
            stub = net in lay_c.get("stub_nets", ()) or (bool(power) and lay_c.get("stub_power_nets", False))
            if power:
                elsewhere = ["control"] if control and self.n.layout["power"].get("short_labels") else [t for t, *_ in control]
                self.route_power(net, power, elsewhere, trunk_slots)
            if control and stub:
                self.route_stubs(net, control)
            elif control:
                self.route_control(net, control, [t for t, *_ in power])

    def route_power(self, net, pts, elsewhere, trunk_slots) -> None:
        if self.n.layout["power"].get("short_labels"):
            return self.route_power_tagged(net, pts, trunk_slots)
        if len(pts) == 1 and not elsewhere:
            t, x, y = pts[0]
            up = t == self._part_of(t).a
            y2 = y - 18 if up else y + 18
            self.path(net, f"M {_f(x)} {_f(y)} V {_f(y2)}")
            self.text(x, y2 - 5 if up else y2 + 13, net, "net")
            return
        ys = {y for _, _, y in pts}
        if len(ys) == 1:
            (y,) = ys
            xs = [x for _, x, _ in pts]
            self.path(net, f"M {_f(min(xs))} {_f(y)} H {_f(max(xs))}")
            trunk_y, x_lo, x_hi = y, min(xs), max(xs)
        else:
            top = min(ys)
            slot = trunk_slots.get(top, 0)
            trunk_slots[top] = slot + 1
            trunk_y = top + 14 + 8 * slot
            xs = [x for _, x, _ in pts]
            x_lo, x_hi = min(xs), max(xs)
            d = [f"M {_f(x_lo)} {_f(trunk_y)} H {_f(x_hi)}"] if x_hi > x_lo else []
            d += [f"M {_f(x)} {_f(y)} V {_f(trunk_y)}" for _, x, y in pts]
            self.path(net, " ".join(d))
            for x in sorted(set(xs)):
                degree = sum(1 for _, px, _ in pts if px == x) + (x > x_lo) + (x < x_hi)
                if degree >= 3:
                    self.dot(x, trunk_y)
        if elsewhere:
            self.path(net, f"M {_f(x_lo)} {_f(trunk_y)} H {_f(x_lo - 34)}")
            self.text(x_lo - 38, trunk_y + 4, f"{net} to {', '.join(elsewhere)}", "net", "end")

    def route_power_tagged(self, net, pts, trunk_slots) -> None:
        """Power nets tagged with their name at every terminal (as the tags on 978741); terminals of one net are
        joined by a trunk just outside the poles, so a trunk never runs along other poles' terminals."""
        for t, x, y in pts:
            top = t == self._part_of(t).a
            self.text(x - 4, y - 6 if top else y + 14, net, "net", "end")
        if len(pts) < 2:
            return
        tops = [(x, y) for t, x, y in pts if t == self._part_of(t).a]
        bottoms = [(x, y) for t, x, y in pts if t != self._part_of(t).a]
        if bottoms and not tops:  # e.g. load LA at the bottom of both TS blocks: trunk below
            yb = max(y for _, y in bottoms)
            slot = trunk_slots.get(("below", yb), 0)
            trunk_slots[("below", yb)] = slot + 1
            ty = yb + 20 + 9 * slot
        else:  # from a bottom terminal down to a top terminal (52U to TS): trunk just above the upper of the tops
            yt = min(y for _, y in tops)
            slot = trunk_slots.get(("above", yt), 0)
            trunk_slots[("above", yt)] = slot + 1
            ty = yt - 20 - 9 * slot
        xs = [x for _, x, _ in pts]
        d = [f"M {_f(min(xs))} {_f(ty)} H {_f(max(xs))}"] if max(xs) > min(xs) else []
        d += [f"M {_f(x)} {_f(y)} V {_f(ty)}" for _, x, y in pts]
        self.path(net, " ".join(d))

    def route_control(self, net, pts, elsewhere) -> None:
        if net in (self.left_rail, self.right_rail):
            rail_x = self.left_x if net == self.left_rail else self.right_x
            for _, x, y in pts:
                self.path(net, f"M {_f(rail_x)} {_f(y)} H {_f(x)}")
                self.dot(rail_x, y)
            top_y = self.n.layout["control"]["origin"][1] - 48
            name = f"{net} from {', '.join(elsewhere)}" if elsewhere else net
            self.text(rail_x, top_y, name, "net", "start" if net == self.left_rail else "middle")
            return
        bus_x = min(x for _, x, _ in pts)
        rows: dict[float, list[float]] = {}
        for _, x, y in pts:
            rows.setdefault(y, []).append(x)
        y_top, y_bot = min(rows), max(rows)
        d = [f"M {_f(bus_x)} {_f(y_top)} V {_f(y_bot)}"] if y_bot > y_top else []
        for y, xs in rows.items():
            if max(xs) > bus_x:
                d.append(f"M {_f(bus_x)} {_f(y)} H {_f(max(xs))}")
            degree = (y > y_top) + (y < y_bot) + (max(xs) > bus_x) + (bus_x in xs)
            if degree >= 3:
                self.dot(bus_x, y)
        if d:
            self.path(net, " ".join(d))
        if elsewhere or len(pts) == 1:
            _, x, y = pts[0]
            self.text(x, y - 8, net, "net")
        self.text(bus_x + 6, y_top - 6, net, "net", "start")

    def route_stubs(self, net, pts) -> None:
        """A short labelled stub at each terminal (the net continues elsewhere on the drawing)."""
        for t, x, y in pts:
            side = self.sides.get((t, x, y), -1)
            x2 = x + 18 * side
            self.path(net, f"M {_f(x)} {_f(y)} H {_f(x2)}")
            self.text(x2 + 3 * side, y + 4, net, "net", "start" if side > 0 else "end")

    def _part_of(self, terminal: str) -> Part:
        for p in self.n.parts.values():
            if terminal in (p.a, p.b):
                return p
        raise KeyError(terminal)

    # ---------------------------------------------------------------- output

    def render(self) -> str:
        self.power()
        self.control()
        self.route()
        self.text(20, 32, self.n.title, "title", "start")
        if self.n.drawing_note:  # a redrawn diagram states its source
            self.text(20, 52, self.n.drawing_note, "lbl", "start")
        width, height = self.max_x + 40, self.max_y + 30
        return "\n".join(
            [
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(width)}" height="{_f(height)}" '
                f'viewBox="0 0 {_f(width)} {_f(height)}" data-circuit="{escape(self.n.name)}">',
                f"<style>{STYLE}</style>",
                f'<rect width="{_f(width)}" height="{_f(height)}" fill="#ffffff"/>',
                '<g class="wires">',
                *self.wires_svg,
                "</g>",
                '<g class="parts">',
                *self.parts_svg,
                "</g>",
                '<g class="labels">',
                *self.labels_svg,
                "</g>",
                "</svg>",
                "",
            ]
        )


def render_png(netlist: Netlist, zoom: float = 1.0) -> bytes:
    """Rasterize the schematic SVG to PNG (the Meta API takes PNG, not SVG)."""
    import resvg_py

    return bytes(resvg_py.svg_to_bytes(svg_string=render_svg(netlist), zoom=zoom, background="#ffffff"))
