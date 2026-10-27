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
horizontal branch on every row that uses it.
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
        self.points: dict[str, tuple[float, float, str]] = {}  # terminal -> x, y, region
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

    def terminal(self, out: list[str], t: str, x, y, region: str) -> None:
        self.points[t] = (x, y, region)
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
        self.text(ox - 90, oy - 72, "Power circuit", "region", "start")
        for block in lay["blocks"]:
            bx, by = block["at"]
            x0, y0 = ox + bx, oy + by
            parts = [self.n.parts[pid] for pid in block["parts"]]
            comp = self.n.components[parts[0].component]
            for i, p in enumerate(parts):
                self.vpart(p, x0 + i * pitch, y0, y0 + h)
            x_last = x0 + (len(parts) - 1) * pitch
            if comp.type in ("contactor", "breaker"):
                self.line(self.parts_svg, x0 - 9, y0 + h / 2, x_last - 9, y0 + h / 2, "link")
            if comp.type == "motor":
                self.parts_svg.append(
                    f'<rect class="link" x="{_f(x0 - 16)}" y="{_f(y0 + 4)}" '
                    f'width="{_f(x_last - x0 + 32)}" height="{_f(h - 8)}" rx="6"/>'
                )
            self.text(x0 - 22, y0 + h / 2, comp.id, "id", "end")
            self.text(x0 - 22, y0 + h / 2 + 14, comp.label, "lbl", "end")

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
        elif k in ("main", "contact_no", "contact_nc"):
            self.line(g, x, y1, x, ym - 9)
            self.line(g, x, ym + 9, x, y2)
            self.line(g, x, ym + 9, x - 10, ym - 10)
            if k == "contact_nc":
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
        self.text(ox, oy - 72, "Control circuit", "region", "start")

        for r, row in enumerate(rows):
            y = oy + r * rh
            for item in row:
                pid, _, col = item.rpartition("@")
                col = int(col)
                xl = ox + 20 + col * w + 26
                self.hpart(self.n.parts[pid], xl, xl + w - 52, y)

        bottom = oy + (len(rows) - 1) * rh + 16
        self.line(self.wires_svg, self.left_x, oy - 40, self.left_x, bottom, "wire", f' data-net="{self.left_rail}"')
        self.line(self.wires_svg, self.right_x, oy - 40, self.right_x, bottom, "wire", f' data-net="{self.right_rail}"')

    def hpart(self, p: Part, xl, xr, y) -> None:
        g = self._start_part(p)
        comp = self.n.components[p.component]
        xm = (xl + xr) / 2
        k = p.kind
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
        self.terminal(g, p.a, xl, y, "control")
        self.terminal(g, p.b, xr, y, "control")
        g.append("</g>")
        self.parts_svg.extend(g)

        label = comp.id
        if comp.type in ("button", "lamp") or k == "coil":
            label = f"{comp.id} {comp.label}"
        self.text(xm, y - 31, label, "id")
        ta, tb = p.name.split("-")
        self.text(xl + 3, y + 25, ta, "tn", "start")
        self.text(xr - 3, y + 25, tb, "tn", "end")

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
            pts = [(t, *self.points[t]) for t in members]
            power = [(t, x, y) for t, x, y, region in pts if region == "power"]
            control = [(t, x, y) for t, x, y, region in pts if region == "control"]
            if power:
                self.route_power(net, power, [t for t, *_ in control], trunk_slots)
            if control:
                self.route_control(net, control, [t for t, *_ in power])

    def route_power(self, net, pts, elsewhere, trunk_slots) -> None:
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
