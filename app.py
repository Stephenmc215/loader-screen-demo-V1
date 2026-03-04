import random
from dataclasses import dataclass

import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ============================================================
# Loader Screen Demo (V8 FIXED)
# Fixes:
# 1) Seed is set BEFORE pads are initialized (stable per session)
# 2) HTML table rows are single-line strings (avoids "<tr>..." printing as text)
# 3) Arriving Soon counts flights within 60s (not all flights)
# ============================================================

st.set_page_config(page_title="Loader Screen Demo", layout="wide")

# -----------------------------
# Styling (banner + big grid + coloured action cells)
# -----------------------------
st.markdown(
    """
    <style>
      .block-container { padding: 0.35rem 0.8rem !important; max-width: 100% !important; }

      .banner {
        border-radius: 18px;
        padding: 20px;
        text-align:center;
        color:white;
        font-weight:900;
        font-size:50px;
        margin-bottom:18px;
        background:#1f3a8a;
      }

      .metrics-col { padding-top: 8px; }
      .metric-label { font-size: 18px; color:#111827; margin-top: 28px; }
      .metric-value { font-size: 58px; font-weight: 900; line-height: 1.0; color:#111827; }

      .grid-wrap { border: 1px solid #e5e7eb; border-radius: 14px; overflow: hidden; background: white; }
      table.grid { width: 100%; border-collapse: collapse; table-layout: fixed; }
      table.grid th {
        text-align: left;
        font-size: 26px;
        padding: 16px 16px;
        border-bottom: 1px solid #e5e7eb;
        background: #f9fafb;
        color: #6b7280;
        font-weight: 700;
      }
      table.grid td {
        font-size: 34px;
        padding: 18px 16px;
        border-bottom: 1px solid #eef2f7;
        color: #111827;
      }
      table.grid tr:last-child td { border-bottom: none; }

      /* Column widths: 4-col grid */
      .col-pad { width: 14%; }
      .col-order { width: 22%; }
      .col-rt { width: 22%; }
      .col-action { width: 42%; }

      /* Action colour blocks (match PDF mapping) */
      .act-none { background: transparent; }
      .act-blue { background: #dbeafe; color: #111827; font-weight: 900; }
      .act-yellow { background: #fde68a; color: #111827; font-weight: 900; }
      .act-orange { background: #fdba74; color: #111827; font-weight: 900; }
      .act-red { background: #f87171; color: #ffffff; font-weight: 900; }

      /* Make action cells look like "badges" but full-cell */
      td.action-cell { border-left: 1px solid #eef2f7; }

    </style>
    """,
    unsafe_allow_html=True,
)

TICK_SECONDS = 2
st_autorefresh(interval=TICK_SECONDS * 1000, key="loader_refresh")

# -----------------------------
# Simulation (ground-only issues + fixing delay)
# -----------------------------
@dataclass
class Pad:
    pad: str
    order: int
    phase: str   # FLIGHT/LANDING/LOADING/FIXING
    t: int       # seconds remaining in current phase
    action: str  # "", numeric next order, or issue text
    fault: bool

FLIGHT_MIN = 120
FLIGHT_MAX = 300
LANDING = 10
LOADING = 60
FIXING = 30

ISSUES = ["Repress Pad", "Change Cassette", "Reboot Drone", "Change Drone"]

def next_order(n: int) -> int:
    return 100 if n + 3 > 999 else n + 3

def rand_flight() -> int:
    return random.randint(FLIGHT_MIN, FLIGHT_MAX)

def init_pads(n: int = 8):
    pads = []
    o = 100
    for i in range(n):
        pads.append(Pad(chr(65 + i), o, "FLIGHT", random.randint(20, rand_flight()), "", False))
        o = next_order(o)
    return pads

# IMPORTANT: seed BEFORE any random-generated state is created
if "seed" not in st.session_state:
    st.session_state.seed = random.randint(1, 10_000_000)
random.seed(st.session_state.seed)

if "pads" not in st.session_state:
    st.session_state.pads = init_pads(8)

pads = st.session_state.pads

