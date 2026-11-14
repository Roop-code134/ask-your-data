# Ask Your Data

Upload a CSV, ask a question in plain English, and get the SQL, a chart, and the results.

**Live demo:** https://ask-your-data-roop.streamlit.app/

## How it works

1. The CSV is loaded with pandas and cleaned: column names are normalized and `dd/mm/yyyy` text dates are converted to `YYYY-MM-DD`.
2. The data goes into an in-memory SQLite table.
3. The table schema and a few sample rows are sent to an LLM (`openai/gpt-oss-120b` on Groq), which writes a SQL query.
4. A validation layer blocks anything that is not a single read-only `SELECT`, including `DROP`, `DELETE`, `UPDATE`, and chained statements. SQLite is also set to `PRAGMA query_only = ON` as a second lock.
5. The query runs, and the result is shown as a table, a chart, and a downloadable CSV.

## Features

- Plain-English questions turned into SQL
- Read-only validation (regex check plus SQLite `query_only`)
- Handling of text-format dates
- Auto-generated charts and an AI summary of the dataset
- CSV download of any result

## Accuracy check

`tests.py` runs 12 questions through the app's pipeline and compares each result with a hand-written SQL query. Result: **12/12 matched**.

## Tech stack

Python, pandas, SQLite, Streamlit, Altair, Groq API

## Run locally
