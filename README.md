# WAR Index – Football Transfer Value

A transparent Streamlit application that answers one question:

**Was this football transfer good value?**

## What it does

The app combines:

- A curated set of notable Premier League permanent transfers (fee, clubs, date)
- Current-season performance from the public Fantasy Premier League API
- A simple, explainable **Value Score (0–100)**

### Value Score components (Version 1)

| Component      | Weight | Meaning                                      |
|----------------|--------|----------------------------------------------|
| Production     | 40%    | Goal contributions + expected involvement /90 |
| Volume         | 25%    | Minutes played (sample reliability)          |
| Efficiency     | 35%    | Output relative to the guaranteed fee paid   |

Labels:

- **Good value** ≥ 70
- **Fair value** 40–69
- **Poor value** < 40

Fees are treated honestly: guaranteed fee is the primary cost base; maximum fee and a confidence flag are also shown.

## Project structure

```text
war_index/
├── app.py                 # Streamlit front-end
├── war_engine.py          # Data pull + Value Score engine
├── requirements.txt
├── README.md
└── .streamlit/
    └── config.toml        # Dark theme (matches FPL FVI app)
```

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The browser should open automatically.

## Deploy to Streamlit Community Cloud

1. Push this folder to a public GitHub repository.
2. Go to https://share.streamlit.io and sign in.
3. Click **New app**.
4. Select the repository, branch, and set the main file path to `app.py`.
5. Deploy.

The app will be available at a URL of the form:

`https://<your-app-name>.streamlit.app/`

Exactly the same deployment path used for the FPL Fixture Value Index.

## Design principles (Era 1)

- Transparent statistical model, not an opaque AI.
- Fees never pretended to be more precise than they are.
- Low-minute samples are softly penalised.
- Morgan Rogers £117 m transfer is included only as an illustrative benchmark.
- The website simply reads the calculated results; it does not recalculate statistics on the fly beyond the engine.

## Next steps (after this deployable Version 1)

1. Expand the transfer database (100–200+ Premier League permanent deals).
2. Add historical season snapshots so post-transfer windows are precise.
3. Introduce position-specific weighting.
4. Add age and contract adjustments (Version 2 / 3 of the original plan).

## Data sources

- Performance: public Fantasy Premier League API (`bootstrap-static`)
- Transfer fees: curated reported figures for the sample set (replace with your own cleaned database later)
