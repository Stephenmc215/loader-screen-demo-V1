import random
from dataclasses import dataclass
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Loader Wall Screen Demo", layout="wide")

# Rerun the script every N milliseconds (this is what makes seconds tick down)
TICK_SECONDS = 2
st_autorefresh(interval=TICK_SECONDS * 1000, key="tick")

# -----------------------------
# Simulation model
# -----------------------------
@dataclass
class PadState:
    pad: str
    order: int
    storage: str     # HEAT/SHELF/FREEZER
    phase: str       # FLIGHT/LANDING/LOADING/FIXING
    t: int           # seconds remaining in current phase
    action: str      # issue text, or ""
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

def pick_storage() -> str:
    r = random.random()
    if r < 0.15:
        return "FREEZER"
    if r < 0.40:
        return "HEAT"
    return "SHELF"

def storage_emoji(storage: str) -> str:
    return {"HEAT": "🔥", "SHELF": "📦", "FREEZER": "🧊"}.get(storage, "")

def severity(action: str) -> int:
    return {"Repress Pad": 1, "Change Cassette": 2, "Reboot Drone": 3, "Change Drone": 4}.get(action, 0)

def init_pads(n: int = 8):
    pads = []
    o = 100
    for i in range(n):
        pads.append(PadState(chr(65 + i), o, pick_storage(), "FLIGHT", random.randint(20, rand_flight()), "", False))
        o = next_order(o)
    return pads

# Each viewer gets their own simulation state (normal on Streamlit)
if "pads" not in st.session_state:
    st.session_state.seed = random.randint(1, 10_000_000)
    random.seed(st.session_state.seed)
    st.session_state.pads = init_pads(8)

pads = st.session_state.pads

# -----------------------------
# Step simulation
# -----------------------------
for p in pads:
    p.t = max(0, p.t - TICK_SECONDS)

    if p.phase == "FLIGHT" and p.t == 0:
        p.phase = "LANDING"
        p.t = LANDING
        p.action = ""
        p.fault = False

    elif p.phase == "LANDING" and p.t == 0:
        # Craft has landed and is ready to be loaded with the NEXT order
        p.phase = "LOADING"
        p.t = LOADING
        p.order = next_order(p.order)     # advance here so it's obvious it's working
        p.storage = pick_storage()
        p.action = ""
        p.fault = False

    elif p.phase == "LOADING":
        # Ground-only issues
        if not p.fault and random.random() < 0.04:
            p.fault = True
            p.phase = "FIXING"
            p.t = FIXING
            p.action = random.choice(ISSUES)

        # Finished loading with no fault => take off (same order continues in flight)
        if p.t == 0 and not p.fault:
            p.phase = "FLIGHT"
            p.t = rand_flight()
            p.action = ""

    elif p.phase == "FIXING" and p.t == 0:
        p.phase = "FLIGHT"
        p.t = rand_flight()
        p.action = ""
        p.fault = False

# -----------------------------
# Priority rules / UI selection
# -----------------------------
IMMINENT = 15
LANDING_SOON = 30

imminent = [p for p in pads if p.phase == "FLIGHT" and p.t <= IMMINENT]
landing_soon = [p for p in pads if p.phase == "FLIGHT" and p.t <= LANDING_SOON]

issues = [p for p in pads if severity(p.action) > 0]
critical = [p for p in issues if severity(p.action) >= 4]
noncrit_issues = [p for p in issues if 0 < severity(p.action) < 4]

loading_now = [p for p in pads if p.phase in ("LOADING", "FIXING")]

best_issue = max(issues, key=lambda x: severity(x.action), default=None)
if best_issue and severity(best_issue.action) >= 4:
    top_text = f"CRITICAL: {best_issue.action} (Pad {best_issue.pad})"
    top_bg = "#b91c1c"
elif best_issue and severity(best_issue.action) == 3:
    top_text = f"HIGH: {best_issue.action} (Pad {best_issue.pad})"
    top_bg = "#b45309"
else:
    top_text = "RPP: 2 mins"
    top_bg = "#1f3a8a"

beacon_title = "RPP"
beacon_pad = ""
beacon_sub = "2 mins"
beacon_order = ""
beacon_hint = "No urgent arrivals or issues"
beacon_class = "u-neutral"
pulse = False

if imminent:
    p = min(imminent, key=lambda x: x.t)
    beacon_title = "GO TO PAD"
    beacon_pad = p.pad
    beacon_sub = f"Landing in {p.t}s"
    beacon_order = f"{storage_emoji(p.storage)} {p.order}"
    beacon_hint = "Prepare to receive and load on landing"
    if p.t < 10:
        beacon_class = "u-red"
        pulse = True
    elif p.t <= 30:
        beacon_class = "u-amber"
elif critical:
    p = max(critical, key=lambda x: severity(x.action))
    beacon_title = "ATTENTION REQUIRED"
    beacon_pad = p.pad
    beacon_sub = p.action
    beacon_order = f"{storage_emoji(p.storage)} {p.order}"
    beacon_hint = "Resolve immediately while at base"
    beacon_class = "u-red"
