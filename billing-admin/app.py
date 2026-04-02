"""Billing Admin Dashboard — Streamlit entry point."""

import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from db import get_breeder_billing_table, get_invoices_for_breeder, get_summary_metrics

load_dotenv()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

st.set_page_config(page_title="Breedly Billing Admin", page_icon="💰", layout="wide")


# ── Authentication ────────────────────────────────────────────────────────────
def check_login():
    """Simple password-based login gate using session state."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("💰 Breedly Billing Admin")
        st.subheader("Login")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login"):
            if password == ADMIN_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid password.")
        st.stop()


check_login()

# ── Sidebar Navigation ───────────────────────────────────────────────────────
st.sidebar.title("💰 Billing Admin")
st.sidebar.divider()
page = st.sidebar.radio(
    "Navigation",
    ["📊 Overview", "🏠 Breeders", "🧾 Invoices"],
    label_visibility="collapsed",
)
st.sidebar.divider()
if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()
st.sidebar.caption("Data refreshes on page reload")


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: Overview
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Overview":
    st.title("📊 Billing Overview")

    try:
        metrics = get_summary_metrics()
    except Exception as e:
        st.error(f"Failed to load metrics: {e}")
        st.stop()

    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Subscriptions", metrics["total_active_subscriptions"])
    c2.metric("Total Revenue", f"${metrics['total_revenue']:,.2f}")
    c3.metric("Overdue Invoices", metrics["overdue_invoices_count"])
    c4.metric("Plans in Use", len(metrics["subscriptions_by_plan"]))

    st.divider()

    # Subscriptions by plan bar chart
    st.subheader("Active Subscriptions by Plan")
    subs_by_plan = metrics["subscriptions_by_plan"]
    if subs_by_plan:
        df_plan = pd.DataFrame(
            [{"Plan": name, "Subscriptions": count} for name, count in subs_by_plan.items()]
        )
        fig = px.bar(
            df_plan,
            x="Plan",
            y="Subscriptions",
            color="Plan",
            text="Subscriptions",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Count")
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No active subscriptions found.")


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: Breeders
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏠 Breeders":
    st.title("🏠 Breeder Billing")

    # Filters
    col_plan, col_status = st.columns(2)
    plan_filter = col_plan.selectbox("Filter by Plan", [None, "Free", "Pro", "Premium"], format_func=lambda x: "All Plans" if x is None else x)
    status_filter = col_status.selectbox("Filter by Status", [None, "active", "canceled", "past_due"], format_func=lambda x: "All Statuses" if x is None else x)

    try:
        df = get_breeder_billing_table(plan_filter=plan_filter, status_filter=status_filter)
    except Exception as e:
        st.error(f"Failed to load breeder data: {e}")
        st.stop()

    if df.empty:
        st.info("No breeders found matching the selected filters.")
    else:
        st.subheader(f"Breeders ({len(df)})")
        st.dataframe(
            df.rename(columns={
                "email": "Email",
                "breedery_name": "Breedery Name",
                "plan_name": "Plan",
                "subscription_status": "Status",
                "stripe_customer_id": "Stripe Customer",
                "last_invoice_date": "Last Invoice Date",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: Invoices
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🧾 Invoices":
    st.title("🧾 Invoice Details")

    # Load breeders for the dropdown
    try:
        df_breeders = get_breeder_billing_table()
    except Exception as e:
        st.error(f"Failed to load breeder list: {e}")
        st.stop()

    if df_breeders.empty:
        st.info("No breeders with subscriptions found.")
        st.stop()

    # Build breeder options: email -> user_id lookup via a secondary query
    breeder_emails = df_breeders["email"].tolist()
    selected_email = st.selectbox("Select Breeder", breeder_emails)

    if selected_email:
        # Look up user_id for the selected breeder
        from db import engine
        from sqlalchemy import text as sa_text

        with engine.connect() as conn:
            row = conn.execute(
                sa_text("SELECT id FROM users WHERE email = :email"),
                {"email": selected_email},
            ).fetchone()

        if row is None:
            st.warning("Breeder not found in database.")
            st.stop()

        user_id = row[0]

        try:
            df_invoices = get_invoices_for_breeder(user_id)
        except Exception as e:
            st.error(f"Failed to load invoices: {e}")
            st.stop()

        if df_invoices.empty:
            st.info(f"No invoices found for {selected_email}.")
        else:
            st.subheader(f"Invoices for {selected_email}")
            st.dataframe(
                df_invoices.rename(columns={
                    "date": "Date",
                    "amount": "Amount",
                    "status": "Status",
                    "period_start": "Period Start",
                    "period_end": "Period End",
                    "stripe_invoice_id": "Stripe Invoice",
                }),
                use_container_width=True,
                hide_index=True,
            )
