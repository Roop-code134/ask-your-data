# Ask Your Data

Upload a CSV, ask a question in plain English, and get the SQL, a chart and the results.

**Live demo:** https://ask-your-data-roop.streamlit.app/

## What it does
- Loads any CSV into an in-memory SQLite database
- Sends the table's schema and your question to an LLM (Google Gemini), which writes the SQL
- Checks the SQL is read-only before running it
- Shows the result as a table and a chart, with the SQL visible and a CSV download

## How it works
1. **Upload:** pandas reads the CSV and cleans the column names
2. **Schema:** the app collects column names, types and sample rows
3. **Generate:** the LLM turns the question into one SQLite query
4. **Validate:** only `SELECT`/`WITH` queries are allowed; anything else is blocked
5. **Run and display:** results appear as a table and a chart

## Safety
The AI is instructed to write read-only SQL, and a separate check in code blocks `DROP`, `DELETE`, `UPDATE`, `INSERT` and chained statements, so a bad or manipulated query can't change the data.

## Tech stack
Python, Streamlit, pandas, SQLite, Altair, Google Gemini API

## Testing
I checked AI-generated answers against hand-written SQL. For example, the app's count of orders placed in 2017 matched my own query using `COUNT(DISTINCT order_id)`.

## Known limitations
- Works with one table (one CSV) at a time
- Dates stored as text are handled with prompt rules, not a proper date type
- The demo uses a shared free API key, so heavy use may hit rate limits
- Please don't upload private data: questions are processed by a third-party AI service

## Run it locally
```
pip install -r requirements.txt
```
Create `.streamlit/secrets.toml` with `GEMINI_API_KEY = "your-key"`, then run:
```
streamlit run app.py
```

## Sample data
`sales.csv` is the public Superstore sales dataset.

## What I'd improve next
Multi-file joins, a proper date-parsing step, and per-user rate limits.
