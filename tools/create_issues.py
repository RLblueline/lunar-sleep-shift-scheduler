"""Create the team's labels, milestones and issues on GitHub from .github/backlog.json.

usage:
    gh auth login                                   # once
    python3 tools/create_issues.py OWNER/REPO       # safe to rerun: skips anything that already exists
    python3 tools/create_issues.py OWNER/REPO --dry-run

Uses the GitHub CLI (`gh api`), so no token handling here.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = {
    "role: systems": ("1d76db", "Systems lead"),
    "role: model": ("5319e7", "Model & science lead"),
    "role: software": ("0e8a16", "Software & UI lead"),
    "role: hardware": ("d93f0b", "Hardware & CAD lead"),
    "fdr": ("fbca04", "Needed for the Final Design Review"),
    "open-item": ("b60205", "Closes an OI, HW-OI or DEV item"),
}


def gh(*args, data=None):
    cmd = ["gh", "api", *args]
    if data is not None:
        cmd += ["--input", "-"]
    out = subprocess.run(cmd, input=json.dumps(data) if data is not None else None, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr.strip() or out.stdout.strip())
    return json.loads(out.stdout or "null")


def paged(path):
    items, page = [], 1
    while True:
        batch = gh(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        items += batch
        if len(batch) < 100:
            return items
        page += 1


def body_for(issue, roles):
    done = "\n".join(f"- [ ] {d}" for d in issue["done"])
    return (f"{issue['body']}\n\n**Done when**\n{done}\n\n**Owner role:** {roles[issue['role']]}\n"
            f"**References:** {issue['refs']}\n\n_From the team plan (docs/10-team-plan.md), task {issue['id']}._")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="OWNER/REPO")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    with open(os.path.join(ROOT, ".github", "backlog.json"), encoding="utf-8") as f:
        plan = json.load(f)
    r = f"repos/{a.repo}"
    if a.dry_run:
        for i in plan["issues"]:
            print(f"[{i['id']}] {i['title']}  (sprint {i['sprint']}, {i['role']})")
        return 0

    have = {l["name"] for l in paged(f"{r}/labels")}
    for name, (colour, desc) in LABELS.items():
        if name not in have:
            gh("-X", "POST", f"{r}/labels", data={"name": name, "color": colour, "description": desc})
            print("label", name)

    ms = {m["title"]: m["number"] for m in paged(f"{r}/milestones?state=all")}
    for m in plan["milestones"]:
        if m["title"] not in ms:
            ms[m["title"]] = gh("-X", "POST", f"{r}/milestones", data={"title": m["title"], "due_on": m["due"] + "T23:00:00Z"})["number"]
            print("milestone", m["title"])

    existing = {i["title"] for i in paged(f"{r}/issues?state=all")}
    for i in plan["issues"]:
        title = f"[{i['id']}] {i['title']}"
        if title in existing:
            continue
        labels = [f"role: {i['role']}", "fdr"] + (["open-item"] if any(k in i["refs"] for k in ("OI-", "DEV", "REQ-MDL")) else [])
        gh("-X", "POST", f"{r}/issues", data={"title": title, "body": body_for(i, plan["roles"]), "labels": labels,
                                             "milestone": ms[plan["milestones"][i["sprint"] - 1]["title"]]})
        print("issue", title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
