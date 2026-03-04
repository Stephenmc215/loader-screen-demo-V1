import random
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

import streamlit as st

# ----------------------------
# Wall Screen – Loader Demo
# ----------------------------
# Single-file Streamlit app with a lightweight simulation.
# Orders increment by 3 (100..999) and wrap back to 100.
# Issues only occur while craft is on-ground (loading window).
# Landing soon list only shows pads within 60s of landing.

st.set_page_config(page_title="Loader Wall Screen Demo", layout="wide")

PADS = list("ABCDEFGH")
ORDER_MIN = 100
ORDER_MAX = 999
ORDER_STEP = 3

# Timing
LOAD_SECONDS = 60
FIX_EXTRA_SECONDS = 30  # extra time available if an issue occurs while on ground
FLIGHT_MIN = 120        # 2 min
FLIGHT_MAX = 300        # 5 min
LANDING_MIN = 5
LANDING_MAX = 60
LANDING_SOON_THRESHOLD = 60

# Weather top bar fallback (when no critical banner)
WEATHER_ROTATE_SECONDS = 6
WEATHER_MESSAGES = [
    "RPP: 2 mins",
    "Weather: Visibility OK",
    "Weather: Light rain",
    "Weather: Wind 12kt",
]

# Storage emoji mapping (bag location)
STORAGE_EMOJI = ["🔥", "📦", "🧊"]  # heat / shelf / freezer

# Issue catalog (from your PDF concept). Only triggered on ground.
ISSUES: List[Tuple[str, str]] = [
    ("critical", "Change Drone"),
    ("critical", "Pad Blocked – do not assign"),
    ("attention", "Repress Pad"),
    ("attention", "Change Cassette"),
    ("attention", "Reboot Drone"),
    ("attention", "Comms lost"),
    ("attention", "Unit expired"),
]

ISSUE_CHANCE = 0.22  # chance that a pad will get an issue during each on-ground window
CRITICAL_WEIGHT = 0.30  # of issues, how many are critical


def next_order(order_id: int) -> int:
    nxt = order_id + ORDER_STEP
    if nxt > ORDER_MAX:
        return ORDER_MIN
    return nxt


def pick_storage(rng: random.Random) -> str:
    return rng.choice(STORAGE_EMOJI)


@dataclass
class PadState:
    pad: str
    phase: str  # FLIGHT | LANDING | LOADING
    remaining: int  # seconds remaining in current phase
    order_next: int  # "next action" order to be loaded on next landing
    storage: str  # emoji indicating where the bag is
    issue: Optional[str] = None  # issue text (only relevant on ground)
    severity: Optional[str] = None  # critical | attention
    fix_left: int = 0  # seconds remaining in fix window (subset of LOADING)


def init_state() -> Dict[str, PadState]:
    seed = int(time.time())  # different per run, stable within session_state
    rng = random.Random(seed)
    base_order = rng.randrange(ORDER_MIN, ORDER_MAX + 1, ORDER_STEP)

    pads: Dict[str, PadState] = {}
    for i, p in enumerate(PADS):
        order_id = base_order + i * ORDER_STEP
        while order_id > ORDER_MAX:
            order_id = ORDER_MIN + (order_id - ORDER_MAX - 1)
        pads[p] = PadState(
            pad=p,
            phase="FLIGHT",
            remaining=rng.randint(FLIGHT_MIN, FLIGHT_MAX),
            order_next=order_id,
            storage=pick_storage(rng),
        )
    return {
        "seed": seed,
        "pads": pads,
        "weather_idx": 0,
        "weather_next": time.time() + WEATHER_ROTATE_SECONDS,
        "last_tick": time.time(),
    }


def maybe_issue(rng: random.Random) -> Tuple[Optional[str], Optional[str]]:
    if rng.random() > ISSUE_CHANCE:
        return None, None
    if rng.random() < CRITICAL_WEIGHT:
        candidates = [t for sev, t in ISSUES if sev == "critical"]
        return rng.choice(candidates), "critical"
    candidates = [t for sev, t in ISSUES if sev == "attention"]
    return rng.choice(candidates), "attention"


