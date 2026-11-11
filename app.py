import altair as alt
import os
import re
import time
import random
import sqlite3
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

MODELS = ["gemini-2.5-flash", "gemini-3.8-flash"]

EXAMPLES = [
    "What are the top 5 products by total sales?",
    "Total sales by region",
    "How many orders were placed in 2017?",
    "Which customer segment has the highest total sales?",
    "Total sales by category",
]

SYSTEM_PROMPT = """You are a SQL expert. Convert the user's question into ONE SQLite query.
Rules:
- Output only the SQL. No explanation, no markdown, no backticks.
- Use only the table and columns in the schema.
- SELECT queries only.
- When ranking or aggregating, always include the aggregated number as a column with a clear alias (for example SUM(sales) AS total_sales).
- Dates are stored as TEXT. Look at the sample rows to see the format. For DD/MM/YYYY, the year is substr(col, 7, 4) and the month is substr(col, 4, 2).
- If the question cannot be answered from the schema, output exactly: CANNOT_ANSWER"""

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|vacuum)\b",
    re.I,
)


# ---------------- Logic ----------------
def get_api_key():
    """Reads the key from .streamlit/secrets.toml (or an environment variable)."""
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.environ.get("GEMINI_API_KEY", "")


def is_safe(sql):
    s = sql.strip().rstrip(";")
    if not s.lower().startswith(("select", "with")):
        return False
    if ";" in s:
        return False
    if FORBIDDEN.search(s):
        return False
    return True


def get_schema(conn):
    text = ""
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for (table,) in tables:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        col_text = ", ".join(f"{c[1]} ({c[2]})" for c in cols)
        sample = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 3", conn)
        text += f"Table {table}: {col_text}\n"
        text += f"Sample rows:\n{sample.to_string(index=False)}\n\n"
    return text


