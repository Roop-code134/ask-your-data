import os
import re
import sqlite3
import time
import pandas as pd
from groq import Groq

CSV_PATH = "sales.csv"
MODEL = "openai/gpt-oss-120b"

# ---------- API key: env var, or read .streamlit/secrets.toml ----------
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    try:
        text = open(".streamlit/secrets.toml", encoding="utf-8").read()
        api_key = re.search(r'GROQ_API_KEY\s*=\s*"([^"]+)"', text).group(1)
    except Exception:
        raise SystemExit("No GROQ_API_KEY found in environment or .streamlit/secrets.toml")

client = Groq(api_key=api_key)

# ---------- Load data exactly like the app does ----------
df = pd.read_csv(CSV_PATH)
df.columns = [c.strip().replace(" ", "_") for c in df.columns]
for col in df.columns:
    if "date" in col.lower():
        df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")

conn = sqlite3.connect(":memory:")
df.to_sql("data", conn, index=False, if_exists="replace")
conn.execute("PRAGMA query_only = ON")
schema = pd.read_sql("PRAGMA table_info(data)", conn)[["name", "type"]].to_string(index=False)


def ask_llm(question: str) -> str:
    prompt = f"""You write SQLite queries. The table is named `data`.

Schema:
{schema}

Sample rows:
{df.head(5).to_string(index=False)}

Notes:
- Date columns are stored as text in YYYY-MM-DD format. Use strftime('%Y-%m', column) for months.
- If a column name has spaces or symbols, wrap it in double quotes. Copy column names exactly as in the schema.
- Return ONLY one SELECT query. No explanation, no markdown fences.

Question: {question}"""
    resp = client.chat.completions.create(
        model=MODEL, max_tokens=2000, temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    sql = resp.choices[0].message.content.strip()
    return sql.replace("```sql", "").replace("```", "").strip().rstrip(";")


def normalize(frame: pd.DataFrame):
    """Compare values only: ignore column names, round numbers, ignore row order."""
    rows = []
    for row in frame.itertuples(index=False):
        rows.append(tuple(round(v, 2) if isinstance(v, float) else v for v in row))
    return sorted(rows, key=str)


# ---------- Test cases: (question, hand-written SQL) ----------
TESTS = [
    ("What is the total sales?",
     "SELECT SUM(Sales) FROM data"),
    ("How many rows are in the data?",
     "SELECT COUNT(*) FROM data"),
    ("How many unique customers are there?",
     "SELECT COUNT(DISTINCT Customer_ID) FROM data"),
    ("What is the average sales value per row?",
     "SELECT AVG(Sales) FROM data"),
    ("Total sales by year",
     "SELECT strftime('%Y', Order_Date), SUM(Sales) FROM data GROUP BY 1"),
    ("Total sales by region",
     "SELECT Region, SUM(Sales) FROM data GROUP BY Region"),
    ("Total sales by ship mode",
     "SELECT Ship_Mode, SUM(Sales) FROM data GROUP BY Ship_Mode"),
    ("Total sales by sub-category",
     'SELECT "Sub-Category", SUM(Sales) FROM data GROUP BY "Sub-Category"'),
    ("Top 5 products by total sales. Show product name and total sales.",
     "SELECT Product_Name, SUM(Sales) FROM data GROUP BY Product_Name ORDER BY 2 DESC LIMIT 5"),
    ("Which state has the highest total sales? Show the state and its total sales.",
     "SELECT State, SUM(Sales) FROM data GROUP BY State ORDER BY 2 DESC LIMIT 1"),
    ("Total sales for the Consumer segment",
     "SELECT SUM(Sales) FROM data WHERE Segment = 'Consumer'"),
    ("Total sales in 2017",
     "SELECT SUM(Sales) FROM data WHERE strftime('%Y', Order_Date) = '2017'"),
]

# ---------- Run ----------
passed = 0
for i, (question, expected_sql) in enumerate(TESTS, 1):
    print(f"\n[{i}/{len(TESTS)}] {question}")
    try:
        model_sql = ask_llm(question)
        got = normalize(pd.read_sql(model_sql, conn))
        want = normalize(pd.read_sql(expected_sql, conn))
        if got == want:
            passed += 1
            print("  PASS")
        else:
            print("  FAIL - results differ")
            print("  Model SQL:   ", model_sql)
            print("  Expected SQL:", expected_sql)
            print("  Model result:", got[:5])
            print("  Expected:    ", want[:5])
    except Exception as e:
        print(f"  FAIL - error: {e}")
    time.sleep(1)  # be gentle with rate limits

print(f"\n=== {passed}/{len(TESTS)} passed ({passed / len(TESTS):.0%}) ===")
