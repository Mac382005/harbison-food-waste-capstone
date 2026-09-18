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
          --fw-text-soft: rgba(34, 42, 53, .72);
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
        .legend-wrap {
          display:flex;
          flex-wrap:wrap;
          gap:10px;
          margin: 6px 0 14px 0;
        }
        .legend-chip {
          display:inline-flex;
          align-items:center;
          gap:8px;
          padding:8px 12px;
          border:1px solid var(--fw-border);
          border-radius:999px;
          background:#fff;
          font-size:0.88rem;
        }
        .legend-dot {
          width:12px;
          height:12px;
          border-radius:50%;
          display:inline-block;
        }
        .section-note {
          color: var(--fw-text-soft);
          font-size: 0.92rem;
          margin-top: -4px;
          margin-bottom: 10px;
        }
        .source-badge-row {
          display:flex;
          flex-wrap:wrap;
          gap:8px;
          margin: 2px 0 12px 0;
        }
        .source-badge {
          display:inline-block;
          padding: 6px 10px;
          border-radius: 999px;
          font-size: 0.82rem;
          font-weight: 600;
          border: 1px solid transparent;
        }
        .source-green { background:#e9f8ef; color:#1b6e39; border-color:#b9e7c9; }
        .source-blue { background:#eaf4ff; color:#1252a3; border-color:#bfd8ff; }
        .source-orange { background:#fff3e8; color:#9a4d00; border-color:#ffd4aa; }
        .source-purple { background:#f4ebff; color:#6e34b8; border-color:#dcc7ff; }
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



def render_legend(items: list[tuple[str, str]]):
    chips = "".join(
        f'<div class="legend-chip"><span class="legend-dot" style="background:{color}"></span>{label}</div>'
        for label, color in items
    )
    st.markdown(f'<div class="legend-wrap">{chips}</div>', unsafe_allow_html=True)



def render_source_badges(items: list[tuple[str, str]]):
    badges = "".join(
        f'<span class="source-badge {css_class}">{label}</span>' for label, css_class in items
    )
    st.markdown(f'<div class="source-badge-row">{badges}</div>', unsafe_allow_html=True)
