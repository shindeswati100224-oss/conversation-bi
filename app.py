# ================= IMPORTS =================
import streamlit as st
import duckdb
import pandas as pd

# ================= CONFIG =================
CSV_PATH = "conversation_bi_output_FAST.csv"
DB_PATH = "conversation_bi.duckdb"
TABLE_NAME = "conversations"

# ================= PAGE =================
st.set_page_config(page_title="Conversational BI", layout="wide")
st.title("🧠 Conversational BI")
st.caption("Ask anything. System detects intent and shows KPI, table, chart, or insight.")

# ================= LOAD DATA =================
@st.cache_data
def load_df():
    return pd.read_csv(CSV_PATH)

@st.cache_resource
def get_con(df):
    con = duckdb.connect(DB_PATH, read_only=False)
    con.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    con.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM df")
    return con

df = load_df()
con = get_con(df)

# ================= INTENT DETECTION =================
def detect_intent(q):
    q = q.lower()

    if any(w in q for w in ["how many", "count", "number"]):
        return "COUNT"

    if any(w in q for w in ["distribution", "breakdown", "split"]):
        return "DISTRIBUTION"

    if any(w in q for w in ["most", "top", "highest"]):
        return "TOP"

    if any(w in q for w in ["why", "reason", "cause"]):
        return "WHY"

    if any(w in q for w in ["overview", "summary", "analyze"]):
        return "SUMMARY"

    return "GENERAL"

# ================= SQL GENERATION =================
def generate_sql(intent, question):
    q = question.lower()

    if intent == "COUNT":
        if "pending" in q or "unresolved" in q:
            return f"""
            SELECT COUNT(*) AS value
            FROM {TABLE_NAME}
            WHERE resolution_status = 'Pending'
            """
        if "negative" in q or "frustrated" in q:
            return f"""
            SELECT COUNT(*) AS value
            FROM {TABLE_NAME}
            WHERE sentiment = 'Negative'
            """
        return f"SELECT COUNT(*) AS value FROM {TABLE_NAME}"

    if intent == "DISTRIBUTION":
        return f"""
        SELECT issue_type, sentiment, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type, sentiment
        """

    if intent == "TOP":
        return f"""
        SELECT issue_type, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type
        ORDER BY count DESC
        LIMIT 5
        """

    if intent == "WHY":
        if "pending" in q:
            return f"""
            SELECT issue_type, COUNT(*) AS count
            FROM {TABLE_NAME}
            WHERE resolution_status = 'Pending'
            GROUP BY issue_type
            ORDER BY count DESC
            """
        if "sentiment" in q or "dissatisfied" in q:
            return f"""
            SELECT issue_type, sentiment, COUNT(*) AS count
            FROM {TABLE_NAME}
            GROUP BY issue_type, sentiment
            """
        return f"""
        SELECT issue_type, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type
        ORDER BY count DESC
        """

    return f"SELECT issue_type, COUNT(*) AS count FROM {TABLE_NAME} GROUP BY issue_type"

# ================= OUTPUT TYPE =================
def decide_output(df):
    if df.shape == (1, 1):
        return "KPI"
    if "sentiment" in df.columns:
        return "STACKED"
    if df.shape[0] > 1:
        return "TABLE_CHART"
    return "SUMMARY"

# ================= INSIGHT ENGINE =================
def generate_insight(intent, question, df):
    if df.empty:
        return "No data available for this question."

    # COUNT
    if intent == "COUNT":
        return f"The total count is **{int(df.iloc[0,0])}**."

    # WHY
    if intent == "WHY":
        top = df.iloc[0]
        total = df["count"].sum()
        pct = (top["count"] / total) * 100
        return (
            f"The primary reason is **{top['issue_type']}** issues, "
            f"which contribute **{pct:.0f}%** of the total cases."
        )

    # DISTRIBUTION
    if intent == "DISTRIBUTION":
        dominant = df.groupby("sentiment")["count"].sum().idxmax()
        return f"The distribution shows **{dominant}** sentiment dominating overall."

    # TOP
    if intent == "TOP":
        return f"The most common issue type is **{df.iloc[0]['issue_type']}**."

    # SUMMARY / GENERAL
    top = df.sort_values("count", ascending=False).iloc[0]
    return f"Overall, **{top['issue_type']}** issues appear most frequently."

# ================= UI =================
st.subheader("💬 Ask a question")
question = st.text_input("Ask anything about customers, issues, sentiment, service…")

if st.button("Ask") and question:
    intent = detect_intent(question)
    sql = generate_sql(intent, question)
    result = con.execute(sql).fetchdf()
    output = decide_output(result)

    if output == "KPI":
        st.metric("Result", int(result.iloc[0,0]))
        st.info(generate_insight(intent, question, result))

    elif output == "STACKED":
        pivot = result.pivot(index="issue_type", columns="sentiment", values="count").fillna(0)
        st.bar_chart(pivot)
        st.success(generate_insight(intent, question, result))

    elif output == "TABLE_CHART":
        st.dataframe(result, use_container_width=True)
        st.bar_chart(result.set_index(result.columns[0]))
        st.success(generate_insight(intent, question, result))

    else:
        st.success(generate_insight(intent, question, result))

# ================= SIDEBAR =================
st.sidebar.header("📌 Example Questions")
st.sidebar.markdown("""
- Count of unresolved issues
- How many customers are frustrated?
- Why pending cases are increasing?
- Show sentiment distribution by issue
- Which issue type has most complaints?
- Give an overview of customer issues
""")