def tick_sim(state: Dict) -> None:
    now = time.time()
    last = state.get("last_tick", now)
    dt = int(now - last)
    if dt <= 0:
        return
    state["last_tick"] = now

    rng = random.Random(state["seed"])
    # advance rng based on time to keep determinism-ish per session
    rng.jumpahead = None  # (compat shim; does nothing, keeps linter quiet)

    pads: Dict[str, PadState] = state["pads"]

    for _ in range(dt):
        for p in pads.values():
            p.remaining = max(0, p.remaining - 1)

            # FLIGHT -> LANDING
            if p.phase == "FLIGHT" and p.remaining == 0:
                p.phase = "LANDING"
                p.remaining = rng.randint(LANDING_MIN, LANDING_MAX)

            # LANDING -> LOADING (touchdown)
            elif p.phase == "LANDING" and p.remaining == 0:
                p.phase = "LOADING"
                p.issue, p.severity = maybe_issue(rng)
                p.fix_left = FIX_EXTRA_SECONDS if p.issue else 0
                p.remaining = LOAD_SECONDS + (FIX_EXTRA_SECONDS if p.issue else 0)

            # LOADING countdown (first FIX_EXTRA_SECONDS used for fixing if issue)
            elif p.phase == "LOADING":
                if p.issue and p.fix_left > 0:
                    p.fix_left = max(0, p.fix_left - 1)

                # LOADING -> FLIGHT (takeoff)
                if p.remaining == 0:
                    p.phase = "FLIGHT"
                    p.remaining = rng.randint(FLIGHT_MIN, FLIGHT_MAX)
                    # once loaded & departed, immediately plan the NEXT action order
                    p.order_next = next_order(p.order_next)
                    p.storage = pick_storage(rng)
                    p.issue = None
                    p.severity = None
                    p.fix_left = 0

    # rotate weather when no critical banner is showing
    if time.time() >= state.get("weather_next", 0):
        state["weather_idx"] = (state["weather_idx"] + 1) % len(WEATHER_MESSAGES)
        state["weather_next"] = time.time() + WEATHER_ROTATE_SECONDS


def pick_primary(pads: List[PadState]) -> Tuple[str, Optional[PadState], str]:
    """
    Priority rules for LEFT panel:
    1) Critical issue on ground
    2) Attention issue on ground
    3) Any on-ground loading
    4) Soonest landing
    5) Default (weather/RPP)
    """
    critical = [p for p in pads if p.phase == "LOADING" and p.severity == "critical" and p.issue]
    if critical:
        p = sorted(critical, key=lambda x: x.pad)[0]
        return "critical", p, p.issue or "Issue"

    attention = [p for p in pads if p.phase == "LOADING" and p.severity == "attention" and p.issue]
    if attention:
        p = sorted(attention, key=lambda x: x.pad)[0]
        return "attention", p, p.issue or "Attention"

    loading = [p for p in pads if p.phase == "LOADING" and not p.issue]
    if loading:
        p = sorted(loading, key=lambda x: x.remaining)[0]
        return "loading", p, "Load now"

    landing = [p for p in pads if p.phase == "LANDING" and p.remaining <= LANDING_SOON_THRESHOLD]
    if landing:
        p = sorted(landing, key=lambda x: x.remaining)[0]
        return "landing", p, "Landing soon"

    return "default", None, ""


def item_html(p: PadState, kind: str, label: str, right_text: str) -> str:
    tag_class = {
        "critical": "tag-red",
        "attention": "tag-blue",
        "loading": "tag-yellow",
        "landing": "tag-orange",
        "flight": "tag-gray",
    }.get(kind, "tag-gray")

    meta = right_text

    return f"""
<div class="item {tag_class}">
  <div class="item-left">
    <div class="pad">{p.pad}</div>
    <div class="desc">{label}</div>
  </div>
  <div class="meta">{meta}</div>
</div>
"""


def top_banner(pads: List[PadState], state: Dict) -> Tuple[str, str]:
    # Banner prioritises critical issues; otherwise show rotating weather/RPP.
    crit = [p for p in pads if p.phase == "LOADING" and p.severity == "critical" and p.issue]
    if crit:
        p = sorted(crit, key=lambda x: x.pad)[0]
        return "banner-red", f"CRITICAL: {p.issue} (Pad {p.pad})"
    return "banner-blue", WEATHER_MESSAGES[state["weather_idx"]]


