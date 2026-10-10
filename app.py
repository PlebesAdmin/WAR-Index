import streamlit as st
import pandas as pd
import numpy as np

from war_engine import WARIndexEngine, WARConfig


st.set_page_config(
    page_title="WAR Index – Football Transfer Value",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ WAR Index")
st.caption(
    "Two questions, two scores: "
    "Was the original transfer good value? "
    "Is the player good value at their current price?"
)

with st.expander("How to use this tool (click to open)", expanded=False):
    st.markdown(
        """
        **WAR Index** answers two related questions:

        1. **Transfer Value** — Was the original transfer good value?
        2. **Current Value** — Is the player good value *now* at their current FPL price?

        | Score | Cost base | Performance window |
        |-------|-----------|--------------------|
        | **Transfer Value** | Guaranteed transfer fee (£m) | All PL output since the transfer |
        | **Current Value** | Current FPL price (£m) | This season only |

        Both scores use the same transparent formula (0–100):
        - **Production** (40%) – goal contributions & expected involvement per 90
        - **Volume** (25%) – minutes (sample reliability)
        - **Efficiency** (35%) – output relative to the cost base

        Labels: **Good value** (≥70) · **Fair value** (40–69) · **Poor value** (<40)

        Historical seasons come from the public
        [vaastav FPL archive](https://github.com/vaastav/Fantasy-Premier-League);
        the current season comes from the live FPL API.
        Fees are curated guaranteed figures with a confidence flag.
        """
    )


@st.cache_resource
def get_engine():
    return WARIndexEngine(
        config=WARConfig(
            production_weight=0.40,
            volume_weight=0.25,
            efficiency_weight=0.35,
        )
    ).load()


engine = get_engine()

with st.sidebar:
    st.header("Filters")

    min_minutes = st.slider(
        "Minimum cumulative minutes since transfer",
        min_value=0,
        max_value=5000,
        value=90,
        step=90,
        help="Players below this threshold are still shown but flagged as low sample.",
    )

    positions = st.multiselect(
        "Positions",
        ["GKP", "DEF", "MID", "FWD"],
        default=["GKP", "DEF", "MID", "FWD"],
    )

    max_fee = st.slider(
        "Maximum fee (£m)",
        min_value=10.0,
        max_value=150.0,
        value=150.0,
        step=5.0,
    )

    value_filter = st.selectbox(
        "Value label",
        ["All", "Good value", "Fair value", "Poor value"],
        index=0,
    )

    top_n = st.slider("Players to display", 5, 30, 15)

    st.divider()
    st.markdown("### Value Score weights")
    st.write("Production 40% · Volume 25% · Efficiency 35%")
    st.caption("Era 1 – transparent statistical model, not an AI oracle.")


with st.spinner("Loading FPL performance data and calculating Value Scores..."):
    df = engine.calculate(min_minutes=min_minutes)

if df.empty:
    st.warning("No transfer records matched the current filters.")
    st.stop()

# Apply UI filters
filtered = df[
    df["position"].isin(positions)
    & (df["fee_guaranteed_m"] <= max_fee)
].copy()

if value_filter != "All":
    filtered = filtered[filtered["value_label"] == value_filter]

if filtered.empty:
    st.warning("No players match these filters. Try relaxing the fee or position limits.")
    st.stop()

display = filtered.head(top_n).copy()

# ---------- Hero metrics ----------
st.subheader("Key insights")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Transfers analysed", f"{len(filtered)}")
col2.metric(
    "Best Transfer Value",
    f"{display['value_score'].max():.0f}",
    help="Highest score for original fee vs cumulative performance",
)
if "current_value_score" in display.columns:
    col3.metric(
        "Best Current Value",
        f"{display['current_value_score'].max():.0f}",
        help="Highest score for current FPL price vs this-season performance",
    )
else:
    col3.metric("Best Current Value", "—")
col4.metric(
    "Highest fee in view",
    f"£{display['fee_guaranteed_m'].max():.0f}m",
)

# ---------- Snapshot cards ----------
st.markdown("### Snapshot")

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("**🟢 Best Transfer Value**")
    bargains = filtered.nlargest(5, "value_score")
    for _, r in bargains.iterrows():
        st.write(
            f"{r['player_name']} — £{r['fee_guaranteed_m']:.0f}m · "
            f"**{r['value_score']:.0f}/100**"
        )

with c2:
    st.markdown("**💰 Best Current Value**")
    if "current_value_score" in filtered.columns:
        cur_best = filtered.nlargest(5, "current_value_score")
        for _, r in cur_best.iterrows():
            st.write(
                f"{r['player_name']} — £{r['price_now']:.1f}m now · "
                f"**{r['current_value_score']:.0f}/100**"
            )
    else:
        st.write("Current value not available in this build.")

with c3:
    st.markdown("**🔴 Weakest Transfer Value**")
    overpays = filtered.nsmallest(5, "value_score")
    for _, r in overpays.iterrows():
        st.write(
            f"{r['player_name']} — £{r['fee_guaranteed_m']:.0f}m · "
            f"**{r['value_score']:.0f}/100**"
        )

# ---------- Main ranking table ----------
st.subheader(f"Rankings · Top {len(display)}")

chart_cols = ["value_score"]
if "current_value_score" in display.columns:
    chart_cols.append("current_value_score")
chart_data = display.set_index("web_name")[chart_cols].rename(columns={
    "value_score": "Transfer Value",
    "current_value_score": "Current Value",
})
st.bar_chart(chart_data, color=["#9BE33C", "#4FC3F7"])

_wanted = [
    ("rank", "Rank"),
    ("player_name", "Player"),
    ("to_club", "Club"),
    ("position", "Pos"),
    ("fee_guaranteed_m", "Fee £m"),
    ("price_now", "FPL £m"),
    ("seasons_counted", "Seasons"),
    ("minutes", "Mins (all)"),
    ("goal_contrib", "G+A (all)"),
    ("live_minutes", "Mins (now)"),
    ("live_goal_contrib", "G+A (now)"),
    ("value_score", "Transfer Value"),
    ("current_value_score", "Current Value"),
    ("value_story", "Story"),
]
_present = [(src, label) for src, label in _wanted if src in display.columns]
table = display[[src for src, _ in _present]].copy()
table.columns = [label for _, label in _present]

def fmt_money(x):
    if pd.isna(x):
        return "—"
    return f"£{x/1_000_000:.1f}m"

st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Fee £m": st.column_config.NumberColumn(format="£%.1f"),
        "FPL £m": st.column_config.NumberColumn(format="£%.1f"),
        "Transfer Value": st.column_config.NumberColumn(format="%.0f"),
        "Current Value": st.column_config.NumberColumn(format="%.0f"),
    },
)

