# ================= IMPORTS =================
import streamlit as st
import duckdb
import pandas as pd

# ================= CONFIG =================
CSV_PATH = "conversation_bi_output_FAST.csv"
DB_PATH = "conversation_bi.duckdb"
TABLE_NAME = "conversations"

# ================= PAGE SETUP =================
st.set_page_config(page_title="Conversational BI", layout="wide")
st.title("🧠 Conversational BI")
st.caption("Ask anything. System decides KPI, table, chart, or insight.")

# ================= LOAD DATA =================
@st.cache_data
def load_dataframe():
    return pd.read_csv(CSV_PATH)

@st.cache_resource
def get_connection(df):
    con = duckdb.connect(database=DB_PATH, read_only=False)
    con.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    con.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM df")
    return con

df = load_dataframe()
con = get_connection(df)

# ================= INTENT HELPERS =================
def has_any(q, words):
    return any(w in q for w in words)

# ================= LLM-2 : SQL GENERATOR =================
def generate_sql(question):
    q = question.lower()

    if has_any(q, ["how many", "count", "number"]) and has_any(q, ["negative", "frustrated"]):
        return f"""
        SELECT COUNT(*) AS value
        FROM {TABLE_NAME}
        WHERE sentiment = 'Negative'
        """

    if has_any(q, ["pending"]):
        return f"""
        SELECT issue_type, COUNT(*) AS count
        FROM {TABLE_NAME}
        WHERE resolution_status = 'Pending'
        GROUP BY issue_type
        ORDER BY count DESC
        """

    if has_any(q, ["sentiment"]):
        return f"""
        SELECT issue_type, sentiment, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type, sentiment
        """

    if has_any(q, ["most", "highest", "top"]) and "issue" in q:
        return f"""
        SELECT issue_type, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type
        ORDER BY count DESC
        LIMIT 1
        """

    if has_any(q, ["why", "reason", "cause"]):
        return f"""
        SELECT issue_type, sentiment, resolution_status, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type, sentiment, resolution_status
        """

    # fallback – always answer
    return f"SELECT * FROM {TABLE_NAME} LIMIT 50"

# ================= OUTPUT DECISION =================
def decide_output(df):
    if df.shape == (1, 1):
        return "kpi"

    if "sentiment" in df.columns and "issue_type" in df.columns:
        return "stacked_chart"

    if df.shape[0] > 1 and df.shape[1] > 1:
        return "table_chart"

    return "summary"

# ================= LLM-3 : REASONING ENGINE =================
def generate_insight(question, df):
    q = question.lower()

    if df.empty:
        return "No data found for this question."

    # KPI insight
    if df.shape == (1, 1):
        return f"The result shows **{int(df.iloc[0,0])}** matching records."

    # Why-type reasoning
    if has_any(q, ["why", "reason", "cause"]):
        neg = df[df["sentiment"] == "Negative"]
        if not neg.empty:
            top_issue = neg.groupby("issue_type")["count"].sum().idxmax()
            pending_pct = (
                neg[neg["resolution_status"] == "Pending"]["count"].sum()
                / neg["count"].sum()
            ) * 100
            return (
                f"Analysis shows **{top_issue}** as the primary driver. "
                f"Approximately **{pending_pct:.0f}%** of negative cases remain unresolved, "
                f"which is increasing customer dissatisfaction."
            )

    # Distribution insight
    if "sentiment" in df.columns:
        dominant = df.groupby("sentiment")["count"].sum().idxmax()
        return f"Overall sentiment is dominated by **{dominant}** cases."

    return "Here is the analysis based on the available data."

# ================= UI =================
st.subheader("💬 Ask a question")
question = st.text_input("Ask anything about customers, issues, sentiment, service…")

if st.button("Ask") and question:
    sql = generate_sql(question)
    result = con.execute(sql).fetchdf()

    output = decide_output(result)

    # KPI
    if output == "kpi":
        st.metric("Result", int(result.iloc[0, 0]))
        st.info(generate_insight(question, result))

    # TABLE + CHART + INSIGHT
    elif output == "table_chart":
        st.dataframe(result, use_container_width=True)
        st.bar_chart(result.set_index(result.columns[0]))
        st.success(generate_insight(question, result))

    # STACKED CHART + INSIGHT
    elif output == "stacked_chart":
        pivot = result.pivot(index="issue_type", columns="sentiment", values="count").fillna(0)
        st.bar_chart(pivot)
        st.success(generate_insight(question, result))

    # SUMMARY ONLY
    else:
        st.success(generate_insight(question, result))

# ================= SIDEBAR =================
st.sidebar.header("📌 Example Questions")
st.sidebar.markdown("""
- How many customers are frustrated?
- Which issue type has most pending cases?
- Show sentiment distribution by issue
- Why customers are dissatisfied?
- Why delivery issues are high?
""")
