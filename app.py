import os
import re
import sqlite3
import pandas as pd
import streamlit as st
import altair as alt
from groq import Groq

st.set_page_config(page_title="Ask Your Data", page_icon="📊", layout="wide")

st.markdown(
    """
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
h1 {font-weight: 800; letter-spacing: -0.5px; color: #23001E;}

/* Gold sidebar */
section[data-testid="stSidebar"] {background: #FFBA49;}
section[data-testid="stSidebar"] * {color: #23001E;}
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {opacity: 1;}

/* Colored stat cards */
.kpi {border-radius: 14px; padding: 16px 20px; color: #FFFFFF;}
.kpi-label {font-size: 0.85rem; font-weight: 600; opacity: 0.95;}
.kpi-value {font-size: 2rem; font-weight: 700; line-height: 1.3;}

/* White content card behind each tab */
.stTabs [data-baseweb="tab-panel"] {
    background: #FFFFFF;
    border-radius: 14px;
    padding: 20px 24px;
    margin-top: 12px;
}

.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
    border-radius: 10px;
    font-weight: 600;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------- Sidebar ----------
with st.sidebar:
    st.header("📁 Your data")
    uploaded = st.file_uploader("Upload a CSV", type="csv")
    st.caption("Ask questions in plain English. The app writes SQL, checks it is read-only, and runs it.")

# ---------- Header ----------
st.title("📊 Ask Your Data")
st.caption("Upload a CSV, then ask questions in plain English.")

if uploaded is None:
    st.info("👈 Upload a CSV file in the sidebar to get started.")
    st.stop()

# ---------- Load and clean data ----------
df = pd.read_csv(uploaded)
df.columns = [c.strip().replace(" ", "_") for c in df.columns]

for col in df.columns:
    if "date" in col.lower():
        df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
        bad = df[col].isna().sum()
        if bad:
            st.warning(f"{bad} values in '{col}' couldn't be read as dates.")

# ---------- SQLite (read-only) ----------
conn = sqlite3.connect(":memory:")
df.to_sql("data", conn, index=False, if_exists="replace")
schema = pd.read_sql("PRAGMA table_info(data)", conn)[["name", "type"]].to_string(index=False)
conn.execute("PRAGMA query_only = ON")

# ---------- API key and model ----------
try:
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    api_key = os.environ.get("GROQ_API_KEY")

if not api_key:
    st.error("No API key found. Add GROQ_API_KEY to .streamlit/secrets.toml or set it as an environment variable.")
    st.stop()

client = Groq(api_key=api_key)
MODEL = "openai/gpt-oss-120b"


def ask_llm(prompt: str, max_tokens: int = 2000) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


FORBIDDEN = re.compile(
    r"\b(drop|delete|update|insert|alter|create|replace|attach|pragma|truncate)\b", re.I
)


def validate_sql(sql: str) -> str:
    sql = sql.strip().rstrip(";").strip()
    if ";" in sql:
        raise ValueError("Chained statements are not allowed.")
    if not re.match(r"^(select|with)\b", sql, re.I):
        raise ValueError("Only SELECT queries are allowed.")
    if FORBIDDEN.search(sql):
        raise ValueError("Query contains a blocked keyword.")
    return sql


# ---------- Charts ----------
PALETTE = ["#23001E", "#A4A9AD", "#FFBA49", "#20A39E", "#EF5B5B"]


def draw_chart(result):
    cat, val = result.columns[0], result.columns[1]
    data = pd.DataFrame({"label": result[cat].astype(str), "value": result[val]})
    tips = [
        alt.Tooltip("label:N", title=cat),
        alt.Tooltip("value:Q", title=val, format=",.2f"),
    ]

    if any(w in cat.lower() for w in ("month", "date", "year")):
        # Time data: plum line with gold dots
        chart = (
            alt.Chart(data)
            .mark_line(color="#23001E", strokeWidth=3,
                       point=alt.OverlayMarkDef(color="#FFBA49", size=80))
            .encode(
                x=alt.X("label:O", sort=None, title=None, axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("value:Q", title=None),
                tooltip=tips,
            )
            .properties(height=320)
        )
    else:
        # Categories: horizontal bars, one palette color each, in table order
        chart = (
            alt.Chart(data)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                y=alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=260)),
                x=alt.X("value:Q", title=None),
                color=alt.Color("label:N", scale=alt.Scale(range=PALETTE), legend=None),
                tooltip=tips,
            )
            .properties(height=max(200, 34 * len(data)))
        )

    st.altair_chart(chart, use_container_width=True)


# ---------- Stat cards ----------
def kpi(label, value, color):
    st.markdown(
        f'<div class="kpi" style="background:{color}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div></div>',
        unsafe_allow_html=True,
    )


date_cols = [c for c in df.columns if "date" in c.lower()]
if date_cols and df[date_cols[0]].notna().any():
    d = df[date_cols[0]].dropna()
    third = ("Date range", f"{d.min()[:4]} – {d.max()[:4]}")
else:
    third = ("Numeric columns", len(df.select_dtypes("number").columns))

k1, k2, k3, k4 = st.columns(4)
with k1:
    kpi("Rows", f"{len(df):,}", "#20A39E")
with k2:
    kpi("Columns", len(df.columns), "#EF5B5B")
with k3:
    kpi(third[0], third[1], "#23001E")
with k4:
    kpi("Missing cells", f"{int(df.isna().sum().sum()):,}", "#A4A9AD")

st.write("")
tab_ask, tab_summary, tab_data = st.tabs(["💬 Ask", "📝 Summary", "🗂️ Data"])

# ---------- Tab: Ask ----------
with tab_ask:
    with st.form("ask_form"):
        question = st.text_input(
            "Your question", placeholder="e.g. Top 5 products by total sales"
        )
        submitted = st.form_submit_button("Ask", type="primary")

    if submitted and question:
        entry = {"question": question, "sql": ""}
        with st.spinner("Thinking..."):
            try:
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
                sql = ask_llm(prompt).replace("```sql", "").replace("```", "").strip()
                entry["sql"] = sql
                entry["result"] = pd.read_sql(validate_sql(sql), conn)
            except Exception as e:
                entry["error"] = str(e)
        st.session_state["last"] = entry

    last = st.session_state.get("last")
    if last:
        with st.expander("Generated SQL"):
            st.code(last["sql"], language="sql")

        if "error" in last:
            st.error(f"Couldn't run that: {last['error']}")
        else:
            result = last["result"]
            st.subheader("Answer")
            st.dataframe(result)

            if len(result.columns) == 2 and pd.api.types.is_numeric_dtype(result.iloc[:, 1]):
                draw_chart(result)

            st.download_button(
                "⬇️ Download result as CSV",
                result.to_csv(index=False).encode("utf-8"),
                file_name="result.csv",
                mime="text/csv",
            )

# ---------- Tab: Summary ----------
with tab_summary:
    if st.button("Generate summary", type="primary"):
        with st.spinner("Summarizing..."):
            stats = df.describe(include="all").to_string()
            st.session_state["summary"] = ask_llm(
                f"Summarize this dataset in 5 short bullet points for a business reader.\n"
                f"Columns:\n{schema}\n\nStats:\n{stats}",
                max_tokens=1500,
            )
    if "summary" in st.session_state:
        st.markdown(st.session_state["summary"].replace("$", "\\$"))

# ---------- Tab: Data ----------
with tab_data:
    st.caption("First 100 rows")
    st.dataframe(df.head(100))
