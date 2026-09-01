import streamlit as st


def apply_styles():
    st.markdown(
        """
        <style>
        :root {
          --fw-accent: #176b55;
          --fw-accent2: #2f7e9d;
          --fw-soft: #eef7f3;
          --fw-border: rgba(80,90,100,.18);
        }
        .block-container { padding-top: 1.2rem; padding-bottom: 3rem; }
        .hero {
          border: 1px solid var(--fw-border);
          border-radius: 18px;
          padding: 24px 26px;
          margin: 4px 0 20px 0;
          background: linear-gradient(135deg, rgba(23,107,85,.08), rgba(47,126,157,.06));
        }
        .hero-kicker { font-size: .78rem; letter-spacing: .09em; font-weight: 700; opacity:.72; }
        .hero-title { font-size: 2rem; font-weight: 800; margin-top: 5px; }
        .hero-sub { margin-top: 6px; opacity:.76; }
        .role-chip {
          display:inline-block; padding:6px 10px; border-radius:999px;
          background:rgba(23,107,85,.10); border:1px solid rgba(23,107,85,.25); font-size:.83rem;
        }
        .callout {
          border-left: 4px solid var(--fw-accent);
          padding: 10px 14px;
          background: rgba(23,107,85,.06);
          border-radius: 8px;
          margin-bottom: 12px;
        }
        .stButton > button { min-height: 44px; border-radius: 11px; font-weight: 600; }
        div[data-testid="stMetric"] {
          border: 1px solid var(--fw-border);
          padding: 14px;
          border-radius: 14px;
          background: rgba(255,255,255,.02);
        }
        div[data-testid="stForm"] { border-radius: 16px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(kicker: str, title: str, subtitle: str):
    st.markdown(
        f"""
        <div class="hero">
          <div class="hero-kicker">{kicker}</div>
          <div class="hero-title">{title}</div>
          <div class="hero-sub">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
