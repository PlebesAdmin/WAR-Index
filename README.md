WAR Index – Football Transfer Value

A transparent application that answers one question:

Was this footballer good value?

What it does

The app combines:





A curated set of notable Premier League permanent transfers (fee, clubs, date) as well as their current FPL fee to calculate a single index value



Cumulative Premier League performance since the transfer date





Historical seasons from the public vaastav FPL archive



Current season from the live Fantasy Premier League API



A simple, explainable Value Score (0–100)

Value Score components (Phase 1)







Component



Weight



Meaning





Production



40%



Goal contributions + expected involvement /90





Volume



25%



Cumulative minutes (sample reliability)





Efficiency



35%



Output relative to the guaranteed fee paid

Labels:





Good value ≥ 70



Fair value 40–69



Poor value < 40

Fees are treated honestly: guaranteed fee is the primary cost base; maximum fee and a confidence flag are also shown. Players with fewer than ~900 cumulative minutes are softly penalised.

Project structure

war_index/
├── app.py                 # Streamlit front-end
├── war_engine.py          # Data pull + Value Score engine (live + historical)
├── requirements.txt
├── README.md
└── .streamlit/
    └── config.toml        # Dark theme (matches FPL FVI app)

Run locally

Requires Python 3.11+.

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py

The browser should open automatically.

Deploy to Streamlit Community Cloud





Push this folder to a public GitHub repository.



Go to https://share.streamlit.io and sign in.



Click New app.



Select the repository, branch, and set the main file path to app.py.



Deploy.

The app will be available at a URL of the form:

https://<your-app-name>.streamlit.app/

Exactly the same deployment path used for the FPL Fixture Value Index.

Design principles





Transparent statistical model, not an opaque AI.



Fees never pretended to be more precise than they are.



Performance is measured as what the buying club actually received in the Premier League.



Low-minute samples are softly penalised.



Morgan Rogers £117 m transfer is included only as an illustrative benchmark.

Data sources





Fees: curated SAMPLE_TRANSFERS list inside war_engine.py



Current season: official FPL API (bootstrap-static)



Historical seasons: vaastav/Fantasy-Premier-League cleaned season aggregates

Next steps (after this Phase 1)





Expand the transfer database (100–200+ Premier League permanent deals).



Optional year-by-year breakdown in the player expander.



Move the transfer list into a simple CSV for easier maintenance.