CSS = """
<style>
:root{
  --bg:#ffffff;
  --ink:#0b1320;
  --muted:#5b6472;
  --card:#ffffff;
  --line:#e8ebf0;

  --blue:#1f3f8a;
  --red:#b51d1d;

  --tag_red_bg:#fbe3e3;
  --tag_red_line:#efb1b1;

  --tag_blue_bg:#e7efff;
  --tag_blue_line:#b9d3ff;

  --tag_yellow_bg:#fff7cf;
  --tag_yellow_line:#f0e39c;

  --tag_orange_bg:#ffedd7;
  --tag_orange_line:#f4c99a;

  --tag_gray_bg:#f4f5f7;
  --tag_gray_line:#e1e3e8;
}

.main .block-container{padding-top:1rem; padding-bottom:1rem; max-width: 1400px;}
body{background:var(--bg); color:var(--ink);}

.banner{
  border-radius:20px;
  padding:22px 22px;
  font-weight:900;
  text-align:center;
  font-size:52px;
  letter-spacing:0.5px;
  margin-bottom:18px;
  color:white;
}
.banner-blue{background:var(--blue);}
.banner-red{background:var(--red);}

.shell{
  display:flex;
  gap:18px;
  align-items:stretch;
}

.left{
  flex:0 0 40%;
  background:#fff6ea;
  border:2px solid #f1dcc7;
  border-radius:18px;
  padding:26px 26px;
  min-height: 72vh;
  display:flex;
  flex-direction:column;
  justify-content:center;
  overflow:hidden;
}
.left.urgent{
  border:4px solid var(--red);
  background:#fff0f0;
}
.left h2{
  margin:0 0 14px 0;
  font-size:44px;
  letter-spacing:1px;
}
.bigrow{
  display:flex;
  gap:20px;
  align-items:center;
}
.arrow{
  font-size:120px;
  font-weight:900;
  line-height:1;
}
.padbig{
  font-size:180px;
  font-weight:1000;
  line-height:0.9;
}
.primaryline{
  margin-top:10px;
  font-size:64px;
  font-weight:1000;
  line-height:1.05;
}
.subline{
  margin-top:14px;
  font-size:28px;
  font-weight:700;
  color:var(--muted);
}
.orderline{
  margin-top:18px;
  display:flex;
  gap:14px;
  align-items:center;
  font-size:46px;
  font-weight:1000;
}

.right{
  flex:0 0 60%;
  display:flex;
  flex-direction:column;
  gap:14px;
  min-height: 72vh;
}

.section{
  border:1px solid var(--line);
  border-radius:14px;
  overflow:hidden;
  background:var(--card);
}
.section-h{
  padding:10px 14px;
  font-size:18px;
  font-weight:900;
  letter-spacing:0.6px;
  display:flex;
  align-items:center;
  gap:8px;
}
.h-critical{background:var(--tag_red_bg); color:#7a1212;}
.h-attn{background:var(--tag_blue_bg); color:#143d8a;}
.h-load{background:var(--tag_yellow_bg); color:#6a5400;}
.h-land{background:var(--tag_orange_bg); color:#7a3a00;}
.h-flight{background:var(--tag_gray_bg); color:#3b4350;}

.items{padding:10px; display:flex; flex-direction:column; gap:10px;}

.item{
  border-radius:12px;
  padding:12px 14px;
  display:flex;
  justify-content:space-between;
  align-items:center;
  border:1px solid var(--tag_gray_line);
}
.item-left{display:flex; gap:14px; align-items:center;}
.pad{
  width:44px; height:44px;
  border-radius:12px;
  background:#ffffff;
  border:1px solid rgba(0,0,0,0.10);
  display:flex; align-items:center; justify-content:center;
  font-weight:1000;
  font-size:22px;
}
.desc{font-size:22px; font-weight:900;}
.meta{font-size:22px; font-weight:900; color:var(--ink);}

.tag-red{background:var(--tag_red_bg); border-color:var(--tag_red_line);}
.tag-blue{background:var(--tag_blue_bg); border-color:var(--tag_blue_line);}
.tag-yellow{background:var(--tag_yellow_bg); border-color:var(--tag_yellow_line);}
.tag-orange{background:var(--tag_orange_bg); border-color:var(--tag_orange_line);}
.tag-gray{background:var(--tag_gray_bg); border-color:var(--tag_gray_line);}

.footer{
  margin-top:auto;
  border:1px solid var(--line);
  border-radius:14px;
  background:white;
  padding:14px 16px;
  display:flex;
  justify-content:space-between;
  font-size:26px;
  font-weight:1000;
  color:#525b68;
}
.footer .k{color:#6b7483; font-weight:900; margin-right:10px;}
</style>
"""


