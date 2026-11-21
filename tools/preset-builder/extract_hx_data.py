#!/usr/bin/env python3
"""Extract HX Effects model data from a local HX Edit install into hx-data.js for the preset builder, plus what this
repo's firmware builds add (NAM, Click, the custom effects, the HX Stomp amps and preamps: firmware_models.py).

Usage:
    python3 tools/preset-builder/extract_hx_data.py ["/Applications/Line6/HX Edit.app"]

Writes hx-data.js next to this script (gitignored: Line 6 data). Re-run after updating HX Edit or the builds.
"""
import json
import statistics
import sys
from pathlib import Path

import firmware_models as fw

DEFAULT_APP = "/Applications/Line6/HX Edit.app"

# .models file -> (display category, sort order). Category numbers come from the files themselves.
MODEL_FILES = [
    "distortion", "compressor", "gate", "eq", "modulation", "delay", "reverb",
    "pitch-synth", "filter", "wah", "amp", "preamp", "cab", "cabmicirs",
    "volumepan", "sendreturn", "fixed",
]

# eCategory (the "category" field in *.models) -> label shown in the browser
CATEGORY_LABELS = {
    3: "Distortion", 4: "Dynamics", 14: "EQ", 8: "Modulation", 9: "Delay", 10: "Reverb",
    7: "Pitch/Synth", 5: "Pitch/Synth", 6: "Filter", 11: "Wah", 1: "Amp", 13: "Preamp",
    2: "Cab", 19: "Cab", 17: "Volume/Pan", 12: "Send/Return", 15: "Looper", 16: "IR",
}

HX_EFFECTS = 2162693
# Stock HX Effects has no amps, preamps or cabs; those models carry no device list, so drop them by category.
# The amps and preamps the firmware builds add come back in below (firmware_models.amp_builds).
NOT_ON_HX_EFFECTS = {1, 13, 2, 19}
FW_TYPE = {1: 2, 2: 0, 3: 1}   # firmware param type (1 bool, 2 int, 3 float) -> HX Edit valueType
# display formats the build scripts use that HelixControls.json doesn't have
FW_CONTROLS = {
    "fw_db": {"format": "%.1f", "formatUnits": "%.1f dB"},
    "fw_hz": {"formatUnits": [{"lowerBound": 0, "upperBound": 1000, "format": "%.0f Hz"},
                              {"lowerBound": 1000, "upperBound": 1e9, "format": "%.1f kHz", "unitsMultiplier": 0.001}]},
}

TEMPLATES = {
    "hfx": "default_preset_hfx.hlx",
}


def main() -> None:
    app = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_APP)
    res = app / "Contents" / "Resources"
    if not res.is_dir():
        sys.exit(f"HX Edit resources not found at {res}")

    models = []
    seen = set()
    every = {}   # every HX Edit model by id, for the firmware models' hosts and templates
    amp_builds = fw.amp_builds()
    for name in MODEL_FILES:
        path = res / f"{name}.models"
        if not path.exists():
            print(f"skip: {path.name} missing")
            continue
        for m in json.loads(path.read_text()):
            every.setdefault(m["symbolicID"], m)
            cat = m.get("category")
            build = amp_builds.get(m["symbolicID"])
            if cat not in CATEGORY_LABELS or m["symbolicID"] in seen:
                continue
            if cat in NOT_ON_HX_EFFECTS and not build:
                continue
            if "devices" in m and HX_EFFECTS not in [d["id"] for d in m["devices"]] and not build:
                continue
            seen.add(m["symbolicID"])
            params = []
            for p in m.get("params", []):
                q = {k: p[k] for k in ("symbolicID", "name", "valueType", "min", "max", "default") if k in p}
                for k in ("displayType", "default_stereo", "max_stereo", "stereo-only"):
                    if k in p:
                        q[k] = p[k]
                params.append(q)
            models.append({
                "id": m["symbolicID"],
                "name": m.get("name") or m["symbolicID"],
                "category": cat,
                "group": CATEGORY_LABELS[cat],
                "mono": m.get("mono"),
                "stereo": m.get("stereo"),
                "load": m.get("load"),
                "loadStereo": m.get("load_stereo"),
                "cablink": m.get("cablink"),
                "devices": [d["id"] for d in m["devices"]] if "devices" in m else None,
                "params": params,
                **({"fw": {"build": build}} if build else {}),
            })

    # The firmware builds' custom effects: each is stored in a preset as the (mono) stock model it takes over
    host_params = json.loads((Path(__file__).with_name("host_params.json")).read_text())
    by_id = {m["id"]: m for m in models}
    # DSP load: HX Edit's figures are percent; the builds give Entry 0 costs. Scale by the amps, which have both.
    ratios = [by_id[a]["load"] / c for a, _i, c in fw.STOMP_AMPS if a in by_id and by_id[a].get("load")]
    per_cost = statistics.median(ratios) if ratios else None
    for cm in fw.custom_models(every):
        host = cm["fw"]["host"]
        hp = host_params[cm["fw"]["hostSymbol"]]
        cm["fw"]["hostParams"] = [{"name": p["name"], "slot": p["slot"], "valueType": FW_TYPE[p["type"]]} for p in hp]
        cm["group"] = CATEGORY_LABELS[cm["category"]]
        cm["load"] = round(cm["fw"]["cost"] * per_cost, 1) if per_cost else None
        models.append(cm)
        # the stock host loses its mono version in that build
        if host in by_id:
            by_id[host].setdefault("fw", {})["monoTakenBy"] = {"build": cm["fw"]["build"], "id": cm["id"]}

    templates = {k: json.loads((res / f).read_text()) for k, f in TEMPLATES.items()}
    app_version = None
    info = app / "Contents" / "Info.plist"
    if info.exists():
        import subprocess
        try:
            app_version = subprocess.run(
                ["plutil", "-extract", "CFBundleShortVersionString", "raw", str(info)],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            pass

    # Display formatting (units, scaling, enum labels) keyed by a param's displayType
    used = {p["displayType"] for m in models for p in m["params"] if "displayType" in p} - set(FW_CONTROLS)
    controls_path = res / "HelixControls.json"
    controls = {}
    if controls_path.exists():
        all_controls = json.loads(controls_path.read_text())
        pending = list(used)
        while pending:  # follow "alias" links so every referenced format is included
            k = pending.pop()
            if k in controls or k not in all_controls:
                continue
            controls[k] = all_controls[k]
            if "alias" in controls[k]:
                pending.append(controls[k]["alias"])
    controls.update(FW_CONTROLS)

    data = {
        "source": str(app), "hxEditVersion": app_version,
        "models": models, "controls": controls, "templates": templates, "builds": list(fw.BUILDS),
    }
    out = Path(__file__).with_name("hx-data.js")
    out.write_text("window.HX_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    n_fw = sum(1 for m in models if "fw" in m and "build" in m["fw"])
    print(f"Wrote {out.name}: {len(models)} models from HX Edit {app_version} ({n_fw} from the firmware builds; "
          f"DSP scale {per_cost and round(per_cost * 1000, 3)}%/1000 cost, from {len(ratios)} amps)")


if __name__ == "__main__":
    main()