elif loading_now:
    p = min(loading_now, key=lambda x: x.t)
    beacon_title = "LOAD NOW"
    beacon_pad = p.pad
    beacon_sub = f"{'Fixing' if p.phase=='FIXING' else 'Loading'} • {p.t}s left"
    beacon_order = f"{storage_emoji(p.storage)} {p.order}"
    beacon_hint = "Active turnaround on ground"
    beacon_class = "u-amber"
elif noncrit_issues:
    p = max(noncrit_issues, key=lambda x: severity(x.action))
    beacon_title = "ATTENTION REQUIRED"
    beacon_pad = p.pad
    beacon_sub = p.action
    beacon_order = f"{storage_emoji(p.storage)} {p.order}"
    beacon_hint = "Resolve while at base"
    beacon_class = "u-amber"
elif landing_soon:
    p = min(landing_soon, key=lambda x: x.t)
    beacon_title = "UP NEXT"
    beacon_pad = p.pad
    beacon_sub = f"Landing in {p.t}s"
    beacon_order = f"{storage_emoji(p.storage)} {p.order}"
    beacon_hint = "Next arrival approaching"

def item_html(p: PadState, label: str, meta: str, tag: str) -> str:
    return f"""<div class="item {tag}">
      <div class="item-left">
        <div class="pad">{p.pad}</div>
        <div class="desc">{label}</div>
      </div>
      <div class="meta">{meta}</div>
    </div>"""

loading_items = ""
for p in sorted(loading_now, key=lambda x: x.t)[:4]:
    label = "Fixing" if p.phase == "FIXING" else "Loading"
    meta = f"{p.t}s • {storage_emoji(p.storage)} {p.order}"
    loading_items += item_html(p, label, meta, "tag-amber")

critical_items = "".join(
    item_html(p, p.action, f"{storage_emoji(p.storage)} {p.order}", "tag-red")
    for p in sorted(critical, key=lambda x: severity(x.action), reverse=True)
)

issues_items = "".join(
    item_html(p, p.action, f"{storage_emoji(p.storage)} {p.order}", "tag-blue")
    for p in sorted(noncrit_issues, key=lambda x: severity(x.action), reverse=True)
)

landing_items = ""
for p in sorted([p for p in pads if p.phase == "FLIGHT"], key=lambda x: x.t)[:3]:
    landing_items += item_html(p, "Landing", f"{p.t}s • {storage_emoji(p.storage)} {p.order}", "tag-orange")

busy_pads = {p.pad for p in loading_now} | {p.pad for p in issues}
idle_candidates = [p for p in pads if p.pad not in busy_pads]
idle_items = ""
for p in sorted(idle_candidates, key=lambda x: x.pad)[:3]:
    meta = "In flight" if p.phase == "FLIGHT" else "At base"
    idle_items += item_html(p, "Idle", meta, "tag-gray")

at_base = sum(1 for p in pads if p.phase in ("LANDING", "LOADING", "FIXING"))
arriving = sum(1 for p in pads if p.phase == "FLIGHT")
cancelled = 0

sections_html = ""
if critical_items:
    sections_html += f"""<div class="section">
      <div class="section-h h-critical">🔴 CRITICAL</div>
      <div class="items">{critical_items}</div>
    </div>"""
if issues_items:
    sections_html += f"""<div class="section">
      <div class="section-h h-issues">⚠️ ATTENTION</div>
      <div class="items">{issues_items}</div>
    </div>"""
if loading_items:
    sections_html += f"""<div class="section">
      <div class="section-h h-loading">🟡 LOADING NOW</div>
      <div class="items">{loading_items}</div>
    </div>"""

sections_html += f"""<div class="section">
  <div class="section-h h-landing">🟠 LANDING SOON</div>
  <div class="items">{landing_items}</div>
</div>"""

if idle_items:
    sections_html += f"""<div class="section">
      <div class="section-h h-idle">⚪ IDLE</div>
      <div class="items">{idle_items}</div>
    </div>"""

pulse_class = "pulse" if pulse else ""
pad_line = f"<div class='beacon-pad'>➡ {beacon_pad}</div>" if beacon_pad else ""
order_line = ""
if beacon_order:
    parts = beacon_order.split(" ", 1)
    emo = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    order_line = f"<div class='beacon-order'><span class='emo'>{emo}</span>{rest}</div>"

page = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  html, body {{ height: 100%; }}
  body {{ margin: 0; padding: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background:#ffffff; }}
  .topbar {{
    border-radius: 18px;
    padding: 14px 18px;
    text-align: center;
    color: #ffffff;
    font-weight: 900;
    font-size: 46px;
    margin: 6px 8px 12px 8px;
    background: {top_bg};
  }}
  .wall {{
    display: grid;
    grid-template-columns: 40% 60%;
    gap: 14px;
    align-items: stretch;
    padding: 0 8px 8px 8px;
  }}

  .beacon {{
    border-radius: 18px;
    border: 1px solid #e5e7eb;
    padding: 18px 22px;
    background: #ffffff;
    height: calc(100vh - 130px);
    display: flex;
    flex-direction: column;
    justify-content: center;
  }}
  .beacon-title {{ font-size: 30px; font-weight: 900; color: #111827; letter-spacing: 0.02em; margin-bottom: 14px; }}
  .beacon-pad {{ font-size: 150px; font-weight: 1000; line-height: 1.0; margin: 0; color:#111827; }}
  .beacon-sub {{ font-size: 48px; font-weight: 900; margin-top: 8px; color:#111827; }}
  .beacon-order {{ margin-top: 12px; font-size: 40px; font-weight: 800; color: #111827; }}
  .beacon-order .emo {{ font-size: 38px; margin-right: 12px; }}
  .beacon-hint {{ margin-top: 12px; font-size: 24px; color: #374151; font-weight: 700; }}

  .u-neutral {{ background: #ffffff; }}
  .u-amber {{ background: #fff7ed; }}
  .u-red {{ background: #fff1f2; }}
  .pulse {{ border: 5px solid #b91c1c !important; animation: pulse 1.0s infinite; }}
  @keyframes pulse {{
    0% {{ box-shadow: 0 0 0 0 rgba(185, 28, 28, 0.55); }}
    70% {{ box-shadow: 0 0 0 16px rgba(185, 28, 28, 0.0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(185, 28, 28, 0.0); }}
  }}

  .stack {{ height: calc(100vh - 130px); display:flex; flex-direction:column; gap:10px; }}
  .section {{ border-radius: 16px; border: 1px solid #e5e7eb; overflow:hidden; background:#ffffff; }}
  .section-h {{ padding: 10px 12px; font-size: 18px; font-weight: 900; letter-spacing: 0.02em; border-bottom: 1px solid #eef2f7; }}
  .h-critical {{ background: #fee2e2; color:#7f1d1d; }}
  .h-landing {{ background: #ffedd5; color:#7c2d12; }}
  .h-issues {{ background: #e0e7ff; color:#1e3a8a; }}
  .h-loading {{ background: #fef9c3; color:#854d0e; }}
  .h-idle {{ background: #f3f4f6; color:#111827; }}

  .items {{ padding: 8px 10px; display:flex; flex-direction:column; gap:8px; }}
  .item {{ border-radius: 12px; padding: 10px 12px; border: 1px solid #eef2f7; display:flex; align-items:center; justify-content:space-between; gap:10px; }}
  .item-left {{ display:flex; align-items:baseline; gap:10px; }}
  .pad {{ font-size: 30px; font-weight: 1000; color:#111827; min-width: 36px; }}
  .desc {{ font-size: 18px; font-weight: 800; color:#111827; }}
  .meta {{ font-size: 18px; font-weight: 900; color:#111827; }}

  .tag-red {{ background:#fecaca; border-color:#fca5a5; }}
  .tag-orange {{ background:#ffedd5; border-color:#fdba74; }}
  .tag-blue {{ background:#dbeafe; border-color:#93c5fd; }}
  .tag-amber {{ background:#fef3c7; border-color:#fcd34d; }}
  .tag-gray {{ background:#f3f4f6; border-color:#e5e7eb; }}

  .footer {{
    margin-top: auto;
    border-radius: 16px;
    border: 1px solid #e5e7eb;
    background:#ffffff;
    padding: 12px 14px;
    display: flex;
    justify-content: space-between;
    font-size: 24px;
    font-weight: 1000;
    color:#111827;
  }}
  .k {{ color:#6b7280; font-weight: 900; margin-right: 10px; }}
</style>
</head>
<body>
  <div class="topbar">{top_text}</div>

  <div class="wall">
    <div class="beacon {beacon_class} {pulse_class}">
      <div class="beacon-title">{beacon_title}</div>
      {pad_line}
      <div class="beacon-sub">{beacon_sub}</div>
      {order_line}
      <div class="beacon-hint">{beacon_hint}</div>
    </div>

    <div class="stack">
      {sections_html}
      <div class="footer">
        <div><span class="k">At Base</span>{at_base}</div>
        <div><span class="k">Arriving</span>{arriving}</div>
        <div><span class="k">Cancelled</span>{cancelled}</div>
      </div>
    </div>
  </div>
</body>
</html>
"""

components.html(page, height=920, scrolling=False)

    _render_section("🟡 LOADING NOW", "h-loading", loading_now, "loading", max_items=3)
    _render_section("🟠 LANDING SOON", "h-landing", landing_soon, "landing", max_items=4)
    _render_section("⚪ IN FLIGHT", "h-flight", inflight, "flight", max_items=6)

# Footer counts
at_base = sum(1 for p in pads if p.phase in ("LOADING", "FIXING") and p.next_order is not None)
arriving = sum(1 for p in pads if p.phase == "FLIGHT" and (_rt_seconds(p) or 999999) <= 60)
cancelled = 0

st.markdown(
    f"""
<div class="footer">
  <div><span class="k">At Base</span>{at_base}</div>
  <div><span class="k">Arriving</span>{arriving}</div>
  <div><span class="k">Cancelled</span>{cancelled}</div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown("</div>", unsafe_allow_html=True)  # right
st.markdown("</div>", unsafe_allow_html=True)  # grid
