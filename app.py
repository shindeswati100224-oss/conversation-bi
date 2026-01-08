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
st.caption("Ask anything. System detects intent and shows the right output.")

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

    if any(w in q for w in ["why", "reason", "cause"]):
        return "WHY"

    if any(w in q for w in ["distribution", "breakdown", "split"]):
        return "DISTRIBUTION"

    if any(w in q for w in ["most", "top", "highest"]):
        return "TOP"

    if any(w in q for w in ["overview", "summary", "analyze"]):
        return "SUMMARY"

    return "GENERAL"

# ================= SQL GENERATION =================
def generate_sql(intent, q):
    q = q.lower()

    if intent == "COUNT":
        if "pending" in q:
            return f"SELECT COUNT(*) AS value FROM {TABLE_NAME} WHERE resolution_status='Pending'"
        if "negative" in q:
            return f"SELECT COUNT(*) AS value FROM {TABLE_NAME} WHERE sentiment='Negative'"
        return f"SELECT COUNT(*) AS value FROM {TABLE_NAME}"

    if intent in ["TOP", "DISTRIBUTION"]:
        if "sentiment" in q:
            return f"""
            SELECT issue_type, sentiment, COUNT(*) AS count
            FROM {TABLE_NAME}
            GROUP BY issue_type, sentiment
            """
        if "pending" in q:
            return f"""
            SELECT issue_type, COUNT(*) AS count
            FROM {TABLE_NAME}
            WHERE resolution_status='Pending'
            GROUP BY issue_type
            ORDER BY count DESC
            """
        return f"""
        SELECT issue_type, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type
        ORDER BY count DESC
        """

    if intent in ["WHY", "SUMMARY", "GENERAL"]:
        return f"""
        SELECT issue_type, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type
        ORDER BY count DESC
        """

# ================= INSIGHT ENGINE (INTENT-BASED) =================
def generate_summary(intent, question, df):
    q = question.lower()

    if df.empty:
        return "No data available."

    top = df.iloc[0]
    total = df["count"].sum()
    pct = (top["count"] / total) * 100

    if intent == "WHY":
        return (
            f"The main reason is **{top['issue_type']}** issues, "
            f"which account for **{pct:.0f}%** of the total cases. "
            f"This imbalance explains the observed increase."
        )

    if intent == "SUMMARY":
        return (
            f"Overall, **{top['issue_type']}** is the most frequent issue type, "
            f"indicating it is the dominant contributor to customer problems."
        )

    return "Here is a summary of the data."

# ================= UI =================
st.subheader("💬 Ask a question")
question = st.text_input("Ask anything about customers, issues, sentiment, service…")

if st.button("Ask") and question:
    intent = detect_intent(question)
    sql = generate_sql(intent, question)
    result = con.execute(sql).fetchdf()

    # ---------- COUNT ----------
    if intent == "COUNT":
        st.metric("Result", int(result.iloc[0, 0]))

    # ---------- WHY ----------
    elif intent == "WHY":
        st.success(generate_summary(intent, question, result))

    # ---------- DISTRIBUTION ----------
    elif intent == "DISTRIBUTION":
        pivot = result.pivot(index="issue_type", columns="sentiment", values="count").fillna(0)
        st.bar_chart(pivot)

    # ---------- TOP ----------
    elif intent == "TOP":
        st.bar_chart(result.set_index("issue_type"))

    # ---------- SUMMARY / GENERAL ----------
    else:
        st.success(generate_summary(intent, question, result))

# ================= SIDEBAR =================
st.sidebar.header("📌 Example Questions")
st.sidebar.markdown("""
- Count of unresolved issues
- Why pending cases are increasing?
- Show sentiment distribution by issue
- Which issue type has most complaints?
- Give an overview of customer issues
""")
