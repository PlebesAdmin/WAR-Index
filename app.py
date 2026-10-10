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
    "What is a footballer really worth? "
    "A transparent Value Score for Fantasy Premier League transfers — "
    "performance delivered relative to the fee paid."
)

with st.expander("How to use this tool (click to open)", expanded=False):
    st.markdown(
        """
        **WAR Index (Weighted Average Rating)** answers a single question:  
        *Was this footballer good value?*

        **Phase 1 method (with history)**
        - Guaranteed transfer fee is used as the cost base.
        - Performance is **cumulative Premier League output since the transfer date**,
          not just the current season.
        - Historical seasons come from the public
          [vaastav FPL archive](https://github.com/vaastav/Fantasy-Premier-League);
          the current season is taken from the live FPL API.
        - Three components combined into a 0–100 Value Score:
          - **Production** (40%) – goal contributions & expected involvement per 90
          - **Volume** (25%) – cumulative minutes (reliability of the sample)
          - **Efficiency** (35%) – output relative to the fee paid
        - Labels: **Good value** (≥70) · **Fair value** (40–69) · **Poor value** (<40)

        The sample set is a curated list of notable permanent Premier League transfers.
        Fees are reported/guaranteed figures and carry a confidence flag.
        Players with fewer than ~900 cumulative minutes are softly penalised.
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
st.subheader("Key Transfer Value Insights")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Transfers analysed", f"{len(filtered)}")
col2.metric("Best Value Score", f"{display.iloc[0]['value_score']:.0f}")
col3.metric(
    "Biggest bargain",
    display.loc[display["value_score"].idxmax(), "web_name"]
    if not display.empty else "—",
)
col4.metric(
    "Highest fee in view",
    f"£{display['fee_guaranteed_m'].max():.0f}m",
)

# ---------- Three insight cards ----------
st.markdown("### Snapshot")

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("**🟢 Biggest Bargains**")
    bargains = filtered.nlargest(5, "value_score")[
        ["player_name", "fee_guaranteed_m", "value_score", "value_label"]
    ]
    for _, r in bargains.iterrows():
        st.write(
            f"{r['player_name']} — £{r['fee_guaranteed_m']:.0f}m · "
            f"**{r['value_score']:.0f}/100**"
        )

with c2:
    st.markdown("**🔴 Biggest Overpays**")
    overpays = filtered.nsmallest(5, "value_score")[
        ["player_name", "fee_guaranteed_m", "value_score", "value_label"]
    ]
    for _, r in overpays.iterrows():
        st.write(
            f"{r['player_name']} — £{r['fee_guaranteed_m']:.0f}m · "
            f"**{r['value_score']:.0f}/100**"
        )

with c3:
    st.markdown("**🏆 Highest Value Scores**")
    top = filtered.nlargest(5, "value_score")[
        ["player_name", "fee_guaranteed_m", "value_score"]
    ]
    for _, r in top.iterrows():
        st.write(
            f"{r['player_name']} — {r['value_score']:.0f}/100 · £{r['fee_guaranteed_m']:.0f}m"
        )

# ---------- Main ranking table ----------
st.subheader(f"Value Rankings · Top {len(display)}")

chart_data = display.set_index("web_name")[["value_score"]]
st.bar_chart(chart_data, color="#9BE33C")

table = display[
    [
        "rank",
        "player_name",
        "to_club",
        "position",
        "fee_guaranteed_m",
        "seasons_counted",
        "minutes",
        "goal_contrib",
        "goal_contrib_per_90",
        "pounds_per_contrib",
        "value_score",
        "value_label",
        "transfer_premium_pct",
    ]
].copy()

table.columns = [
    "Rank",
    "Player",
    "Club",
    "Pos",
    "Fee £m",
    "Seasons",
    "Minutes",
    "G+A",
    "G+A / 90",
    "£ per G+A",
    "Value Score",
    "Label",
    "Premium %",
]

# Format money columns for display
def fmt_money(x):
    if pd.isna(x):
        return "—"
    return f"£{x/1_000_000:.1f}m"

table["£ per G+A"] = table["£ per G+A"].apply(fmt_money)

st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Fee £m": st.column_config.NumberColumn(format="£%.1f"),
        "G+A / 90": st.column_config.NumberColumn(format="%.2f"),
        "Value Score": st.column_config.NumberColumn(format="%.0f"),
        "Premium %": st.column_config.NumberColumn(format="%+.0f%%"),
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

    with st.expander(
        f"#{int(row['rank'])} {row['player_name']} — "
        f"£{row['fee_guaranteed_m']:.0f}m → Value Score {row['value_score']:.0f}/100 {label_icon}"
    ):
        st.write(engine.explain_player(row))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Minutes", f"{int(row['minutes'])}")
        m2.metric("Goals + Assists", f"{int(row['goal_contrib'])}")
        m3.metric("G+A per 90", f"{row['goal_contrib_per_90']:.2f}")
        m4.metric(
            "£ per G+A",
            fmt_money(row["pounds_per_contrib"]),
        )

        st.write(
            f"**Component scores** — "
            f"Production {row['production_score']:.0f} · "
            f"Volume {row['volume_score']:.0f} · "
            f"Efficiency {row['efficiency_score']:.0f}"
        )
        st.write(
            f"Estimated fair value (illustrative): £{row['estimated_fair_value_m']:.1f}m · "
            f"Transfer premium: {row['transfer_premium_pct']:+.0f}%"
        )
        if row["low_sample"]:
            st.warning("Low minutes sample — score has been softly penalised.")
        if row["notes"]:
            st.info(row["notes"])
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