def generate_sql(client, question, schema):
    last_error = None
    for model in MODELS:
        for attempt in range(2):
            for thinking_off in (True, False):
                t0 = time.time()
                try:
                    settings = dict(system_instruction=SYSTEM_PROMPT, temperature=0)
                    if thinking_off:
                        settings["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
                    response = client.models.generate_content(
                        model=model,
                        contents=f"Schema:\n{schema}\n\nQuestion: {question}",
                        config=types.GenerateContentConfig(**settings),
                    )
                    print(f"[{model}] OK in {time.time() - t0:.1f}s (thinking_off={thinking_off})")
                    sql = response.text.strip()
                    sql = re.sub(r"^```(?:sql)?|```$", "", sql, flags=re.I | re.M).strip()
                    return sql
                except Exception as e:
                    last_error = e
                    print(f"[{model}] FAILED in {time.time() - t0:.1f}s: {str(e)[:100]}")
                    if "503" in str(e) or "429" in str(e) or "UNAVAILABLE" in str(e):
                        time.sleep(2)
                        break  # server busy, so try again
    raise last_error

def show_chart(result):
    """Draws a chart if the result suits one. Returns True if it did."""
    nums = result.select_dtypes("number").columns.tolist()
    others = [c for c in result.columns if c not in nums]
    if len(result) < 2 or not nums or not others:
        return False
    x, y = others[0], nums[0]
    chart_df = result[[x, y]]
    if any(k in x.lower() for k in ("date", "month", "year")):
        st.line_chart(chart_df.set_index(x), color="#587A5F")
    else:
        chart = (
            alt.Chart(chart_df)
            .mark_bar(color="#8FAF94")
            .encode(
                x=alt.X(f"{x}:N", sort=None, title=None, axis=alt.Axis(labelAngle=-30)),
                y=alt.Y(f"{y}:Q", title=None),
            )
        )
        st.altair_chart(chart, use_container_width=True)
    return True


def set_question(text):
    st.session_state.question = text


def surprise():
    st.session_state.question = random.choice(EXAMPLES)


# ---------------- Page setup and styling ----------------
st.set_page_config(page_title="Ask Your Data", layout="centered")

st.markdown(
    """
    <style>
    .block-container {padding-top: 2.5rem; max-width: 880px;}

    .hero {text-align: center; padding: 0.5rem 0 1.5rem 0;
           border-bottom: 1px solid #D9E0D2; margin-bottom: 1.5rem;}
    .hero .badge {
        display: inline-block; padding: 4px 14px; border-radius: 4px;
        background: #E9EEE3; color: #587A5F; border: 1px solid #CBD6C4;
        font-size: 0.75rem; letter-spacing: 0.12em; text-transform: uppercase;
        margin-bottom: 1rem;
    }
    .hero h1 {
        font-family: Georgia, "Times New Roman", serif;
        font-size: 2.8rem; font-weight: 600; margin: 0; color: #2F3A33;
    }
    .hero p {color: #6B7568; font-size: 1.05rem; margin-top: 0.8rem;}

    h2, h3 {font-family: Georgia, "Times New Roman", serif; font-weight: 600;}

    div[data-testid="stMetric"] {
        background: #FBFAF5; border: 1px solid #D9E0D2;
        padding: 14px 18px; border-radius: 6px;
    }
    div.stButton > button {border-radius: 6px; border: 1px solid #CBD6C4; min-height: 4.2rem; white-space: normal;}
    div.stButton > button:hover {border-color: #587A5F; color: #587A5F;}
    div.stButton > button[kind="primary"]:hover {color: #FFFFFF; background: #46644C;}

    .footer {text-align: center; color: #8A9486; font-size: 0.85rem;
             margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #D9E0D2;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <div class="badge">AI-assisted data analysis</div>
        <h1>Ask Your Data</h1>
        <p>Upload a CSV file, ask a question in plain English, and receive the SQL, chart and results.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("How it works")
    st.markdown(
        """
        1. Upload a CSV file
        2. Ask a question in plain English
        3. The AI writes the SQL query
        4. A safety check permits read-only queries only
        5. Review the chart, table and download the result
        """
    )
    st.divider()
    st.caption("Please avoid uploading private or confidential data. Questions are processed by a third-party AI service.")

api_key = get_api_key()

# ---------------- Main ----------------
file = st.file_uploader("Upload a CSV file", type="csv")

if not file:
    st.info("Upload a CSV file to begin. Sales, HR and survey data all work well.")
else:
    df = pd.read_csv(file)
    df.columns = [re.sub(r"\W+", "_", c.strip().lower()) for c in df.columns]

    conn = sqlite3.connect(":memory:")
    df.to_sql("data", conn, index=False)
    schema = get_schema(conn)

    m1, m2, m3 = st.columns(3)
    m1.metric("Rows", f"{len(df):,}")
    m2.metric("Columns", len(df.columns))
    m3.metric("File", file.name[:18])

    with st.expander("Preview data"):
        st.dataframe(df.head(), use_container_width=True)

    st.write("**Example questions**")
    cols = st.columns(3)
    for i, ex in enumerate(EXAMPLES[:3]):
        cols[i].button(ex, on_click=set_question, args=(ex,), use_container_width=True)

    ask_col, surprise_col = st.columns([4, 1])
    question = ask_col.text_input(
        "Your question",
        key="question",
        placeholder="e.g. Which region generated the most profit?",
    )
    surprise_col.write("")
    surprise_col.write("")
    surprise_col.button("Random", on_click=surprise, use_container_width=True)

    if st.button("Ask", type="primary", use_container_width=True):
        if not api_key:
            st.error("This app is not configured yet: the API key is missing from the secrets file.")
        elif not question.strip():
            st.warning("Please type a question first.")
        else:
            try:
                start = time.time()
                client = genai.Client(api_key=api_key)
                with st.spinner("Reading your data and writing the SQL query..."):
                    sql = generate_sql(client, question, schema)

                if sql == "CANNOT_ANSWER":
                    st.error("This question cannot be answered from the uploaded data.")
                elif not is_safe(sql):
                    st.error("Blocked: only read-only SELECT queries are allowed.")
                    st.code(sql, language="sql")
                else:
                    result = pd.read_sql_query(sql, conn)
                    elapsed = time.time() - start
                    st.toast("Answer ready")

                    r1, r2, r3 = st.columns(3)
                    r1.metric("Rows returned", f"{len(result):,}")
                    r2.metric("Columns", len(result.columns))
                    r3.metric("Response time", f"{elapsed:.1f}s")

                    tab_chart, tab_table, tab_sql = st.tabs(["Chart", "Table", "SQL"])
                    with tab_chart:
                        if not show_chart(result):
                            st.info("This result is not suited to a chart. See the Table tab.")
                    with tab_table:
                        st.dataframe(result, use_container_width=True)
                    with tab_sql:
                        st.code(sql, language="sql")

                    st.download_button(
                        "Download result as CSV",
                        result.to_csv(index=False),
                        "result.csv",
                        "text/csv",
                        use_container_width=True,
                    )
            except Exception as e:
                st.error(f"Something went wrong: {e}")

st.markdown(
    '<div class="footer">Built with Streamlit, SQLite and Gemini</div>',
    unsafe_allow_html=True,
)