# Step simulation
for p in pads:
    p.t = max(0, p.t - TICK_SECONDS)

    if p.phase == "FLIGHT" and p.t == 0:
        p.phase = "LANDING"
        p.t = LANDING
        p.action = ""
        p.fault = False

    elif p.phase == "LANDING" and p.t == 0:
        p.phase = "LOADING"
        p.t = LOADING
        p.action = str(next_order(p.order))  # default task: next order to load
        p.fault = False

    elif p.phase == "LOADING":
        # Issues only happen on the ground (during loading)
        if not p.fault and random.random() < 0.04:
            p.fault = True
            p.phase = "FIXING"
            p.t = FIXING
            p.action = random.choice(ISSUES)

        # If loading finished and no fault, take off
        if p.t == 0 and not p.fault:
            p.phase = "FLIGHT"
            p.order = next_order(p.order)
            p.t = rand_flight()
            p.action = ""

    elif p.phase == "FIXING" and p.t == 0:
        # After fixing, take off
        p.phase = "FLIGHT"
        p.order = next_order(p.order)
        p.t = rand_flight()
        p.action = ""
        p.fault = False

# -----------------------------
# Banner logic
# -----------------------------
def severity(action: str) -> int:
    if action == "Change Drone":
        return 4
    if action == "Reboot Drone":
        return 3
    if action == "Change Cassette":
        return 2
    if action == "Repress Pad":
        return 1
    return 0

best = {"sev": 0, "pad": "", "action": ""}
for p in pads:
    sev = severity(p.action)
    if sev > best["sev"]:
        best = {"sev": sev, "pad": p.pad, "action": p.action}

if best["sev"] >= 4:
    banner_text = f"CRITICAL: {best['action']} (Pad {best['pad']})"
    banner_bg = "#b91c1c"
elif best["sev"] == 3:
    banner_text = f"HIGH: {best['action']} (Pad {best['pad']})"
    banner_bg = "#b45309"
else:
    banner_text = "RPP: 2 mins"
    banner_bg = "#1f3a8a"

st.markdown(f"<div class='banner' style='background:{banner_bg};'>{banner_text}</div>", unsafe_allow_html=True)

# -----------------------------
# Layout
# -----------------------------
left, right = st.columns([1, 4], gap="large")

with left:
    at_base = sum(1 for p in pads if p.phase in ("LANDING", "LOADING", "FIXING"))
    arriving = sum(1 for p in pads if p.phase == "FLIGHT" and p.t <= 60)

    st.markdown("<div class='metrics-col'>", unsafe_allow_html=True)
    st.markdown("<div class='metric-label'>At Base</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric-value'>{at_base}</div>", unsafe_allow_html=True)

    st.markdown("<div class='metric-label'>Arriving Soon</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric-value'>{arriving}</div>", unsafe_allow_html=True)

    st.markdown("<div class='metric-label'>Cancelled</div>", unsafe_allow_html=True)
    st.markdown("<div class='metric-value'>0</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

def action_class(a: str) -> str:
    if a == "Change Drone":
        return "act-red"
    if a == "Reboot Drone":
        return "act-orange"
    if a == "Change Cassette":
        return "act-yellow"
    if a == "Repress Pad":
        return "act-blue"
    return "act-none"

with right:
    # Build HTML table (single-line rows for reliability)
    header = (
        '<div class="grid-wrap">'
        '<table class="grid">'
        '<thead><tr>'
        '<th class="col-pad">Pad</th>'
        '<th class="col-order">Order</th>'
        '<th class="col-rt">RT (s)</th>'
        '<th class="col-action">Next Action</th>'
        '</tr></thead>'
        '<tbody>'
    )

    rows_html = []
    for p in pads:
        rt = "" if p.phase in ("LANDING", "LOADING", "FIXING") else str(p.t)
        cls = action_class(p.action)
        action_txt = p.action or ""
        rows_html.append(
            f"<tr><td>{p.pad}</td><td>{p.order}</td><td>{rt}</td><td class='action-cell {cls}'>{action_txt}</td></tr>"
        )

    footer = "</tbody></table></div>"
    st.markdown(header + "".join(rows_html) + footer, unsafe_allow_html=True)