def build_right_sections(pads: List[PadState]) -> str:
    # Disjoint sections (no pad appears twice)
    used = set()

    critical = [p for p in pads if p.phase == "LOADING" and p.severity == "critical" and p.issue]
    critical = sorted(critical, key=lambda x: x.pad)
    used |= {p.pad for p in critical}

    attention = [p for p in pads if p.phase == "LOADING" and p.severity == "attention" and p.issue and p.pad not in used]
    attention = sorted(attention, key=lambda x: x.pad)
    used |= {p.pad for p in attention}

    loading = [p for p in pads if p.phase == "LOADING" and p.pad not in used]
    loading = sorted(loading, key=lambda x: x.remaining)
    used |= {p.pad for p in loading}

    landing = [p for p in pads if p.phase == "LANDING" and p.remaining <= LANDING_SOON_THRESHOLD and p.pad not in used]
    landing = sorted(landing, key=lambda x: x.remaining)
    used |= {p.pad for p in landing}

    flight = [p for p in pads if p.phase == "FLIGHT" and p.pad not in used]
    flight = sorted(flight, key=lambda x: x.pad)

    html = ""

    def sec(title: str, cls: str, items_html: str) -> str:
        return f"""
<div class="section">
  <div class="section-h {cls}">{title}</div>
  <div class="items">{items_html if items_html else '<div class="item tag-gray"><div class="desc">None</div></div>'}</div>
</div>
"""

    # CRITICAL
    crit_items = "".join(
        item_html(p, "critical", p.issue or "Issue", f"{p.storage} {p.order_next}")
        for p in critical
    )
    html += sec("🔴 CRITICAL", "h-critical", crit_items)

    # ATTENTION
    att_items = "".join(
        item_html(p, "attention", p.issue or "Attention", f"{p.storage} {p.order_next}")
        for p in attention
    )
    html += sec("⚠️ ATTENTION", "h-attn", att_items)

    # LOADING NOW
    load_items = "".join(
        item_html(p, "loading", "Loading", f"{p.remaining}s • {p.storage} {p.order_next}")
        for p in loading
    )
    html += sec("🟡 LOADING NOW", "h-load", load_items)

    # LANDING SOON (<=60s)
    land_items = "".join(
        item_html(p, "landing", "Landing", f"{p.remaining}s • {p.storage} {p.order_next}")
        for p in landing
    )
    html += sec("🟠 LANDING SOON", "h-land", land_items)

    # IN FLIGHT (was IDLE)
    flight_items = "".join(
        item_html(p, "flight", "In flight", f"Next • {p.storage} {p.order_next}")
        for p in flight
    )
    html += sec("⚪ IN FLIGHT", "h-flight", flight_items)

    return html


def build_left_panel(kind: str, p: Optional[PadState], label: str) -> str:
    if kind == "default" or p is None:
        return f"""
<div class="left">
  <h2>STATUS</h2>
  <div class="primaryline">All clear</div>
  <div class="subline">Waiting for next arrival</div>
</div>
"""
    urgent = (kind in ("critical",))
    left_cls = "left urgent" if urgent else "left"

    if kind in ("critical", "attention"):
        # issue-first
        return f"""
<div class="{left_cls}">
  <h2>ACTION REQUIRED</h2>
  <div class="bigrow">
    <div class="arrow">➡</div>
    <div class="padbig">{p.pad}</div>
  </div>
  <div class="primaryline">{label}</div>
  <div class="orderline">{p.storage} {p.order_next}</div>
</div>
"""

    if kind == "loading":
        return f"""
<div class="{left_cls}">
  <h2>LOAD NOW</h2>
  <div class="bigrow">
    <div class="arrow">➡</div>
    <div class="padbig">{p.pad}</div>
  </div>
  <div class="primaryline">{p.remaining}s left</div>
  <div class="orderline">{p.storage} {p.order_next}</div>
</div>
"""

    # landing
    return f"""
<div class="{left_cls}">
  <h2>GO TO PAD</h2>
  <div class="bigrow">
    <div class="arrow">➡</div>
    <div class="padbig">{p.pad}</div>
  </div>
  <div class="primaryline">Landing in {p.remaining}s</div>
  <div class="orderline">{p.storage} {p.order_next}</div>
</div>
"""


# -------- App ----------
if "wall_state" not in st.session_state:
    st.session_state["wall_state"] = init_state()

state = st.session_state["wall_state"]
tick_sim(state)
pads = list(state["pads"].values())

# Autorefresh every second (keeps seconds changing)
try:
    from streamlit_autorefresh import st_autorefresh as _st_autorefresh
    _st_autorefresh(interval=1000, key="tick")
except Exception:
    # fallback: Streamlit reruns on interaction; on some hosts autorefresh may be unavailable
    pass

st.markdown(CSS, unsafe_allow_html=True)

banner_cls, banner_text = top_banner(pads, state)
st.markdown(f'<div class="banner {banner_cls}">{banner_text}</div>', unsafe_allow_html=True)

kind, primary_pad, primary_label = pick_primary(pads)
left_html = build_left_panel(kind, primary_pad, primary_label)

right_html = build_right_sections(pads)

# footer counts
at_base = sum(1 for p in pads if p.phase == "LOADING")
arriving = sum(1 for p in pads if p.phase == "LANDING")
cancelled = 0

right_html += f"""
<div class="footer">
  <div><span class="k">At Base</span>{at_base}</div>
  <div><span class="k">Arriving</span>{arriving}</div>
  <div><span class="k">Cancelled</span>{cancelled}</div>
</div>
"""

st.markdown(f'<div class="shell">{left_html}<div class="right">{right_html}</div></div>', unsafe_allow_html=True)
