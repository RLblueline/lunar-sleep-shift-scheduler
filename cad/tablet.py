"""Parametric model of the Lunar Sleep-Shift tablet (CadQuery).

Every dimension lives in `Params`. Change a number, then run:
    python3 cad/check.py     design-rule checks  -> docs/09-hardware-checks.md
    python3 cad/build.py     STEP assembly + print-ready STLs -> cad/out/

Coordinates (mm): x across the width (0 at the left edge, looking at the screen),
y up the height (0 at the bottom edge), z through the thickness (0 = rear face,
front of the bezel at z = P.T, front of the control overlay at z = front_top()).

Bought parts (Pi, display, cells, switches) are simple envelopes taken from datasheets.
Envelopes marked VERIFY in docs/08-hardware-design.md must be measured on real parts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq


@dataclass(frozen=True)
class Params:
    # outer body
    W: float = 240.0               # width
    H: float = 138.0               # height
    T: float = 41.5                # rear face to front of bezel
    split: float = 36.0            # rear shell / bezel seam height
    wall: float = 2.4              # structural wall (six 0.4 mm perimeters)
    floor: float = 2.4
    corner_r: float = 13.0         # plan-view corner radius (REQ-HW-001)
    edge_r: float = 3.0            # front and rear perimeter edge radius (REQ-HW-001)
    plate: float = 2.4             # bezel front plate
    # display: Raspberry Pi Touch Display 2 (7 in, 1280 x 720)
    margin: float = 9.0
    disp_w: float = 189.5
    disp_h: float = 120.0
    disp_d: float = 15.0
    view_w: float = 155.5          # viewing area
    view_h: float = 88.0
    gasket: float = 0.5
    # control strip on the right
    strip_w: float = 41.5
    overlay: float = 1.5           # control-panel overlay plate
    key_w: float = 24.0            # square key cap
    key_flange: float = 26.0
    key_pitch: float = 34.0
    collar_h: float = 2.0
    collar_wall: float = 2.4
    key_gap: float = 0.4           # cap-to-hole clearance per side
    toggle_pitch: float = 22.0
    lever_len: float = 7.0
    lever_tilt: float = 15.0       # degrees from vertical in either latched position
    cover_h: float = 15.5          # flip-up safety covers over the front toggles
    cover_tab: float = 2.0         # glove lift tab on the free edge of each cover
    label_h: float = 2.8           # front label cap height: 0.4 deg at 400 mm (NASA-STD-3001 V2 10066)
    label_depth: float = 0.5
    # battery: 2 x 18650, 1S2P
    cell_d: float = 18.6
    cell_l: float = 65.2
    # fasteners
    m3_insert_hole: float = 4.0
    m3_insert_len: float = 5.7
    m25_insert_hole: float = 3.6
    m4_insert_hole: float = 5.6

    @property
    def cy(self): return self.H / 2

    @property
    def disp_cx(self): return self.margin + self.disp_w / 2

    @property
    def strip_cx(self): return self.margin + self.disp_w + (self.strip_w - self.wall) / 2 + 0.6

    @property
    def glass_top(self): return self.T - self.plate - self.gasket


P = Params()

# ---------------------------------------------------------------- layout
COVER_HX, COVER_HY, COVER_WALL = 7.0, 8.0, 1.6     # cover half-sizes in x and y, wall thickness
HINGE_DX, HINGE_DZ, KNUCKLE_R, PIN_D = 10.2, 3.2, 2.8, 2.0   # knuckles sit 0.4 mm clear of the cover wall
BUSHING_D, NUT_H, BUSHING_PROUD = 6.2, 2.0, 3.0    # 1/4-40 bushing; how far it stands above the overlay


def keys(p=P):
    """Square momentary keys: name -> (x, y)."""
    return {"ACK": (p.strip_cx, 24.0), "SNOOZE": (p.strip_cx, 24.0 + p.key_pitch)}


def toggles(p=P):
    """Front bat-handle toggles: name -> (x, y, up label, down label)."""
    y0 = 87.0
    return {"LIGHTS": (p.strip_cx, y0, "LINK", "MAN"), "MODE": (p.strip_cx, y0 + p.toggle_pitch, "CREW", "CTRL")}


def edge_toggles(p=P):
    """Recessed toggles in wells on the top edge: name -> x."""
    return {"MAIN": 40.0, "TEST": 62.0}


POWER_KEY_X = 86.0
WELL_BLOCK, WELL_DEPTH = 13.4, 9.0
EDGE_Z = 16.5                       # centre height of the top-edge controls (below the display)  # edge-toggle wells: boss depth from the top face, pocket depth
TETHER = (20.0, 124.0)
SENSOR = (P.strip_cx, 126.0)
LED = (P.strip_cx + 8.0, 24.0)     # under the ACK cap flange, beside the tactile switch
GX12 = (P.W, 36.0, 17.0)           # LIGHT OUT on the right edge: (x face, y, z)
USBC = (150.0, 0.0, 17.0)          # CHG 5V on the bottom edge: (x, y face, z)
VESA = 75.0


def overlay_box(p=P):
    """Control-panel overlay outline (x0, y0, x1, y1), kept 3.5 mm clear of the rounded bezel edge."""
    return (p.strip_cx - 17.5, 6.0, p.strip_cx + 17.5, 133.0)


def front_top(p=P):
    return p.T + p.overlay


def hinge_axis(p=P):
    """(x, z) of the cover hinge pin, which runs along y through both covers."""
    return p.strip_cx + HINGE_DX, front_top(p) + HINGE_DZ


def toggle_tip_z(p=P):
    return front_top(p) + BUSHING_PROUD + p.lever_len * math.cos(math.radians(p.lever_tilt))


def bezel_screws(p=P):
    # 5 mm from the edge: the display fills the body to within 9 mm, so the bosses merge into the wall
    return [(18, 5.0), (100, 5.0), (231, 5.0), (18, p.H - 5.0), (100, p.H - 5.0), (231, p.H - 5.0)]


SCREW_LEN = 35.0                   # M3 x 35 socket head, from the rear
JOINT_Z = 32.0                     # rear-shell bosses stop here; bezel bosses carry the inserts down to it
DISPLAY_POSTS = [(P.disp_cx + dx, P.cy + dy) for dx in (-82, 82) for dy in (-40, 40)]   # VERIFY on the real display


# ---------------------------------------------------------------- helpers
def rbox(w, h, d, r, x=0.0, y=0.0, z=0.0):
    s = cq.Workplane("XY").rect(w, h, centered=False).extrude(d)
    if r > 0:
        s = s.edges("|Z").fillet(min(r, w / 2 - 0.01, h / 2 - 0.01))
    return s.translate((x, y, z))


def box(w, h, d, x=0.0, y=0.0, z=0.0):
    return cq.Workplane("XY").box(w, h, d, centered=False).translate((x, y, z))


def cbox(w, h, d, cx, cy, z):
    return box(w, h, d, cx - w / 2, cy - h / 2, z)


def cyl_z(d, h, x, y, z):
    return cq.Workplane("XY").circle(d / 2).extrude(h).translate((x, y, z))


def cyl_y(d, length, x, y0, z):
    return cq.Workplane("XZ").circle(d / 2).extrude(-length).translate((x, y0, z))


def teardrop_y(d, length, x, y0, z):
    """Horizontal hole along +y with a 45-degree peak so it prints without support."""
    r = d / 2
    prof = (cq.Workplane("XZ").moveTo(-r * math.sqrt(0.5), r * math.sqrt(0.5)).lineTo(0, r * math.sqrt(2)).lineTo(r * math.sqrt(0.5), r * math.sqrt(0.5)).close()
            .extrude(-length))
    return cyl_y(d, length, 0, 0, 0).union(prof).translate((x, y0, z))


def teardrop_x(d, length, x0, y, z):
    """Horizontal hole along +x with a 45-degree peak."""
    return teardrop_y(d, length, 0, 0, 0).rotate((0, 0, 0), (0, 0, 1), -90).translate((x0, y, z))


def label(text, size, x, y, z, depth=None, angle=0.0):
    """Engraving tool: text standing on z, cut downward by `depth`."""
    depth = depth or P.label_depth
    t = cq.Workplane("XY").text(text, size, depth + 0.2, kind="bold", halign="center", valign="center")
    if angle:
        t = t.rotate((0, 0, 0), (0, 0, 1), angle)
    return t.translate((x, y, z - depth))


def body_blank(p, z0, z1, round_front, round_rear):
    b = rbox(p.W, p.H, z1 - z0, p.corner_r, 0, 0, z0)
    if round_rear:
        b = b.faces("<Z").edges().fillet(p.edge_r)
    if round_front:
        b = b.faces(">Z").edges().fillet(p.edge_r)
    return b


# ---------------------------------------------------------------- printed parts
def rear_shell(p=P):
    s = body_blank(p, 0, p.split, False, True)
    s = s.cut(rbox(p.W - 2 * p.wall, p.H - 2 * p.wall, p.split, p.corner_r - p.wall, p.wall, p.wall, p.floor))
    # battery bay (left) and compute hatch (centre) openings, closed by doors
    s = s.cut(cbox(*BATT_DOOR[:2], 10, *BATT_DOOR[2:], -1))
    s = s.cut(cbox(*HATCH[:2], 10, *HATCH[2:], -1))
    # door ledges: a 3 mm rim the doors sit on
    for (w, h, cx, cy) in (BATT_DOOR, HATCH):
        ring = cbox(w + 6, h + 6, LEDGE, cx, cy, p.floor).cut(cbox(w, h, LEDGE, cx, cy, p.floor))
        s = s.union(ring)
    # bezel screw bosses (through, counterbored from the rear)
    for (x, y) in bezel_screws(p):
        s = s.union(cyl_z(7.0, JOINT_Z - p.floor, x, y, p.floor))
        s = s.cut(cyl_z(3.4, p.split + 1, x, y, -0.5)).cut(cyl_z(6.2, 3.0, x, y, -0.5))
    # VESA 75 M4 insert bosses
    vx, vy = 120.0, p.cy
    for dx in (-VESA / 2, VESA / 2):
        for dy in (-VESA / 2, VESA / 2):
            s = s.union(cyl_z(10, 8, vx + dx, vy + dy, p.floor))
            s = s.cut(cyl_z(p.m4_insert_hole, 12, vx + dx, vy + dy, -0.5))
    # Pi 5 stand-offs (M2.5 inserts), board sits 8 mm off the floor
    for (x, y) in PI_HOLES:
        s = s.union(cyl_z(7.0, PI_Z - p.floor, x, y, p.floor)).cut(cyl_z(p.m25_insert_hole, 6, x, y, PI_Z - 5.5))
    # top-edge wells for MAIN and TEST, and the recessed power key
    for name, x in edge_toggles(p).items():
        top = p.glass_top - p.disp_d - 0.2        # stays under the display
        s = s.union(cbox(18, WELL_BLOCK, top - p.floor, x, p.H - WELL_BLOCK / 2, p.floor))   # solid to the floor: no overhang
        s = s.cut(cbox(14, WELL_DEPTH, 12, x, p.H - WELL_DEPTH / 2 + 0.01, EDGE_Z - 7))
        s = s.cut(teardrop_y(BUSHING_D + 0.4, WELL_BLOCK, x, p.H - WELL_BLOCK - 0.5, EDGE_Z))
    s = s.cut(teardrop_y(11, 1.0, POWER_KEY_X, p.H - 1.0, EDGE_Z)).cut(teardrop_y(6.4, p.wall + 2, POWER_KEY_X, p.H - p.wall - 1.0, EDGE_Z))
    for (x, y) in DISPLAY_POSTS:
        s = s.union(cyl_z(7.0, p.glass_top - p.disp_d - p.floor, x, y, p.floor)).cut(cyl_z(p.m25_insert_hole, 6, x, y, p.glass_top - p.disp_d - 5.5))
    # exhaust slots on the top edge above the Pi cooler (2 mm, finger safe)
    for i in range(EXHAUST_SLOTS):
        s = s.cut(cbox(2.0, p.wall + 2, EXHAUST_LEN, 108 + i * 4.0, p.H - p.wall / 2, 8))
    # connectors: GX12 on the right edge, USB-C on the bottom edge
    s = s.cut(teardrop_x(12.2, p.wall + 2, p.W - p.wall - 1, GX12[1], GX12[2]))
    s = s.cut(cq.Workplane("XZ").rect(9.6, 3.9).extrude(-(p.wall + 2)).translate((USBC[0], -1, USBC[2])))
    # tether: two 3 mm slots through the floor with a sealed cup inside (12 mm webbing)
    tx, ty = TETHER
    s = s.union(cbox(18, 16, 6, tx, ty, p.floor)).cut(cbox(14, 12, 3.6, tx, ty, p.floor))
    for dy in (-4.5, 4.5):
        s = s.cut(cbox(14, 3.0, p.floor + 0.2, tx, ty + dy, -0.1))
    # rear engravings
    for text, x, y, sz in (("MAIN", edge_toggles(p)["MAIN"], p.H - 6, 3.4), ("TEST", edge_toggles(p)["TEST"], p.H - 6, 3.4), ("PWR", POWER_KEY_X, p.H - 6, 3.4),
                           ("LIGHT OUT", p.W - 22, GX12[1], 3.0), ("CHG 5V", USBC[0], 12, 3.0), ("TETHER", tx, ty - 13, 3.0)):
        s = s.cut(label(text, sz, x, y, 0.5, depth=0.5).mirror("YZ", basePointVector=(x, 0, 0)))
    return s


def bezel(p=P):
    b = body_blank(p, p.split, p.T, True, False)
    b = b.cut(rbox(p.W - 2 * p.wall, p.H - 2 * p.wall, p.T - p.plate - p.split, p.corner_r - p.wall, p.wall, p.wall, p.split))
    # display window: 1 mm beyond the viewing area, 45 degree chamfer toward the front, 0.8 mm land
    vw, vh, land = p.view_w + 2, p.view_h + 2, 0.8
    b = b.cut(cbox(vw, vh, p.plate + 1, p.disp_cx, p.cy, p.T - p.plate - 0.5))
    cham = (cq.Workplane("XY").rect(vw, vh).workplane(offset=p.plate - land).rect(vw + 2 * (p.plate - land), vh + 2 * (p.plate - land))
            .loft().translate((p.disp_cx, p.cy, p.T - p.plate + land)))
    b = b.cut(cham)
    # control strip openings
    for x, y in keys(p).values():
        b = b.cut(cbox(p.key_w + 2 * p.key_gap, p.key_w + 2 * p.key_gap, p.plate + 1, x, y, p.T - p.plate - 0.5))
    for x, y, *_ in toggles(p).values():
        b = b.cut(cyl_z(BUSHING_D + 0.4, p.plate + 1, x, y, p.T - p.plate - 0.5))
    b = b.cut(cyl_z(9.0, p.plate + 1, *SENSOR, p.T - p.plate - 0.5))
    # screw bosses with M3 heat-set inserts
    for (x, y) in bezel_screws(p):
        boss = cyl_z(7.0, p.T - p.plate - JOINT_Z, x, y, JOINT_Z)
        # below the seam the boss reaches into the rear shell: trim it to the shell's cavity
        cavity = rbox(p.W - 2 * p.wall, p.H - 2 * p.wall, p.split - JOINT_Z, p.corner_r - p.wall, p.wall, p.wall, JOINT_Z)
        boss = boss.intersect(cavity.union(box(p.W, p.H, p.T, 0, 0, p.split)))
        b = b.union(boss)
        b = b.cut(cyl_z(p.m3_insert_hole, p.m3_insert_len, x, y, JOINT_Z - 0.01))
    # function labels to the left of the overlay
    lx = overlay_box(p)[0] - 8
    for name, (x, y, *_ ) in toggles(p).items():
        b = b.cut(label(name, p.label_h, lx, y, p.T))
    b = b.cut(label("LIGHT", p.label_h, lx, SENSOR[1], p.T))
    return b


def control_overlay(p=P):
    x0, y0, x1, y1 = overlay_box(p)
    ft = front_top(p)
    o = rbox(x1 - x0, y1 - y0, p.overlay, 4.0, x0, y0, p.T)
    # raised collars around the keys (cap top flush with collar top)
    for x, y in keys(p).values():
        outer = p.key_w + 2 * p.key_gap + 2 * p.collar_wall
        o = o.union(rbox(outer, outer, p.collar_h, 4.0, x - outer / 2, y - outer / 2, ft))
        o = o.cut(cbox(p.key_w + 2 * p.key_gap, p.key_w + 2 * p.key_gap, p.overlay + p.collar_h + 1, x, y, p.T - 0.5))
    for name, (x, y, up, down) in toggles(p).items():
        o = o.cut(cyl_z(BUSHING_D + 0.4, p.overlay + 1, x, y, p.T - 0.5))
        lx = x - COVER_HX - 6.0               # position labels beside the closed cover, clear of the lift tab
        o = o.cut(label(up, p.label_h, lx, y + 4.0, ft)).cut(label(down, p.label_h, lx, y - 4.0, ft))
    o = o.cut(cyl_z(9.0, p.overlay + 1, *SENSOR, p.T - 0.5))
    # held by the two toggle nuts plus VHB tape on the back (no room for a screw between the collars)
    # fixed hinge knuckles: D-shaped (flat base on the overlay) so they print without support
    for k in fixed_knuckles(p):
        o = o.union(k)
    hx, hz = hinge_axis(p)
    ys = [y for (_, y, *_ ) in toggles(p).values()]
    o = o.cut(cyl_y(PIN_D + 0.1, (ys[-1] + COVER_HY + 0.5) - (ys[0] - COVER_HY - 0.5), hx, ys[0] - COVER_HY - 0.5, hz))
    return o


def fixed_knuckles(p=P):
    hx, hz = hinge_axis(p)
    ft = front_top(p)
    out = []
    ys = sorted(y for (_, y, *_ ) in toggles(p).values())
    # one knuckle below the first cover, one shared between covers, one above the last
    spans = [(ys[0] - COVER_HY - 0.5, ys[0] - 4.6),
             (ys[0] + 4.6, ys[1] - 4.6),
             (ys[1] + 4.6, ys[1] + COVER_HY + 0.5)]
    for a, b in spans:
        k = cyl_y(2 * KNUCKLE_R, b - a, hx, a, hz).union(box(2 * KNUCKLE_R, b - a, hz - ft, hx - KNUCKLE_R, a, ft))
        out.append(k)
    return out


def switch_cover(name, open_deg=0.0, p=P):
    """Flip-up safety cover (aircraft / race-car style). Printed in black PETG, top down
    (red is reserved for emergency and warning, NASA-STD-3001 App. F)."""
    x, y, *_ = toggles(p)[name]
    ft = front_top(p)
    top = ft + p.cover_h
    c = cbox(2 * COVER_HX, 2 * COVER_HY, p.cover_h - 0.4, x, y, ft + 0.4)
    c = c.edges("|Z").fillet(2.0)
    c = c.cut(cbox(2 * (COVER_HX - COVER_WALL), 2 * (COVER_HY - COVER_WALL), p.cover_h - COVER_WALL, x, y, ft))
    # solid spine joining the right wall to the knuckle
    hx, hz = hinge_axis(p)
    c = c.union(box(hx - (x + COVER_HX) + 0.01, 8.8, top - hz, x + COVER_HX - 0.01, y - 4.4, hz))
    c = c.union(cyl_y(2 * KNUCKLE_R, 8.8, hx, y - 4.4, hz))
    c = c.cut(cyl_y(PIN_D - 0.05, 10, hx, y - 5, hz))                # light press fit on the pin
    # glove lift tab on the free edge, flush with the top (prints flat on the bed)
    c = c.union(rbox(p.cover_tab + 2.0, 2 * COVER_HY - 3.0, 2.4, 1.0, x - COVER_HX - p.cover_tab, y - COVER_HY + 1.5, top - 2.4))
    c = c.cut(label(name, p.label_h, x - 0.8, y, top))
    if open_deg:
        c = c.rotate((hx, 0, hz), (hx, 1, hz), open_deg)
    return c


def hinge_pin(p=P):
    hx, hz = hinge_axis(p)
    ys = [y for (_, y, *_ ) in toggles(p).values()]
    a, b = ys[0] - COVER_HY - 0.5, ys[-1] + COVER_HY + 0.5
    return cyl_y(PIN_D, b - a, hx, a, hz)


def key_cap(name, p=P):
    x, y = keys(p)[name]
    ft = front_top(p)
    top = ft + p.collar_h
    under = p.T - p.plate                       # inner face of the bezel plate
    c = rbox(p.key_w, p.key_w, top - (under - 0.3), 3.0, x - p.key_w / 2, y - p.key_w / 2, under - 0.3)
    c = c.union(rbox(p.key_flange, p.key_flange, 1.5, 3.0, x - p.key_flange / 2, y - p.key_flange / 2, under - 1.8))
    if name == "ACK":
        c = c.cut(cyl_z(3.2, 3.0, LED[0], LED[1], under - 1.8 - 0.01))   # pocket for the red LED   # raised ring: ACK can be found by touch (V2 10068)
        ring = rbox(p.key_w - 5, p.key_w - 5, 0.6, 2.0, x - (p.key_w - 5) / 2, y - (p.key_w - 5) / 2, top)
        ring = ring.cut(rbox(p.key_w - 7, p.key_w - 7, 0.6, 1.0, x - (p.key_w - 7) / 2, y - (p.key_w - 7) / 2, top))
        c = c.union(ring)
    return c.cut(label(name, 4.0 if name == "ACK" else 3.4, x, y, top))


def power_cap(p=P):
    """Flange behind the wall, stem ends 1.4 mm below the recess face (cannot be pressed by a flat surface)."""
    inner = p.H - p.wall
    return cyl_y(9.6, 3.0, POWER_KEY_X, inner - 3.0, EDGE_Z).union(cyl_y(5.8, p.wall - 0.4 - 1.0, POWER_KEY_X, inner, EDGE_Z))


LEDGE, LIP = 0.8, 1.0                      # door ledge in the shell, door lip that rests on it
BATT_DOOR = (82.0, 46.0, 52.0, 69.0)      # w, h, cx, cy
HATCH = (46.0, 38.0, 140.5, 69.0)        # between the Pi stand-offs
INTAKE_SLOTS, INTAKE_LEN = 10, 26.0
EXHAUST_SLOTS, EXHAUST_LEN = 12, 22.0
PI_Z = 10.4                                # Pi board underside
PI_ORIGIN = (108.0, 41.0)                  # Pi 5 lower-left corner (85 x 56 board)
PI_HOLES = [(PI_ORIGIN[0] + dx, PI_ORIGIN[1] + dy) for dx in (3.5, 61.5) for dy in (3.5, 52.5)]


def door(which, p=P):
    w, h, cx, cy = BATT_DOOR if which == "battery" else HATCH
    d = rbox(w - 0.4, h - 0.4, p.floor + LEDGE, 2.0, cx - w / 2 + 0.2, cy - h / 2 + 0.2, 0)
    # lip that sits on the ledge inside, a hook tab at one end and one captive M3 screw at the other
    d = d.union(cbox(w + 4.0, h + 4.0, LIP, cx, cy, p.floor + LEDGE))
    if which == "compute":   # intake slots over the Pi 5 Active Cooler, 2 mm wide (finger safe)
        for i in range(INTAKE_SLOTS):
            d = d.cut(cbox(2.0, INTAKE_LEN, 10, cx - 18 + i * 4.0, cy, -1))
    d = d.cut(label("BATTERY" if which == "battery" else "COMPUTE", 3.4, cx, cy + h / 2 - (7 if which == "battery" else 3.0), 0.5, depth=0.5).mirror("YZ", basePointVector=(cx, 0, 0)))
    if which == "battery":
        d = d.cut(label("+UP", 3.0, cx, cy - h / 2 + 7, 0.5, depth=0.5).mirror("YZ", basePointVector=(cx, 0, 0)))
    return d


# ---------------------------------------------------------------- bought parts (envelopes)
def bought(p=P):
    ft = front_top(p)
    out = {}
    out["Display (Touch Display 2)"] = cbox(p.disp_w, p.disp_h, p.disp_d, p.disp_cx, p.cy, p.glass_top - p.disp_d)
    out["Pi 5 + Active Cooler"] = box(85, 56, 1.6, PI_ORIGIN[0], PI_ORIGIN[1], PI_Z).union(cbox(40, 40, 8, PI_ORIGIN[0] + 33, PI_ORIGIN[1] + 28, PI_Z + 1.6))
    for i in range(2):
        out[f"18650 cell {i + 1}"] = (cq.Workplane("YZ").circle(p.cell_d / 2).extrude(p.cell_l)
                                     .translate((52 - p.cell_l / 2, 69 - 10.5 + i * 21.0, p.floor + LEDGE + LIP + 0.2 + p.cell_d / 2)))
    out["Tactile key board"] = cbox(30, 64, 1.6, p.strip_cx, 41.0, p.T - p.plate - 1.8 - 3.6 - 1.6)
    for name, (x, y) in keys(p).items():
        out[f"Tactile switch {name}"] = cbox(12, 12, 3.6, x, y, p.T - p.plate - 1.8 - 3.6)
    for name, (x, y, *_ ) in toggles(p).items():
        out[f"Toggle {name}"] = (cbox(13, 13, 10, x, y, p.T - p.plate - 10).union(cyl_z(BUSHING_D, p.plate + p.overlay + BUSHING_PROUD, x, y, p.T - p.plate))
                                 .union(bat_lever(x, y, +1, p)))
    for name, x in edge_toggles(p).items():
        floor_y = p.H - WELL_BLOCK                           # inner face of the well boss
        out[f"Toggle {name}"] = (cbox(13, 10, 13, x, floor_y - 5, EDGE_Z - 6.5).union(cyl_y(BUSHING_D, WELL_BLOCK - WELL_DEPTH + 1.0, x, floor_y, EDGE_Z))
                                 .union(edge_lever(x, p)))
    out["Boost 5 V 5 A"] = cbox(25, 22, 8, 104, 20, p.floor)
    out["BMS + fuse"] = cbox(30, 12, 4, 52, 102, p.floor)
    out["INA260"] = cbox(23, 23, 3, 60, 20, p.floor)
    out["GX12-5 socket"] = cq.Workplane("YZ").circle(7.5).extrude(16).translate((p.W - p.wall - 16, GX12[1], GX12[2]))
    out["USB-C charge board"] = cbox(14, 18, 4, USBC[0], 9 + p.wall, USBC[2] - 2)
    out["TSL2591"] = cbox(16, 19, 1.6, SENSOR[0], SENSOR[1], p.T - p.plate - 1.6 - 0.5)
    inner = p.H - p.wall
    out["Power tactile switch"] = cbox(6, 3.5, 6, POWER_KEY_X, inner - 3.0 - 1.75, EDGE_Z - 3)
    out["ACK LED"] = cyl_z(3.0, 5.0, LED[0], LED[1], p.T - p.plate - 1.8 - 3.0)
    out["Hinge pin (2 mm steel)"] = hinge_pin(p)
    return out


def bat_lever(x, y, direction, p=P):
    base = front_top(p) + BUSHING_PROUD
    lever = cq.Workplane("XY").circle(1.2).workplane(offset=p.lever_len).circle(1.9).loft()
    lever = lever.rotate((0, 0, 0), (1, 0, 0), -direction * p.lever_tilt).translate((x, y, base))
    return lever


def edge_lever(x, p=P):
    """Edge toggles point along +y; the tip must stay below the top edge (REQ-HW-002)."""
    base = p.H - WELL_DEPTH + 1.0
    lever = cq.Workplane("XZ").circle(1.2).workplane(offset=-EDGE_LEVER).circle(1.9).loft().translate((x, base, EDGE_Z))
    return lever.rotate((x, base, EDGE_Z), (x + 1, base, EDGE_Z), p.lever_tilt)


EDGE_LEVER = 5.5


def edge_tip_y(p=P):
    return p.H - WELL_DEPTH + 1.0 + EDGE_LEVER * math.cos(math.radians(p.lever_tilt)) + 1.9 * math.sin(math.radians(p.lever_tilt))


def parts(p=P, open_deg=0.0):
    """name -> (solid, kind, colour). kind: 'printed' or 'bought'."""
    PRINTED, BOUGHT = "printed", "bought"
    d = {
        "Rear shell": (rear_shell(p), PRINTED, "body"),
        "Front bezel": (bezel(p), PRINTED, "body"),
        "Control panel overlay": (control_overlay(p), PRINTED, "panel"),
        "Battery door": (door("battery", p), PRINTED, "body"),
        "Compute hatch": (door("compute", p), PRINTED, "body"),
        "Key cap ACK": (key_cap("ACK", p), PRINTED, "ack"),
        "Key cap SNOOZE": (key_cap("SNOOZE", p), PRINTED, "key"),
        "Switch cover LIGHTS": (switch_cover("LIGHTS", open_deg, p), PRINTED, "cover"),
        "Switch cover MODE": (switch_cover("MODE", 0.0, p), PRINTED, "cover"),
        "Power key cap": (power_cap(p), PRINTED, "key"),
    }
    for k, v in bought(p).items():
        d[k] = (v, BOUGHT, "metal" if "pin" in k or "lever" in k else "pcb" if any(s in k for s in ("Pi", "board", "INA", "BMS", "Boost", "TSL", "Tactile")) else "dark")
    return d


# Print orientation for each printed part: rotation about x (deg) so the listed face is on the bed.
PRINT_ORIENT = {"Rear shell": 0, "Front bezel": 180, "Control panel overlay": 0, "Battery door": 0, "Compute hatch": 0,
                "Key cap ACK": 180, "Key cap SNOOZE": 180, "Switch cover LIGHTS": 180, "Switch cover MODE": 180, "Power key cap": 0}
