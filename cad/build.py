"""Export the tablet model.

usage: python3 cad/build.py [--open DEG]
writes to cad/out/:
    tablet.step          full assembly for Fusion, Onshape or FreeCAD
    stl/<part>.stl       every printed part, already in print orientation
    viewer.html          interactive 3D viewer (open in a browser; needs internet for three.js)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

import cadquery as cq
import trimesh
from cadquery import exporters

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tablet as T  # noqa: E402

OUT = os.path.join(HERE, "out")
COLOURS = {"body": "#3d4148", "panel": "#4a4f57", "cover": "#1b1c1f", "ack": "#e9d79a", "key": "#dcdcdc",
           "metal": "#b9bdc2", "pcb": "#1f6b3a", "dark": "#141518"}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def to_mesh(shape, tol=0.08):
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        path = f.name
    exporters.export(shape, path, tolerance=tol, angularTolerance=0.2)
    m = trimesh.load(path)
    os.unlink(path)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", type=float, default=0.0, help="open angle of the LIGHTS cover in the viewer and STEP")
    args = ap.parse_args()
    os.makedirs(os.path.join(OUT, "stl"), exist_ok=True)
    parts = T.parts(open_deg=args.open)

    asm = cq.Assembly(name="lunar-sleep-shift-tablet")
    for name, (shape, kind, colour) in parts.items():
        asm.add(shape, name=slug(name), color=cq.Color(COLOURS[colour]))
    asm.save(os.path.join(OUT, "tablet.step"))

    for name, (shape, kind, _) in parts.items():
        if kind != "printed":
            continue
        deg = T.PRINT_ORIENT.get(name, 0)
        s = shape.rotate((0, 0, 0), (1, 0, 0), deg) if deg else shape
        m = to_mesh(s, 0.05)
        m.apply_translation(-m.bounds[0])
        m.export(os.path.join(OUT, "stl", slug(name) + ".stl"))

    meshes = []
    for name, (shape, kind, colour) in parts.items():
        m = to_mesh(shape)
        meshes.append({"name": name, "kind": kind, "colour": COLOURS[colour],
                       "v": [round(float(c), 2) for c in m.vertices.flatten()], "f": m.faces.flatten().tolist()})
    with open(os.path.join(HERE, "viewer_template.html"), encoding="utf-8") as f:
        html = f.read().replace("/*MESHES*/[]", json.dumps(meshes, separators=(",", ":")))
    with open(os.path.join(OUT, "viewer.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", os.path.relpath(OUT), "(tablet.step, stl/, viewer.html)")


if __name__ == "__main__":
    main()