# ---------- Player detail expanders ----------
st.divider()
st.subheader("Player detail & explanation")

for _, row in display.iterrows():
    label_icon = {
        "Good value": "🟢",
        "Fair value": "🟡",
        "Poor value": "🔴",
    }.get(row["value_label"], "⚪")
    cur_icon = {
        "Good value": "🟢",
        "Fair value": "🟡",
        "Poor value": "🔴",
    }.get(row.get("current_value_label", ""), "⚪")

    cur_txt = ""
    if "current_value_score" in row.index and pd.notna(row["current_value_score"]):
        cur_txt = (
            f" · Current {row['current_value_score']:.0f}/100 {cur_icon}"
        )

    with st.expander(
        f"#{int(row['rank'])} {row['player_name']} — "
        f"Transfer {row['value_score']:.0f}/100 {label_icon}{cur_txt}"
    ):
        st.write(engine.explain_player(row))

        st.markdown("**Transfer value (fee vs career since move)**")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Fee paid", f"£{row['fee_guaranteed_m']:.1f}m")
        m2.metric("Minutes since transfer", f"{int(row['minutes']):,}")
        m3.metric("G+A since transfer", f"{int(row['goal_contrib'])}")
        m4.metric("Transfer Value", f"{row['value_score']:.0f}/100")

        if "current_value_score" in row.index:
            st.markdown("**Current value (FPL price vs this season)**")
            n1, n2, n3, n4 = st.columns(4)
            n1.metric("FPL price now", f"£{row['price_now']:.1f}m")
            n2.metric("Minutes this season", f"{int(row.get('live_minutes', 0))}")
            n3.metric("G+A this season", f"{int(row.get('live_goal_contrib', 0))}")
            n4.metric("Current Value", f"{row['current_value_score']:.0f}/100")

        if "value_story" in row.index and row["value_story"]:
            st.info(row["value_story"])

        st.write(
            f"**Transfer components** — "
            f"Production {row['production_score']:.0f} · "
            f"Volume {row['volume_score']:.0f} · "
            f"Efficiency {row['efficiency_score']:.0f}"
        )
        if row["low_sample"]:
            st.warning("Low cumulative minutes — Transfer Value softly penalised.")
        if row["notes"]:
            st.caption(row["notes"])
        st.caption(
            f"Fee confidence: {row['fee_confidence']} · "
            f"Reported / max fee: £{row['fee_reported_m']:.1f}m / £{row['fee_max_m']:.1f}m"
        )

# ---------- Download ----------
st.divider()
csv = display.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download current ranking as CSV",
    data=csv,
    file_name="war_index_rankings.csv",
    mime="text/csv",
)

st.caption(
    "WAR Index is a decision-support model for understanding transfer value. "
    "It is not a prediction of future performance or a valuation service. "
    "Performance data is sourced from the public Fantasy Premier League API. "
    "Transfer fees are curated reported figures and may differ from final accounting values."
)
