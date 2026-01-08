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

    if any(w in q for w in ["problems", "facing"]):
        return "PROBLEMS"

    if any(w in q for w in ["overview", "summary", "analyze"]):
        return "SUMMARY"

    return "GENERAL"

# ================= SQL GENERATION =================
def generate_sql(intent, q):
    q = q.lower()

    if intent == "COUNT":
        if "pending" in q:
            return f"SELECT COUNT(*) AS value FROM {TABLE_NAME} WHERE resolution_status='Pending'"
        if "negative" in q or "frustrated" in q:
            return f"SELECT COUNT(*) AS value FROM {TABLE_NAME} WHERE sentiment='Negative'"
        return f"SELECT COUNT(*) AS value FROM {TABLE_NAME}"

    if intent == "DISTRIBUTION":
        return f"""
        SELECT issue_type, sentiment, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type, sentiment
        """

    if intent in ["TOP", "WHY", "SUMMARY", "PROBLEMS", "GENERAL"]:
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

# ================= SUMMARY / WHY ENGINE =================
def generate_text(intent, question, df):
    q = question.lower()

    if df.empty:
        return "No data available."

    total = df["count"].sum()

    # ---------- WHY (INTENT-AWARE) ----------
    if intent == "WHY":

        def explain(keyword, label):
            sub = df[df["issue_type"].str.contains(keyword, case=False)]
            if not sub.empty:
                cnt = sub.iloc[0]["count"]
                pct = (cnt / total) * 100
                return (
                    f"{label} issues impact customers because they account for "
                    f"**{pct:.0f}%** of reported cases, indicating resolution and process gaps."
                )
            return None

        if "service" in q or "satisfaction" in q:
            return explain("general", "Service")

        if "delivery" in q:
            return explain("delivery", "Delivery")

        if "product" in q:
            return explain("product", "Product")

        if "refund" in q:
            return explain("refund", "Refund")

        if "pending" in q or "unresolved" in q:
            top = df.iloc[0]
            pct = (top["count"] / total) * 100
            return (
                f"Pending cases are increasing mainly due to **{top['issue_type']}** issues, "
                f"which contribute **{pct:.0f}%** of unresolved cases."
            )

        top = df.iloc[0]
        pct = (top["count"] / total) * 100
        return (
            f"The primary reason is **{top['issue_type']}** issues, "
            f"accounting for **{pct:.0f}%** of total cases."
        )

    # ---------- PROBLEMS / MULTI-ISSUE SUMMARY ----------
    if intent in ["PROBLEMS", "SUMMARY", "GENERAL"]:
        top_issues = df.head(3)
        issue_list = ", ".join(top_issues["issue_type"])
        top = top_issues.iloc[0]
        pct = (top["count"] / total) * 100
        return (
            f"Customers mainly face issues related to **{issue_list}**, "
            f"with **{top['issue_type']}** being the most frequent, "
            f"contributing **{pct:.0f}%** of reported cases."
        )

# ================= UI =================
st.subheader("💬 Ask a question")
question = st.text_input("Ask anything about customers, issues, sentiment, service…")

if st.button("Ask") and question:
    intent = detect_intent(question)
    sql = generate_sql(intent, question)
    result = con.execute(sql).fetchdf()

    # COUNT → KPI
    if intent == "COUNT":
        st.metric("Result", int(result.iloc[0, 0]))

    # WHY / SUMMARY / PROBLEMS → TEXT ONLY
    elif intent in ["WHY", "SUMMARY", "PROBLEMS", "GENERAL"]:
        st.success(generate_text(intent, question, result))

    # DISTRIBUTION → CHART ONLY
    elif intent == "DISTRIBUTION":
        pivot = result.pivot(
            index="issue_type",
            columns="sentiment",
            values="count"
        ).fillna(0)
        st.bar_chart(pivot)

    # TOP → CHART ONLY
    elif intent == "TOP":
        st.bar_chart(result.set_index("issue_type"))

# ================= SIDEBAR =================
st.sidebar.header("📌 Example Questions")
st.sidebar.markdown("""
- Count of unresolved issues
- Why pending cases are increasing?
- Why service issues affect customer satisfaction?
- What problems are customers facing?
- Show sentiment distribution by issue
- Which issue type has most complaints?
- Give an overview of customer issues
""")
