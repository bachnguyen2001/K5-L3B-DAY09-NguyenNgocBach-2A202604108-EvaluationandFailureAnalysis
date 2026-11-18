"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import math
from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems = []

    # 1. Any metric value in pr["metrics"] that is NaN or inf
    for k, v in pr.get("metrics", {}).items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric {k} is NaN or inf ({v})")

    # 2. Row count != manifest items x len(manifest seeds)
    m = pr.get("manifest", {})
    expected_rows = m.get("items", 0) * len(m.get("seeds", []))
    if len(pr.get("rows", [])) != expected_rows:
        problems.append(f"row count {len(pr.get('rows', []))} != expected {expected_rows}")

    # 3. The (item_id, seed) set of PR differs from baseline
    pr_pairs = {(r["item_id"], r["seed"]) for r in pr.get("rows", [])}
    base_pairs = {(r["item_id"], r["seed"]) for r in base.get("rows", [])}
    if pr_pairs != base_pairs:
        problems.append(f"PR (item, seed) pairs differ from baseline (PR: {len(pr_pairs)}, base: {len(base_pairs)})")

    # 4. Evaluator failures or a row whose value for a graded spec metric is None
    if pr.get("evaluator_failures"):
        problems.append(f"PR has {len(pr['evaluator_failures'])} evaluator failure(s)")
    graded_metric_ids = {metric["id"] for metric in spec.get("metrics", []) if metric["id"] in GRADERS}
    for r in pr.get("rows", []):
        for mid in graded_metric_ids:
            if r.get(mid) is None:
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has None for graded metric {mid}")
                break
        else:
            continue
        break

    # 5. Item slice tags in PR rows differ from baseline
    base_slices = {r["item_id"]: sorted(r.get("slices") or []) for r in base.get("rows", [])}
    for r in pr.get("rows", []):
        iid = r.get("item_id")
        if iid in base_slices and sorted(r.get("slices") or []) != base_slices[iid]:
            problems.append(f"item {iid} slice tags differ from baseline")
            break

    # 6. Ratchet: base_spec given and a threshold in spec is looser than in base_spec
    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        base_m_map = {metric["id"]: metric for metric in base_spec.get("metrics", [])}
        curr_m_map = {metric["id"]: metric for metric in spec.get("metrics", [])}
        for mid, bm in base_m_map.items():
            if mid not in curr_m_map:
                problems.append(f"metric {mid} was dropped from spec")
                continue
            cm = curr_m_map[mid]
            if bm.get("blocking") and not cm.get("blocking"):
                problems.append(f"metric {mid} became non-blocking")
            b_th = bm.get("threshold", {})
            c_th = cm.get("threshold", {})
            if "max" in b_th and ("max" not in c_th or c_th["max"] > b_th["max"]):
                problems.append(f"metric {mid} max threshold loosened")
            if "min" in b_th and ("min" not in c_th or c_th["min"] < b_th["min"]):
                problems.append(f"metric {mid} min threshold loosened")
            if "max_increase" in b_th and ("max_increase" not in c_th or c_th["max_increase"] > b_th["max_increase"]):
                problems.append(f"metric {mid} max_increase loosened")
            if b_th.get("no_significant_drop") and not c_th.get("no_significant_drop"):
                problems.append(f"metric {mid} dropped no_significant_drop")

        base_s_map = {s["name"]: s for s in base_spec.get("slices", [])}
        curr_s_map = {s["name"]: s for s in spec.get("slices", [])}
        for sname, bs in base_s_map.items():
            if sname not in curr_s_map:
                problems.append(f"slice {sname} was dropped from spec")
                continue
            cs = curr_s_map[sname]
            if bs.get("blocking") and not cs.get("blocking"):
                problems.append(f"slice {sname} became non-blocking")
            if "min" in bs and ("min" not in cs or cs["min"] < bs["min"]):
                problems.append(f"slice {sname} min threshold loosened")
            if bs.get("no_significant_drop") and not cs.get("no_significant_drop"):
                problems.append(f"slice {sname} dropped no_significant_drop")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices", []):
        name = s["name"]
        metric = s["metric"]
        pr_items = per_item(pr, metric, slice_name=name)
        base_items = per_item(base, metric, slice_name=name)
        if not pr_items:
            continue
        val = round(sum(pr_items.values()) / len(pr_items), 4)
        verdict = "ok"
        note = ""

        if "min" in s and val < s["min"]:
            verdict = "fail"
        if s.get("no_significant_drop"):
            keys = sorted(set(pr_items) & set(base_items))
            if keys:
                d, lo, hi = stats.paired_bootstrap(
                    [pr_items[k] for k in keys],
                    [base_items[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"

        slice_id = f"slice:{name}/{metric}"
        if verdict != "ok" and s.get("blocking", True):
            blocked.append(slice_id)
        label = "BLOCK" if (verdict != "ok" and s.get("blocking", True)) else ("warn" if verdict != "ok" else "ok")
        lines.append(f"  {slice_id:<22} {val!s:<8} {json.dumps(s):<40} {note:<28} {label}")

    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
