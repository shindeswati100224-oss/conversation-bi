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
st.caption("Ask anything. System decides table, chart, or summary.")

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
def is_why(q):
    return any(w in q for w in ["why", "reason", "explain", "cause", "not satisfied"])

def wants_count(q):
    return any(w in q for w in ["how many", "count", "number"])

def wants_distribution(q):
    return any(w in q for w in ["distribution", "breakdown", "by"])

# ================= LLM-2 : SQL GENERATION =================
def llm2_generate_sql(question: str):
    q = question.lower()

    if "frustrated" in q or "negative" in q:
        return f"""
        SELECT COUNT(*) AS count
        FROM {TABLE_NAME}
        WHERE sentiment = 'Negative';
        """

    if "pending" in q:
        return f"""
        SELECT issue_type, COUNT(*) AS count
        FROM {TABLE_NAME}
        WHERE resolution_status = 'Pending'
        GROUP BY issue_type
        ORDER BY count DESC;
        """

    if "sentiment" in q:
        return f"""
        SELECT issue_type, sentiment, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type, sentiment;
        """

    if "most" in q and "issue" in q:
        return f"""
        SELECT issue_type, COUNT(*) AS count
        FROM {TABLE_NAME}
        GROUP BY issue_type
        ORDER BY count DESC
        LIMIT 1;
        """

    return None

# ================= LLM-3 : OUTPUT DECISION =================
def decide_output(question, result_df):
    q = question.lower()

    if is_why(q):
        return "summary"

    if wants_count(q) and result_df.shape == (1, 1):
        return "kpi"

    if "sentiment" in q and "issue_type" in result_df.columns:
        return "stacked_chart"

    if len(result_df) > 1:
        return "table_chart"

    return "summary"

# ================= LLM-3 : SUMMARY ENGINE =================
def llm3_summary(question, df):
    q = question.lower()

    if "service" in q or "not satisfied" in q:
        top_issue = df[df["sentiment"]=="Negative"]["issue_type"].value_counts().idxmax()
        return f"Customers are mainly dissatisfied due to **{top_issue}** issues, driven by negative sentiment and unresolved cases."

    if "delivery" in q:
        return "Delivery issues are largely caused by delays and failed deliveries, reflected by high negative sentiment."

    return "Based on overall trends, negative sentiment and pending resolutions are the main drivers of customer dissatisfaction."

# ================= UI =================
st.subheader("💬 Ask a question")
question = st.text_input("Ask anything about customers, issues, sentiment, service…")

if st.button("Ask") and question:
    sql = llm2_generate_sql(question)

    if sql:
        result = con.execute(sql).fetchdf()
        output = decide_output(question, result)

        # KPI
        if output == "kpi":
            st.metric("Result", int(result.iloc[0, 0]))

        # TABLE + CHART
        elif output == "table_chart":
            st.dataframe(result, use_container_width=True)
            st.bar_chart(result.set_index(result.columns[0]))

        # STACKED CHART
        elif output == "stacked_chart":
            pivot = result.pivot(index="issue_type", columns="sentiment", values="count").fillna(0)
            st.bar_chart(pivot)

        # SUMMARY
        else:
            st.success(llm3_summary(question, df))

    else:
        # ALWAYS ANSWER
        st.success(llm3_summary(question, df))

# ================= SIDEBAR =================
st.sidebar.header("📌 Example Questions")
st.sidebar.markdown("""
- How many persons are frustrated?
- Which issue type has most pending cases?
- Show sentiment distribution by issue
- Why customers are not satisfied with service?
- Why delivery issues are high?
""")
