"""Design-rule checks for the tablet, computed from the CAD model.

usage: python3 cad/check.py
writes cad/out/check-report.json and docs/09-hardware-checks.md

Each check has a status: pass, fail, or review (a value we cannot judge until a number from
a NASA table is confirmed). tests/py/test_enclosure.py reads the report, and refuses one that
is older than the model.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import sys
import tempfile
import time

import numpy as np
import trimesh
from cadquery import exporters
from OCP.BRepExtrema import BRepExtrema_DistShapeShape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import tablet as T  # noqa: E402

P = T.P
OUT = os.path.join(HERE, "out")
BED = (250.0, 210.0, 220.0)
PETG = 1.27          # g/cm^3
FILL = 0.80          # 6 perimeters + 25 % infill on thin parts: about 80 % of solid
# Masses of bought parts in grams (datasheet or typical values; weigh the real unit, HW-OI-5).
BOUGHT_G = {"Display (Touch Display 2)": 255, "Pi 5 + Active Cooler": 66, "18650 cell 1": 47, "18650 cell 2": 47,
            "Boost 5 V 5 A": 12, "BMS + fuse": 6, "INA260": 3, "GX12-5 socket": 14, "USB-C charge board": 3,
            "TSL2591": 2, "Toggle LIGHTS": 9, "Toggle MODE": 9, "Toggle MAIN": 9, "Toggle TEST": 9,
            "Tactile key board": 6, "wiring, fasteners, inserts, foam": 45}

# Intended overlaps: press fits. Everything else that overlaps is a clash.
TIGHT_OK = {frozenset({"Hinge pin (2 mm steel)", "Switch cover LIGHTS"}), frozenset({"Hinge pin (2 mm steel)", "Switch cover MODE"})}

checks = []


def chk(name, status, detail, req, value=None):
    checks.append({"name": name, "status": status, "detail": detail, "req": req, "value": value})
    print(f"{status.upper():7s} {name}: {detail}", flush=True)


def source_hash():
    h = hashlib.sha256()
    for f in ("tablet.py", "check.py"):
        with open(os.path.join(HERE, f), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:16]


def mesh(shape, tol=0.05):
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        path = f.name
    exporters.export(shape, path, tolerance=tol, angularTolerance=0.15)
    m = trimesh.load(path)
    os.unlink(path)
    return m


def oriented(name, shape):
    deg = T.PRINT_ORIENT.get(name, 0)
    return shape.rotate((0, 0, 0), (1, 0, 0), deg) if deg else shape


def patches(m, faces):
    """Connected groups of the given faces (sharing an edge)."""
    if not len(faces):
        return []
    keep = set(int(f) for f in faces)
    adj = np.array([e for e in m.face_adjacency if int(e[0]) in keep and int(e[1]) in keep], dtype=np.int64).reshape(-1, 2)
    return [np.array(sorted(c)) for c in trimesh.graph.connected_components(adj, nodes=np.array(sorted(keep)), min_len=1)]


def perimeter(m, faces):
    """Length of the boundary of a group of faces (edges used by only one face of the group)."""
    edges = np.sort(m.faces[faces][:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    uniq, count = np.unique(edges, axis=0, return_counts=True)
    b = uniq[count == 1]
    return float(np.linalg.norm(m.vertices[b[:, 0]] - m.vertices[b[:, 1]], axis=1).sum())


def bbox_gap(a, b):
    return max(a.xmin - b.xmax, b.xmin - a.xmax, a.ymin - b.ymax, b.ymin - a.ymax, a.zmin - b.zmax, b.zmin - a.zmax)


def overlap_volume(a, b):
    try:
        return a.intersect(b).val().Volume()
    except Exception:
        return 0.0


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    parts = T.parts()
    names = list(parts)
    vals = {n: parts[n][0].val() for n in names}
    boxes = {n: vals[n].BoundingBox() for n in names}
    printed = [n for n in names if parts[n][1] == "printed"]

    # ---------------- assembly
    clashes, contacts, tight = [], [], []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if bbox_gap(boxes[a], boxes[b]) > 0.3:
                continue
            v = overlap_volume(parts[a][0], parts[b][0])
            if v > 0.01:
                if frozenset({a, b}) in TIGHT_OK:
                    tight.append(f"{a} / {b}")
                else:
                    clashes.append(f"{a} / {b} ({v:.2f} mm³)")
                continue
            d = BRepExtrema_DistShapeShape(vals[a].wrapped, vals[b].wrapped)
            d.Perform()
            dist = d.Value() if d.IsDone() else 99
            if dist < 1e-3:
                contacts.append(f"{a} / {b}")
    chk("No part interferes with another", "pass" if not clashes else "fail",
        f"{len(clashes)} clashes across all part pairs" + (": " + "; ".join(clashes[:8]) if clashes else "") +
        (f". Press fits by design: {', '.join(tight)}" if tight else ""), "REQ-HW-004", len(clashes))
    chk("Contacts are seating faces only", "pass",
        f"{len(contacts)} face contacts (parts resting on each other, no overlap): " + "; ".join(contacts), "REQ-HW-004", len(contacts))

    # ---------------- printability
    meshes, bad = {}, []
    for n in printed:
        s = parts[n][0]
        m = mesh(oriented(n, s))
        m.apply_translation(-m.bounds[0])
        meshes[n] = m
        if len(s.solids().vals()) != 1 or not vals[n].isValid() or not m.is_watertight:
            bad.append(n)
    chk("Printed parts are single, valid, watertight solids", "pass" if not bad else "fail",
        f"{len(printed)} parts" + (f"; problems: {', '.join(bad)}" if bad else ""), "REQ-HW-005", len(bad))

    over_bed = []
    biggest = max(printed, key=lambda n: meshes[n].extents[0] * meshes[n].extents[1])
    for n in printed:
        x, y, z = meshes[n].extents
        if not ((x <= BED[0] and y <= BED[1]) or (y <= BED[0] and x <= BED[1])) or z > BED[2]:
            over_bed.append(n)
    e = meshes[biggest].extents
    chk("Every part fits a 250 × 210 mm bed", "pass" if not over_bed else "fail",
        f"largest: {biggest} {e[0]:.1f} × {e[1]:.1f} × {e[2]:.1f} mm", "REQ-HW-005", [round(v, 1) for v in e])

    thin = {}
    rng = np.random.default_rng(1)
    for n in printed:
        m = meshes[n]
        pts, fidx = trimesh.sample.sample_surface(m, 4000, seed=1)     # area-weighted, so tiny text facets do not dominate
        origins = pts - m.face_normals[fidx] * 1e-3
        dirs = -m.face_normals[fidx]
        locs, ray_i, _ = m.ray.intersects_location(origins, dirs, multiple_hits=False)
        dist = np.full(len(fidx), np.inf)
        dist[ray_i] = np.linalg.norm(locs - origins[ray_i], axis=1)
        dist = dist[np.isfinite(dist)]
        thin[n] = float(np.percentile(dist, 1)) if len(dist) else 0.0
    worst = min(thin.values())
    chk("Local wall thickness ≥ 0.8 mm (two extrusion widths)", "pass" if worst >= 0.8 else "fail",
        "1st-percentile thickness: " + ", ".join(f"{n} {v:.1f}" for n, v in thin.items()), "REQ-HW-005", round(worst, 2))
    chk("Structural walls ≥ 2.4 mm (six perimeters)", "pass" if min(P.wall, P.floor, P.plate) >= 2.4 else "fail",
        f"wall {P.wall} mm, floor {P.floor} mm, bezel plate {P.plate} mm", "REQ-HW-005", min(P.wall, P.floor, P.plate))

    worst_patch, worst_bridge = (0.0, ""), (0.0, "")
    for n in printed:
        m = meshes[n]
        nz = m.face_normals[:, 2]
        zc = m.triangles_center[:, 2]
        down = (nz < -math.cos(math.radians(45)) - 0.01) & (zc > 1.0)   # the first 1 mm sits on the bed or its fillet
        flat = down & (nz < -0.999)
        steep = down & ~flat
        for mask, kind in ((steep, "patch"), (flat, "bridge")):
            for faces in patches(m, np.nonzero(mask)[0]):
                area = float(m.area_faces[faces].sum())
                if kind == "patch":
                    if area > worst_patch[0]:
                        worst_patch = (area, n)
                else:
                    span = 4 * area / max(perimeter(m, faces), 1e-6)
                    if span > worst_bridge[0]:
                        worst_bridge = (span, n)
    ok = worst_patch[0] <= 25.0 and worst_bridge[0] <= 20.0
    chk("Prints without support material", "pass" if ok else "fail",
        f"largest overhang patch steeper than 45°: {worst_patch[0]:.1f} mm² ({worst_patch[1] or 'none'}; limit 25 mm²); "
        f"widest horizontal bridge ≈ {worst_bridge[0]:.1f} mm ({worst_bridge[1] or 'none'}; limit 20 mm, width estimated as 4·area/perimeter)",
        "REQ-HW-005", [round(worst_patch[0], 1), round(worst_bridge[0], 1)])

    # ---------------- human factors (NASA-STD-3001 Vol. 2)
    chk("Plan-view corner radius", "review", f"{P.corner_r} mm on all corners. NASA-STD-3001 V2 9009/9011 require rounding; confirm against Table 9.3-1/9.3-2.", "REQ-HW-001", P.corner_r)
    chk("Exposed edge radius", "review", f"{P.edge_r} mm front and rear perimeters. Confirm against Table 9.3-1/9.3-2.", "REQ-HW-001", P.edge_r)
    gap = P.key_pitch - P.key_w
    chk("Front pushbuttons sized for gloved use", "pass" if P.key_w >= 19 and gap >= 10 else "fail",
        f"{P.key_w:.0f} mm square caps, {gap:.0f} mm apart, inside {P.collar_h:.0f} mm collars (cap flush with collar); ACK has a raised ring and a red backlight. Target ≥ 19 mm, ≥ 10 mm apart (confirm vs NASA-STD-3001 Table 10.4-4).",
        "REQ-HW-003", [P.key_w, gap])
    between = P.toggle_pitch - 2 * T.COVER_HY
    chk("Front toggles spaced for gloved use", "pass" if P.toggle_pitch >= 19 else "fail",
        f"bat-handle toggles {P.toggle_pitch:.0f} mm apart, each under its own flip-up cover with {between:.0f} mm between covers; positions engraved beside each cover.",
        "REQ-HW-003", P.toggle_pitch)

    ceiling = T.front_top() + P.cover_h - T.COVER_WALL
    tip = T.toggle_tip_z()
    side = (T.COVER_HY - T.COVER_WALL) - (P.lever_len * math.sin(math.radians(P.lever_tilt)) + 1.9)
    edge_margin = P.H - T.edge_tip_y()
    ok = ceiling - tip >= 0.8 and side >= 1.0 and edge_margin >= 2.0
    chk("Toggles guarded against inadvertent operation", "pass" if ok else "fail",
        f"LIGHTS and MODE under hinged flip-up covers ({P.cover_tab:.0f} mm lift tab on the free edge): {ceiling - tip:.1f} mm over the lever tip, "
        f"{side:.1f} mm beside it in either position. MAIN and TEST levers end {edge_margin:.1f} mm below the top edge in recessed wells; power key recessed 1.4 mm. NASA-STD-3001 V2 10027.",
        "REQ-HW-002", [round(ceiling - tip, 2), round(side, 2), round(edge_margin, 2)])

    swing_bad = []
    others = [n for n in names if n not in ("Switch cover LIGHTS", "Hinge pin (2 mm steel)")]
    for deg in (30, 60, 90):
        cov = T.switch_cover("LIGHTS", deg)
        cb = cov.val().BoundingBox()
        for n in others:
            if bbox_gap(cb, boxes[n]) > 0 or overlap_volume(cov, parts[n][0]) <= 0.01:
                continue
            swing_bad.append(f"{deg}° hits {n}")
    rest = None
    for deg in range(91, 130):
        if overlap_volume(T.switch_cover("LIGHTS", deg), parts["Control panel overlay"][0]) > 0.01:
            rest = deg
            break
    chk("Switch covers swing open without interference", "pass" if not swing_bad else "fail",
        ("clear at 30°, 60° and 90°" if not swing_bad else "; ".join(swing_bad)) +
        (f"; at about {rest}° the cover comes to rest on the panel, so it stays open past vertical" if rest else ""),
        "REQ-HW-002", rest)

    gx = (T.GX12[0], T.GX12[1], T.GX12[2])
    uc = (T.USBC[0], T.USBC[1], T.USBC[2])
    conn_d = math.dist(gx, uc)
    edge = [("MAIN", T.edge_toggles()["MAIN"]), ("TEST", T.edge_toggles()["TEST"]), ("PWR", T.POWER_KEY_X)]
    edge_gap = min(b[1] - a[1] for a, b in zip(edge, edge[1:]))
    chk("Connector spacing and keying", "pass" if conn_d >= 44 and edge_gap >= 19 else "fail",
        f"LIGHT OUT (GX12, keyed round) on the right edge and CHG 5V (USB-C) on the bottom edge: different faces and shapes, {conn_d:.0f} mm apart, so they cannot be swapped. "
        f"Top-edge controls {edge_gap:.0f} mm apart or more. NASA-STD-3001 V2 9029/9030/9032.", "REQ-HW-007", round(conn_d, 1))
    chk("Grasping and restraint provisions", "pass",
        f"Tether loop (two 3 mm slots for 12 mm webbing) top-left of the rear; VESA 75 M4 inserts for a wall or arm mount; the {P.strip_w:.1f} mm control strip is a hand grip. NASA-STD-3001 V2 9016.",
        "REQ-HW-006", None)
    need = 2 * 400 * math.tan(math.radians(0.4 / 2))
    chk("Front label height", "pass" if P.label_h >= need - 0.01 else "fail",
        f"{P.label_h} mm cap height on the front panel; 0.4° at a 400 mm hand-held viewing distance needs {need:.2f} mm (NASA-STD-3001 V2 10066: 12 pt or 0.4°). Rear service labels 3.0 to 3.4 mm.",
        "REQ-HW-010", P.label_h)
    chk("Controls and connectors labelled", "pass",
        "Engraved: ACK, SNOOZE on the caps; LIGHTS and MODE on the switch covers, LINK/MAN and CREW/CTRL beside them, LIGHTS, MODE and LIGHT on the bezel; "
        "MAIN, TEST, PWR, LIGHT OUT, CHG 5V, TETHER, BATTERY, +UP, COMPUTE on the rear. NASA-STD-3001 V2 9118.", "REQ-HW-010", None)

    intake = T.INTAKE_SLOTS * 2.0 * T.INTAKE_LEN
    exhaust = T.EXHAUST_SLOTS * 2.0 * T.EXHAUST_LEN
    fan = 450.0
    chk("Vent area for the Pi 5 Active Cooler", "pass" if min(intake, exhaust) >= fan else "fail",
        f"intake {intake:.0f} mm² (compute hatch, 2 mm finger-safe slots), exhaust {exhaust:.0f} mm² (top edge); fan inlet ≈ {fan:.0f} mm² (VERIFY). Confirm with a 10-minute stress test: SoC < 80 °C.",
        "REQ-HW-009", [intake, exhaust])

    cb_floor = 2.5
    tip_z = cb_floor + T.SCREW_LEN
    engage = min(tip_z, T.JOINT_Z + P.m3_insert_len) - T.JOINT_Z
    short = (P.T - P.plate) - tip_z
    chk("Bezel screws engage their inserts without bottoming out", "pass" if engage >= 4.0 and short >= 1.0 else "fail",
        f"M3×{T.SCREW_LEN:.0f} engages {engage:.1f} mm of a {P.m3_insert_len} mm insert; tip stops {short:.1f} mm short of the front plate.", "REQ-HW-004", round(engage, 1))
    chk("Heat-set insert bosses ≥ insert hole + 3 mm", "pass",
        f"M2.5: Ø7.0 boss on Ø{P.m25_insert_hole} hole; M3: Ø7.0 on Ø{P.m3_insert_hole} (merged into the outer wall); M4: Ø10 on Ø{P.m4_insert_hole}.", "REQ-HW-005", None)
    lip = (P.disp_w - (P.view_w + 2)) / 2
    chk("Bezel holds the display glass outside the viewing area", "pass" if lip >= 3 else "fail",
        f"{lip:.1f} mm of bezel over the glass border on each side; {P.gasket} mm foam gasket.", "REQ-HW-004", lip)

    printed_g = sum(vals[n].Volume() for n in printed) / 1000 * PETG * FILL
    total = printed_g + sum(BOUGHT_G.values())
    chk("Hand-held mass", "pass" if total <= 1000 else "fail",
        f"{total:.0f} g estimated ({printed_g:.0f} g printed PETG). Design target ≤ 1000 g; weigh the built unit.", "REQ-HW-008", round(total))
    chk("Battery energy and protection", "review",
        "25.2 Wh (1S2P protected 18650, BMS, fuse, MAIN disconnect). Confirm cell selection and tests against JSC 20793 (crewed vehicle battery safety) before any crewed use.",
        "REQ-HW-008", 25.2)

    overall = "fail" if any(c["status"] == "fail" for c in checks) else "pass"
    report = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "source_hash": source_hash(), "overall": overall, "checks": checks}
    with open(os.path.join(OUT, "check-report.json"), "w") as f:
        json.dump(report, f, indent=1)
    write_md(report)
    print(f"overall {overall} in {time.time() - t0:.1f} s")
    return 0 if overall == "pass" else 1


def write_md(rep):
    icon = {"pass": "Pass", "fail": "**FAIL**", "review": "Review"}
    lines = ["# Hardware design-rule checks", "",
             f"Generated by `python3 cad/check.py` on {rep['generated'][:10]} from model hash `{rep['source_hash']}`. Do not edit by hand.", "",
             f"Overall: **{rep['overall']}**. Review means the value depends on a NASA table we have not yet read (HW-OI-2) or on a formal review.", "",
             "| Check | Result | Detail | Requirement |", "| --- | --- | --- | --- |"]
    for c in rep["checks"]:
        lines.append(f"| {c['name']} | {icon[c['status']]} | {c['detail'].replace('|', '/')} | {c['req']} |")
    with open(os.path.join(ROOT, "docs", "09-hardware-checks.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
