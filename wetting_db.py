"""
Wetting measurement DB (KOKI SV-PBF-304P flux)

Table columns:
- Temperature (degC): 250, 260, 270, 280, 290
- fMAX: maximum wetting force (mN) where higher is better
- T0: wetting time / speed metric (sec) where lower is better

Each record: name (BD, solder_db 스타일), comp wt%, data[tempC] = {fmax_mn, t0_s}.
"""

WETTING_TEMPS_C = [250, 260, 270, 280, 290]

WETTING_DB = [
    {"name": "Sn0.7Cu", "comp": {"Cu": 0.7, "Sn": 99.3}, "data": {250: {"fmax_mn": 0.87, "t0_s": 2.05}, 260: {"fmax_mn": 1.87, "t0_s": 0.93}, 270: {"fmax_mn": 2.31, "t0_s": 0.59}, 280: {"fmax_mn": 2.50, "t0_s": 0.43}, 290: {"fmax_mn": 2.43, "t0_s": 0.42}}},
    {"name": "Sn0.5Cu", "comp": {"Cu": 0.5, "Sn": 99.5}, "data": {250: {"fmax_mn": 1.23, "t0_s": 1.77}, 260: {"fmax_mn": 2.01, "t0_s": 0.88}, 270: {"fmax_mn": 2.33, "t0_s": 0.64}, 280: {"fmax_mn": 2.44, "t0_s": 0.48}, 290: {"fmax_mn": 2.52, "t0_s": 0.38}}},
    {"name": "Sn0.3Ag0.7Cu", "comp": {"Ag": 0.3, "Cu": 0.7, "Sn": 99.0}, "data": {250: {"fmax_mn": 1.88, "t0_s": 1.24}, 260: {"fmax_mn": 2.33, "t0_s": 0.71}, 270: {"fmax_mn": 2.42, "t0_s": 0.53}, 280: {"fmax_mn": 2.50, "t0_s": 0.46}, 290: {"fmax_mn": 2.50, "t0_s": 0.39}}},
    {"name": "Sn1.0Ag0.5Cu", "comp": {"Ag": 1.0, "Cu": 0.5, "Sn": 98.5}, "data": {250: {"fmax_mn": 2.05, "t0_s": 0.86}, 260: {"fmax_mn": 2.36, "t0_s": 0.63}, 270: {"fmax_mn": 2.42, "t0_s": 0.51}, 280: {"fmax_mn": 2.46, "t0_s": 0.40}, 290: {"fmax_mn": 2.50, "t0_s": 0.33}}},
    {"name": "Sn3.0Ag0.5Cu", "comp": {"Ag": 3.0, "Cu": 0.5, "Sn": 96.5}, "data": {250: {"fmax_mn": 2.32, "t0_s": 0.71}, 260: {"fmax_mn": 2.42, "t0_s": 0.53}, 270: {"fmax_mn": 2.47, "t0_s": 0.41}, 280: {"fmax_mn": 2.52, "t0_s": 0.33}, 290: {"fmax_mn": 2.60, "t0_s": 0.30}}},
    # 92조성 (NS-F051, 젖음성 평가 보고 260608) — Sn-0.3Ag-0.5Cu-3Bi
    {"name": "Sn0.3Ag0.5Cu3Bi", "comp": {"Ag": 0.3, "Cu": 0.5, "Bi": 3.0, "Sn": 96.2}, "data": {250: {"fmax_mn": 2.36, "t0_s": 0.75}, 260: {"fmax_mn": 2.47, "t0_s": 0.58}, 270: {"fmax_mn": 2.43, "t0_s": 0.49}, 280: {"fmax_mn": 2.47, "t0_s": 0.41}, 290: {"fmax_mn": 2.44, "t0_s": 0.36}}},
]
