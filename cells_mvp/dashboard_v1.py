"""
═══════════════════════════════════════════════════════════════════════════════
  BIOCELLS DISCOVERY · Cockpit Ejecutivo
  Dashboard multi-línea de negocio · Streamlit + Neon (PostgreSQL)
───────────────────────────────────────────────────────────────────────────────
  Líneas de negocio:
    1. Diagnóstico Molecular
    2. Cultivo Celular
    3. Bioinformática / Análisis
    4. Ventas / Clientes
  + Resumen Ejecutivo Global (cockpit cruzado)

  Funcionalidades:
    · Acceso protegido por contraseña (st.secrets)
    · Capa de datos conmutable: Neon (prod) ó CSV local (dev/test)
    · KPIs con variación vs. período anterior (Δ%)
    · Alertas operativas por reglas (lo que requiere atención directiva)
    · Gráficos interactivos (Plotly)
    · Descarga de reporte PDF por pantalla
    · Envío del reporte por correo (SMTP, desde tu cuenta)

  Ejecutar:   streamlit run biocells_dashboard.py
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import io
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage

import matplotlib
matplotlib.use("Agg")                 # backend sin display, obligatorio para PDF
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ═══════════════════════════════════════════════════════════════════════════════
#  1 · CONFIGURACIÓN GLOBAL  (todo lo sensible vive en .streamlit/secrets.toml)
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Biocells · Cockpit Ejecutivo",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Fuente de datos: "neon" (producción) | "csv" (pruebas locales) ──────────────
# Defínelo en secrets como  data_source = "neon"  o sobreescribe aquí.
DATA_SOURCE = st.secrets.get("data_source", "csv")
CSV_DIR     = st.secrets.get("csv_dir", "./biocells_data")   # solo modo csv

# ── Identidad de marca (cámbialo cuando me pases los links de Cloudinary) ───────
BRAND = {
    "nombre":    "Biocells Discovery",
    "logo_url":  st.secrets.get("brand_logo_url", "https://res.cloudinary.com/dwcqgcl0m/image/upload/q_auto/f_auto/v1781110167/biocells-v-b_mvomrd.png"),  
    "primary":   "#0EA5A4",   # teal
    "secondary": "#2563EB",   # azul
    "accent":    "#7C3AED",   # violeta
    "ok":        "#16A34A",
    "warn":      "#D97706",
    "bad":       "#DC2626",
    "ink":       "#0F172A",
    "muted":     "#64748B",
    "bg_soft":   "#F1F5F9",
}
SEQ = [BRAND["primary"], BRAND["secondary"], BRAND["accent"],
       "#F59E0B", "#EC4899", "#10B981", "#6366F1", "#14B8A6"]

PLOTLY_TEMPLATE = "plotly_white"


# ═══════════════════════════════════════════════════════════════════════════════
#  2 · ESTILOS (CSS ligero para una UI limpia y muy visual)
# ═══════════════════════════════════════════════════════════════════════════════

def inject_css():
    st.markdown(f"""
    <style>
      .block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1500px; }}
      h1, h2, h3 {{ letter-spacing: -0.02em; }}
      .hero {{
        background: linear-gradient(120deg, {BRAND['primary']}22, {BRAND['secondary']}18);
        border: 1px solid {BRAND['primary']}44; border-radius: 18px;
        padding: 20px 26px; margin-bottom: 14px;
      }}
      .hero h1 {{ margin: 0; font-size: 1.7rem; }}
      .hero p  {{ margin: 4px 0 0; font-size: .95rem; opacity: 0.72; }}
      .exec-summary {{
        background: var(--secondary-background-color);
        border-left: 5px solid {BRAND['primary']};
        border-radius: 10px; padding: 14px 18px; margin: 6px 0 18px;
        box-shadow: 0 1px 3px rgba(15,23,42,.08); font-size: .96rem; line-height: 1.55;
      }}
      .alert {{ border-radius: 10px; padding: 11px 15px; margin: 6px 0; font-size: .9rem; }}
      .alert-bad  {{ background: {BRAND['bad']}30;  border-left: 4px solid {BRAND['bad']};  }}
      .alert-warn {{ background: {BRAND['warn']}30; border-left: 4px solid {BRAND['warn']}; }}
      .alert-ok   {{ background: {BRAND['ok']}30;   border-left: 4px solid {BRAND['ok']};   }}
      div[data-testid="stMetric"] {{
        background: var(--secondary-background-color);
        border: 1px solid rgba(128,128,128,0.2); border-radius: 14px;
        padding: 14px 16px; box-shadow: 0 1px 2px rgba(15,23,42,.05);
      }}
      div[data-testid="stMetricLabel"] {{ font-weight: 600; opacity: 0.75; }}
      section[data-testid="stSidebar"] {{ background: {BRAND['ink']}; }}
      section[data-testid="stSidebar"] * {{ color: #E2E8F0 !important; }}
      section[data-testid="stSidebar"] .stRadio label {{ font-size: .95rem; }}
    </style>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  3 · AUTENTICACIÓN (contraseña única definida en secrets)
# ═══════════════════════════════════════════════════════════════════════════════

def check_password() -> bool:
    expected = st.secrets.get("app_password", "biocells2026")  # cámbialo en secrets
    if st.session_state.get("auth_ok"):
        return True

    st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
    c = st.columns([1, 1.2, 1])[1]
    with c:
        if BRAND["logo_url"]:
            st.image(BRAND["logo_url"], width=180)
        st.markdown(f"### 🧬 {BRAND['nombre']}")
        st.caption("Cockpit Ejecutivo · Acceso restringido")
        pwd = st.text_input("Contraseña", type="password", key="pwd_in")
        if st.button("Ingresar", type="primary", use_container_width=True):
            if pwd == expected:
                st.session_state["auth_ok"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#  4 · CAPA DE DATOS  (Neon vía SQLAlchemy  ó  CSV local) — todo cacheado
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def get_engine():
    """Engine SQLAlchemy hacia Neon. Solo se usa si DATA_SOURCE == 'neon'."""
    from sqlalchemy import create_engine
    url = st.secrets["neon_url"]      # ej: postgresql+psycopg2://user:pass@host/db?sslmode=require
    return create_engine(url, pool_pre_ping=True)


def _read_table(name: str) -> pd.DataFrame:
    if DATA_SOURCE == "neon":
        return pd.read_sql(f'SELECT * FROM {name}', get_engine())
    return pd.read_csv(f"{CSV_DIR}/{name}.csv")


@st.cache_data(ttl=900, show_spinner="Cargando datos…")
def load_line(line: str) -> pd.DataFrame:
    """
    Devuelve la fact desnormalizada (unida a sus dims + dim_fecha).
    Mismo resultado en modo Neon o CSV: se hace el join en pandas para
    garantizar columnas idénticas y evitar dialectos SQL.
    """
    fecha = _read_table("dim_fecha")[["fecha_id", "fecha", "anio", "trimestre", "mes", "dia_semana"]]
    fecha["fecha"] = pd.to_datetime(fecha["fecha"])
    emp = _read_table("dim_empleado")[["empleado_id", "nombre", "rol", "departamento", "nivel"]] \
        .rename(columns={"nombre": "empleado"})

    if line == "diagnostico":
        f = _read_table("fact_diagnostico")
        pr = _read_table("dim_prueba_dx").rename(columns={"nombre_prueba": "prueba"})
        mu = _read_table("dim_muestra")[["muestra_id", "tipo_muestra", "origen", "conservacion"]]
        df = (f.merge(fecha, on="fecha_id").merge(pr, on="prueba_id")
                .merge(mu, on="muestra_id").merge(emp, on="empleado_id"))

    elif line == "cultivo":
        f = _read_table("fact_cultivo")
        lc = _read_table("dim_linea_celular").rename(columns={"nombre_linea": "linea", "tipo": "tipo_linea"})
        br = _read_table("dim_biorreactor").rename(columns={"codigo": "biorreactor", "tipo": "tipo_reactor"})
        df = (f.merge(fecha, on="fecha_id").merge(lc, on="linea_id")
                .merge(br, on="biorreactor_id").merge(emp, on="empleado_id"))

    elif line == "bio":
        f = _read_table("fact_analisis_bio")
        pi = _read_table("dim_pipeline").rename(columns={"nombre": "pipeline"})
        df = (f.merge(fecha, on="fecha_id").merge(pi, on="pipeline_id").merge(emp, on="empleado_id"))

    elif line == "ventas":
        f = _read_table("fact_ventas")
        cl = _read_table("dim_cliente").rename(columns={"nombre": "cliente", "tipo": "cliente_tipo"})
        ps = _read_table("dim_producto_servicio").rename(columns={"nombre": "producto"})
        df = (f.merge(fecha, on="fecha_id").merge(cl, on="cliente_id")
                .merge(ps, on="producto_id").merge(emp, on="empleado_id"))
    else:
        raise ValueError(line)

    return df.sort_values("fecha").reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  5 · HELPERS (períodos, deltas, formato)
# ═══════════════════════════════════════════════════════════════════════════════

def slice_periodo(df, ini, fin):
    """Devuelve (actual, anterior). El período anterior es del mismo largo, justo antes."""
    ini, fin = pd.Timestamp(ini), pd.Timestamp(fin)
    dur = fin - ini
    prev_ini, prev_fin = ini - dur - timedelta(days=1), ini - timedelta(days=1)
    cur  = df[(df["fecha"] >= ini)      & (df["fecha"] <= fin)]
    prev = df[(df["fecha"] >= prev_ini) & (df["fecha"] <= prev_fin)]
    return cur, prev


def delta_pct(cur, prev):
    if prev in (0, None) or pd.isna(prev):
        return None
    return (cur - prev) / prev * 100


def fmt_money(x):  return f"${x:,.0f}"
def fmt_int(x):    return f"{x:,.0f}"
def fmt_pct(x):    return f"{x:.1f}%"
def hex_alpha(hex_color, alpha=0.13):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"rgba({r},{g},{b},{alpha})"


def kpi_card(col, label, value, delta=None, inverse=False, help_txt=None):
    """st.metric con Δ. inverse=True → subir es malo (rojo)."""
    kwargs = {}
    if delta is not None:
        kwargs["delta"] = f"{delta:+.1f}%"
        kwargs["delta_color"] = "inverse" if inverse else "normal"
    if help_txt:
        kwargs["help"] = help_txt
    col.metric(label, value, **kwargs)


def alert(level, msg):
    cls = {"bad": "alert-bad", "warn": "alert-warn", "ok": "alert-ok"}[level]
    icon = {"bad": "🔴", "warn": "🟠", "ok": "🟢"}[level]
    st.markdown(f"<div class='alert {cls}'>{icon}&nbsp; {msg}</div>", unsafe_allow_html=True)


def hero(title, subtitle):
    st.markdown(
        f"<div class='hero'><h1>{title}</h1><p>{subtitle}</p></div>",
        unsafe_allow_html=True,
    )


def style_fig(fig, h=340):
    fig.update_layout(
        template=PLOTLY_TEMPLATE, height=h,
        margin=dict(l=10, r=10, t=40, b=10),
        colorway=SEQ, font=dict(size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig


def monthly(df, value=None, agg="count"):
    """Serie mensual lista para line/bar charts."""
    g = df.copy()
    g["periodo"] = g["fecha"].dt.to_period("M").dt.to_timestamp()
    if agg == "count":
        out = g.groupby("periodo").size().reset_index(name="valor")
    else:
        out = g.groupby("periodo")[value].agg(agg).reset_index(name="valor")
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  6 · REPORTE PDF  (reportlab + matplotlib, sin dependencias de binarios)
# ═══════════════════════════════════════════════════════════════════════════════

def _mpl_bar(data_x, data_y, title, color, horizontal=False, xlabel="", ylabel=""):
    fig, ax = plt.subplots(figsize=(5.2, 2.6), dpi=130)
    data_x = list(data_x); data_y = list(data_y)
    if horizontal:
        bars = ax.barh(data_x, data_y, color=color)
        ax.invert_yaxis()
        for bar, v in zip(bars, data_y):
            ax.text(v + max(data_y) * 0.02, bar.get_y() + bar.get_height() / 2,
                    f"{v:,.0f}", va="center", ha="left", fontsize=6.5, fontweight="bold",
                    color=BRAND["ink"])
        ax.set_xlabel(xlabel or "Valor", fontsize=7)
    else:
        bars = ax.bar(data_x, data_y, color=color)
        for bar, v in zip(bars, data_y):
            ax.text(bar.get_x() + bar.get_width() / 2, v + max(data_y) * 0.02,
                    f"{v:,.0f}", ha="center", va="bottom", fontsize=6.5, fontweight="bold",
                    color=BRAND["ink"])
        plt.xticks(rotation=30, ha="right", fontsize=7)
        ax.set_xlabel(xlabel, fontsize=7)
        ax.set_ylabel(ylabel or "Valor", fontsize=7)
    ax.set_title(title, fontsize=9, fontweight="bold", color=BRAND["ink"])
    ax.tick_params(labelsize=7)
    ax.set_ylim(0, max(data_y) * 1.18) if not horizontal else None
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def build_pdf(titulo, periodo_txt, kpis, alertas, charts):
    """
    kpis:    lista de (label, valor_str, delta_str|"")
    alertas: lista de (nivel, texto)
    charts:  lista de BytesIO (PNGs de matplotlib)
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, Image as RLImage)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.4*cm, bottomMargin=1.4*cm,
                            leftMargin=1.6*cm, rightMargin=1.6*cm)
    ss = getSampleStyleSheet()
    H = ParagraphStyle("H", parent=ss["Title"], fontSize=18, textColor=colors.HexColor(BRAND["ink"]))
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=9.5, textColor=colors.HexColor(BRAND["muted"]))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, textColor=colors.HexColor(BRAND["primary"]))
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=9.5, leading=14)

    el = []
    el.append(Paragraph(f"{BRAND['nombre']} — {titulo}", H))
    el.append(Paragraph(f"Período: {periodo_txt} · Generado {date.today():%d/%m/%Y}", sub))
    el.append(Spacer(1, 0.5*cm))

    # KPIs en tabla
    el.append(Paragraph("Indicadores clave", h2))
    rows = [["Indicador", "Valor", "Δ vs período anterior"]]
    rows += [[k[0], k[1], k[2]] for k in kpis]
    t = Table(rows, colWidths=[7.5*cm, 4.5*cm, 5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BRAND["primary"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    el.append(t)
    el.append(Spacer(1, 0.5*cm))

    # Alertas
    el.append(Paragraph("Puntos de atención", h2))
    if alertas:
        for lvl, txt in alertas:
            tag = {"bad": "🔴", "warn": "🟠", "ok": "🟢"}[lvl]
            el.append(Paragraph(f"{tag} {txt}", body))
    else:
        el.append(Paragraph("Sin alertas en el período.", body))
    el.append(Spacer(1, 0.4*cm))

    # Gráficos (2 por fila)
    el.append(Paragraph("Visión gráfica", h2))
    imgs = [RLImage(c, width=8*cm, height=4*cm) for c in charts]
    for i in range(0, len(imgs), 2):
        pair = imgs[i:i+2]
        el.append(Table([pair], colWidths=[8.5*cm]*len(pair)))
        el.append(Spacer(1, 0.3*cm))

    el.append(Spacer(1, 0.6*cm))
    el.append(Paragraph("Documento confidencial — uso interno directivo.", sub))
    doc.build(el)
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════════════════════════════════════
#  7 · ENVÍO DE CORREO  (SMTP, desde tu cuenta · credenciales en secrets)
# ═══════════════════════════════════════════════════════════════════════════════

def send_email(destino, asunto, cuerpo, pdf_bytes, filename):
    cfg = st.secrets.get("smtp", {})
    host = cfg.get("host", "smtp.gmail.com")
    port = int(cfg.get("port", 587))
    user = cfg.get("user")          # tu correo
    pwd  = cfg.get("password")      # App Password (NO tu contraseña normal)
    sender = cfg.get("from", user)
    if not (user and pwd):
        raise RuntimeError("Faltan credenciales SMTP en secrets ([smtp] user/password).")

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = sender
    msg["To"] = destino
    msg.set_content(cuerpo)
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)


def report_controls(page_key, titulo, periodo_txt, kpis, alertas, charts):
    """Bloque reutilizable: descargar PDF + enviar por correo."""
    st.divider()
    st.subheader("📄 Reporte ejecutivo")
    pdf = build_pdf(titulo, periodo_txt, kpis, alertas, charts)
    fname = f"Biocells_{page_key}_{date.today():%Y%m%d}.pdf"

    c1, c2 = st.columns(2)
    c1.download_button("⬇️  Descargar PDF", data=pdf.getvalue(),
                       file_name=fname, mime="application/pdf",
                       use_container_width=True, key=f"dl_{page_key}")

    with c2.popover("✉️  Enviar por correo", use_container_width=True):
        dest = st.text_input("Correo destino", key=f"to_{page_key}")
        extra = st.text_area("Mensaje (opcional)", key=f"msg_{page_key}", height=80)
        if st.button("Enviar reporte", type="primary", key=f"send_{page_key}"):
            if not dest:
                st.warning("Ingresa un correo destino.")
            else:
                try:
                    cuerpo = (extra + "\n\n" if extra else "") + \
                             f"Adjunto el reporte de {titulo} ({periodo_txt}).\n\n— {BRAND['nombre']}"
                    send_email(dest, f"[Biocells] {titulo} — {periodo_txt}",
                               cuerpo, pdf.getvalue(), fname)
                    st.success(f"Enviado a {dest}.")
                except Exception as e:
                    st.error(f"No se pudo enviar: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  8 · PÁGINAS POR LÍNEA DE NEGOCIO
# ═══════════════════════════════════════════════════════════════════════════════

def page_overview(rango):
    hero("Resumen Ejecutivo Global",
         "Estado consolidado de las 4 líneas de negocio · vista de dirección")
    ini, fin = rango
    periodo_txt = f"{ini:%d/%m/%Y} – {fin:%d/%m/%Y}"

    ventas = load_line("ventas");      v_cur, v_prev = slice_periodo(ventas, ini, fin)
    dx     = load_line("diagnostico"); d_cur, _      = slice_periodo(dx, ini, fin)
    cul    = load_line("cultivo");     c_cur, _      = slice_periodo(cul, ini, fin)
    bio    = load_line("bio");         b_cur, _      = slice_periodo(bio, ini, fin)

    ingreso_cur  = v_cur.loc[v_cur["estado_orden"] == "Cobrada", "total_usd"].sum()
    ingreso_prev = v_prev.loc[v_prev["estado_orden"] == "Cobrada", "total_usd"].sum()

    _delta = delta_pct(ingreso_cur, ingreso_prev)
    _delta_txt = (
        f"({'+' if _delta >= 0 else ''}{_delta:.1f}% vs. período previo) "
        if _delta is not None else ""
    )
    st.markdown(
        f"<div class='exec-summary'>En el período <b>{periodo_txt}</b>, Biocells generó "
        f"<b>{fmt_money(ingreso_cur)}</b> en ingresos cobrados {_delta_txt}"
        f"Operación: <b>{len(d_cur)}</b> diagnósticos, <b>{len(c_cur)}</b> cultivos, "
        f"<b>{len(b_cur)}</b> análisis bioinformáticos.</div>",
        unsafe_allow_html=True,
    )

    k = st.columns(4)
    kpi_card(k[0], "Ingresos cobrados", fmt_money(ingreso_cur), delta_pct(ingreso_cur, ingreso_prev))
    tasa_exito = (c_cur["resultado"] == "Exitoso").mean()*100 if len(c_cur) else 0
    kpi_card(k[1], "Tasa éxito cultivo", fmt_pct(tasa_exito))
    completados = (b_cur["estado"] == "Completado").mean()*100 if len(b_cur) else 0
    kpi_card(k[2], "Análisis completados", fmt_pct(completados))
    positividad = (d_cur["resultado"] == "Positivo").mean()*100 if len(d_cur) else 0
    kpi_card(k[3], "Positividad Dx", fmt_pct(positividad))

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Ingresos cobrados por mes**")
        mv = monthly(v_cur[v_cur["estado_orden"] == "Cobrada"], "total_usd", "sum")
        fig = px.area(mv, x="periodo", y="valor", markers=True)
        fig.update_traces(line_color=BRAND["primary"], fillcolor=hex_alpha(BRAND["primary"]))
        st.plotly_chart(style_fig(fig), use_container_width=True)
        #añadir labels en la parte superior de cada barra
    with c2:
        st.markdown("**Volumen operativo por línea**")
        vol = pd.DataFrame({
            "Línea": ["Diagnóstico", "Cultivo", "Bioinformática", "Ventas"],
            "Operaciones": [len(d_cur), len(c_cur), len(b_cur), len(v_cur)],
        })
        fig = px.bar(vol, x="Línea", y="Operaciones", color="Línea",
                     text="Operaciones")
        fig.update_traces(texttemplate="<b>%{text}</b>", textposition="outside",
                          textfont=dict(size=16, color=BRAND["ink"]))
        fig.update_layout(showlegend=False, yaxis_visible=True,
                          yaxis=dict(title="Operaciones", showticklabels=False, showgrid=False, zeroline=False),
                          uniformtext_minsize=16, uniformtext_mode="show",
                          yaxis_range=[0, vol["Operaciones"].max() * 1.25])
        st.plotly_chart(style_fig(fig), use_container_width=True)

    # Salud por línea (semáforo)
    st.markdown("**Tablero de salud por línea**")
    contam = (c_cur["resultado"] == "Contaminado").mean()*100 if len(c_cur) else 0
    fallidos = (b_cur["estado"] == "Fallido").mean()*100 if len(b_cur) else 0
    cancel = (v_cur["estado_orden"] == "Cancelada").mean()*100 if len(v_cur) else 0
    repet = d_cur["repeticion"].mean()*100 if len(d_cur) else 0
    salud = pd.DataFrame([
        ["Diagnóstico", f"{len(d_cur)} pruebas", f"Repetición {repet:.1f}%", "🟠" if repet > 10 else "🟢"],
        ["Cultivo", f"{len(c_cur)} cultivos", f"Contaminación {contam:.1f}%", "🔴" if contam > 10 else "🟢"],
        ["Bioinformática", f"{len(b_cur)} análisis", f"Fallidos {fallidos:.1f}%", "🟠" if fallidos > 8 else "🟢"],
        ["Ventas", fmt_money(ingreso_cur), f"Cancelación {cancel:.1f}%", "🔴" if cancel > 12 else "🟢"],
    ], columns=["Línea", "Volumen", "Indicador crítico", "Estado"])
    st.dataframe(salud, use_container_width=True, hide_index=True)

    charts = [
        _mpl_bar(vol["Línea"], vol["Operaciones"], "Volumen por línea", BRAND["primary"],
                 ylabel="Operaciones"),
        _mpl_bar([d.strftime("%b'%y") for d in mv["periodo"]], mv["valor"], "Ingresos/mes", BRAND["secondary"],
                 xlabel="Mes", ylabel="USD"),
    ]
    _d = delta_pct(ingreso_cur, ingreso_prev)
    kpis = [("Ingresos cobrados", fmt_money(ingreso_cur), f"{_d:+.1f}%" if _d is not None else ""),
            ("Tasa éxito cultivo", fmt_pct(tasa_exito), ""),
            ("Análisis completados", fmt_pct(completados), ""),
            ("Positividad Dx", fmt_pct(positividad), "")]
    alertas = []
    if contam > 10: alertas.append(("bad", f"Contaminación de cultivos elevada: {contam:.1f}%"))
    if cancel > 12: alertas.append(("bad", f"Tasa de cancelación de ventas alta: {cancel:.1f}%"))
    if fallidos > 8: alertas.append(("warn", f"Análisis bioinformáticos fallidos: {fallidos:.1f}%"))
    report_controls("overview", "Resumen Ejecutivo Global", periodo_txt, kpis, alertas, charts)


def page_diagnostico(rango):
    hero("Diagnóstico Molecular", "Volumen, calidad analítica y eficiencia operativa")
    ini, fin = rango; periodo_txt = f"{ini:%d/%m/%Y} – {fin:%d/%m/%Y}"
    df = load_line("diagnostico"); cur, prev = slice_periodo(df, ini, fin)
    if cur.empty:
        st.warning("Sin datos en el período seleccionado."); return

    vol = len(cur); vol_p = len(prev)
    pos = (cur["resultado"] == "Positivo").mean()*100
    t_proc = cur["tiempo_proceso_horas"].mean(); t_proc_p = prev["tiempo_proceso_horas"].mean() if len(prev) else None
    repet = cur["repeticion"].mean()*100; repet_p = prev["repeticion"].mean()*100 if len(prev) else None
    costo = cur["costo_real_usd"].mean()
    invalido = (cur["resultado"] == "Inválido").mean()*100

    st.markdown(f"<div class='exec-summary'>Se procesaron <b>{vol}</b> pruebas diagnósticas "
                f"con <b>{fmt_pct(pos)}</b> de positividad. Tiempo medio de proceso "
                f"<b>{t_proc:.1f} h</b>; tasa de repetición <b>{fmt_pct(repet)}</b>.</div>",
                unsafe_allow_html=True)

    k = st.columns(5)
    kpi_card(k[0], "Pruebas", fmt_int(vol), delta_pct(vol, vol_p))
    kpi_card(k[1], "Positividad", fmt_pct(pos))
    kpi_card(k[2], "Tiempo proceso (h)", f"{t_proc:.1f}", delta_pct(t_proc, t_proc_p), inverse=True)
    kpi_card(k[3], "Tasa repetición", fmt_pct(repet), delta_pct(repet, repet_p), inverse=True)
    kpi_card(k[4], "Costo medio", fmt_money(costo))

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Pruebas por mes**")
        m = monthly(cur)
        st.plotly_chart(style_fig(px.bar(m, x="periodo", y="valor")), use_container_width=True)
    with c2:
        st.markdown("**Distribución de resultados**")
        r = cur["resultado"].value_counts().reset_index()
        r.columns = ["resultado", "n"]
        st.plotly_chart(style_fig(px.pie(r, names="resultado", values="n", hole=.55)), use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**Top pruebas por volumen**")
        top = cur["prueba"].value_counts().head(8).reset_index()
        top.columns = ["prueba", "n"]
        st.plotly_chart(style_fig(px.bar(top, x="n", y="prueba", orientation="h")
                                  .update_layout(yaxis=dict(autorange="reversed"))), use_container_width=True)
    with c4:
        st.markdown("**Tiempo de proceso por metodología**")
        st.plotly_chart(style_fig(px.box(cur, x="metodologia", y="tiempo_proceso_horas")),
                        use_container_width=True)

    st.markdown("**Calidad de muestra por tipo**")
    q = cur.groupby(["tipo_muestra", "calidad_muestra"]).size().reset_index(name="n")
    st.plotly_chart(style_fig(px.bar(q, x="tipo_muestra", y="n", color="calidad_muestra", barmode="stack"), 320),
                    use_container_width=True)

    alertas = []
    if repet > 10:  alertas.append(("warn", f"Tasa de repetición sobre umbral (10%): {repet:.1f}%"))
    if invalido > 6: alertas.append(("bad", f"Resultados inválidos elevados: {invalido:.1f}%"))
    if t_proc > 40: alertas.append(("warn", f"Tiempo de proceso medio alto: {t_proc:.1f} h"))
    if not alertas: alertas.append(("ok", "Indicadores dentro de rangos esperados."))
    for lvl, m_ in alertas: alert(lvl, m_)

    with st.expander("🔎 Ver registros"):
        st.dataframe(cur[["fecha", "prueba", "metodologia", "resultado", "calidad_muestra",
                          "tiempo_proceso_horas", "costo_real_usd", "empleado"]].head(300),
                     use_container_width=True, hide_index=True)

    charts = [
        _mpl_bar([d.strftime("%b'%y") for d in m["periodo"]], m["valor"], "Pruebas/mes", BRAND["primary"],
                 xlabel="Mes", ylabel="Pruebas"),
        _mpl_bar(top["prueba"], top["n"], "Top pruebas", BRAND["secondary"], horizontal=True,
                 xlabel="Cantidad"),
    ]
    _dv = delta_pct(vol, vol_p); _dt = delta_pct(t_proc, t_proc_p); _dr = delta_pct(repet, repet_p)
    kpis = [("Pruebas", fmt_int(vol), f"{_dv:+.1f}%" if _dv is not None else ""),
            ("Positividad", fmt_pct(pos), ""),
            ("Tiempo proceso (h)", f"{t_proc:.1f}", f"{_dt:+.1f}%" if _dt is not None else ""),
            ("Tasa repetición", fmt_pct(repet), f"{_dr:+.1f}%" if _dr is not None else ""),
            ("Costo medio", fmt_money(costo), "")]
    report_controls("diagnostico", "Diagnóstico Molecular", periodo_txt, kpis, alertas, charts)


def page_cultivo(rango):
    hero("Cultivo Celular", "Rendimiento, viabilidad y control de contaminación")
    ini, fin = rango; periodo_txt = f"{ini:%d/%m/%Y} – {fin:%d/%m/%Y}"
    df = load_line("cultivo"); cur, prev = slice_periodo(df, ini, fin)
    if cur.empty:
        st.warning("Sin datos en el período seleccionado."); return

    vol = len(cur); vol_p = len(prev)
    exito = (cur["resultado"] == "Exitoso").mean()*100
    exito_p = (prev["resultado"] == "Exitoso").mean()*100 if len(prev) else None
    viab = cur["viabilidad_pct"].mean()
    contam = (cur["resultado"] == "Contaminado").mean()*100
    contam_p = (prev["resultado"] == "Contaminado").mean()*100 if len(prev) else None
    rend = cur["rendimiento_mg"].mean()

    st.markdown(f"<div class='exec-summary'>Se ejecutaron <b>{vol}</b> cultivos con "
                f"<b>{fmt_pct(exito)}</b> de éxito y viabilidad media de <b>{viab:.1f}%</b>. "
                f"Contaminación <b>{fmt_pct(contam)}</b>.</div>", unsafe_allow_html=True)

    k = st.columns(5)
    kpi_card(k[0], "Cultivos", fmt_int(vol), delta_pct(vol, vol_p))
    kpi_card(k[1], "Tasa éxito", fmt_pct(exito), delta_pct(exito, exito_p))
    kpi_card(k[2], "Viabilidad media", fmt_pct(viab))
    kpi_card(k[3], "Contaminación", fmt_pct(contam), delta_pct(contam, contam_p), inverse=True)
    kpi_card(k[4], "Rendimiento (mg)", f"{rend:.1f}" if not pd.isna(rend) else "—")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Cultivos por mes**")
        m = monthly(cur)
        st.plotly_chart(style_fig(px.bar(m, x="periodo", y="valor")), use_container_width=True)
    with c2:
        st.markdown("**Distribución de resultados**")
        r = cur["resultado"].value_counts().reset_index(); r.columns = ["resultado", "n"]
        st.plotly_chart(style_fig(px.pie(r, names="resultado", values="n", hole=.55)), use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**Viabilidad por tipo de línea**")
        st.plotly_chart(style_fig(px.box(cur, x="tipo_linea", y="viabilidad_pct")), use_container_width=True)
    with c4:
        st.markdown("**Contaminación por biorreactor**")
        cb = (cur.assign(contam=(cur["resultado"] == "Contaminado"))
                 .groupby("tipo_reactor")["contam"].mean().mul(100).reset_index())
        st.plotly_chart(style_fig(px.bar(cb, x="tipo_reactor", y="contam")
                                  .update_yaxes(title="% contaminación")), use_container_width=True)

    st.markdown("**Rendimiento por organismo**")
    ro = cur.groupby("organismo")["rendimiento_mg"].mean().reset_index().dropna()
    st.plotly_chart(style_fig(px.bar(ro, x="organismo", y="rendimiento_mg"), 320), use_container_width=True)

    alertas = []
    if contam > 10: alertas.append(("bad", f"Contaminación sobre umbral crítico (10%): {contam:.1f}%"))
    if viab < 80:   alertas.append(("warn", f"Viabilidad media baja: {viab:.1f}%"))
    peor = cb.sort_values("contam", ascending=False).iloc[0] if not cb.empty else None
    if peor is not None and peor["contam"] > 12:
        alertas.append(("warn", f"Biorreactor '{peor['tipo_reactor']}' con contaminación {peor['contam']:.1f}%"))
    if not alertas: alertas.append(("ok", "Producción celular dentro de parámetros."))
    for lvl, m_ in alertas: alert(lvl, m_)

    with st.expander("🔎 Ver registros"):
        st.dataframe(cur[["fecha", "linea", "tipo_linea", "organismo", "biorreactor", "resultado",
                          "viabilidad_pct", "rendimiento_mg", "empleado"]].head(300),
                     use_container_width=True, hide_index=True)

    charts = [
        _mpl_bar([d.strftime("%b'%y") for d in m["periodo"]], m["valor"], "Cultivos/mes", BRAND["primary"],
                 xlabel="Mes", ylabel="Cultivos"),
        _mpl_bar(cb["tipo_reactor"], cb["contam"], "% contaminación x reactor", BRAND["bad"],
                 xlabel="Biorreactor", ylabel="% Contaminación"),
    ]
    _dv = delta_pct(vol, vol_p); _de = delta_pct(exito, exito_p); _dc = delta_pct(contam, contam_p)
    kpis = [("Cultivos", fmt_int(vol), f"{_dv:+.1f}%" if _dv is not None else ""),
            ("Tasa éxito", fmt_pct(exito), f"{_de:+.1f}%" if _de is not None else ""),
            ("Viabilidad media", fmt_pct(viab), ""),
            ("Contaminación", fmt_pct(contam), f"{_dc:+.1f}%" if _dc is not None else ""),
            ("Rendimiento (mg)", f"{rend:.1f}" if not pd.isna(rend) else "—", "")]
    report_controls("cultivo", "Cultivo Celular", periodo_txt, kpis, alertas, charts)


def page_bio(rango):
    hero("Bioinformática / Análisis", "Throughput, costo de cómputo y calidad de secuenciación")
    ini, fin = rango; periodo_txt = f"{ini:%d/%m/%Y} – {fin:%d/%m/%Y}"
    df = load_line("bio"); cur, prev = slice_periodo(df, ini, fin)
    if cur.empty:
        st.warning("Sin datos en el período seleccionado."); return

    vol = len(cur); vol_p = len(prev)
    compl = (cur["estado"] == "Completado").mean()*100
    fallidos = (cur["estado"] == "Fallido").mean()*100
    t_comp = cur["tiempo_computo_min"].mean()
    q30 = cur["calidad_q30_pct"].mean()
    costo_tot = cur["costo_computo_usd"].sum()
    costo_tot_p = prev["costo_computo_usd"].sum() if len(prev) else None

    st.markdown(f"<div class='exec-summary'>Se corrieron <b>{vol}</b> análisis "
                f"(<b>{fmt_pct(compl)}</b> completados). Costo de cómputo total "
                f"<b>{fmt_money(costo_tot)}</b>; Q30 medio <b>{fmt_pct(q30)}</b>.</div>",
                unsafe_allow_html=True)

    k = st.columns(5)
    kpi_card(k[0], "Análisis", fmt_int(vol), delta_pct(vol, vol_p))
    kpi_card(k[1], "Completados", fmt_pct(compl))
    kpi_card(k[2], "Tiempo cómputo (min)", f"{t_comp:.0f}", inverse=True)
    kpi_card(k[3], "Q30 medio", fmt_pct(q30))
    kpi_card(k[4], "Costo cómputo", fmt_money(costo_tot), delta_pct(costo_tot, costo_tot_p), inverse=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Análisis por mes**")
        m = monthly(cur)
        st.plotly_chart(style_fig(px.bar(m, x="periodo", y="valor")), use_container_width=True)
    with c2:
        st.markdown("**Estado de los análisis**")
        r = cur["estado"].value_counts().reset_index(); r.columns = ["estado", "n"]
        st.plotly_chart(style_fig(px.pie(r, names="estado", values="n", hole=.55)), use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**Costo de cómputo por pipeline**")
        cp = cur.groupby("pipeline")["costo_computo_usd"].sum().sort_values(ascending=False).head(8).reset_index()
        st.plotly_chart(style_fig(px.bar(cp, x="costo_computo_usd", y="pipeline", orientation="h")
                                  .update_layout(yaxis=dict(autorange="reversed"))), use_container_width=True)
    with c4:
        st.markdown("**Cobertura vs. variantes detectadas**")
        st.plotly_chart(style_fig(px.scatter(cur, x="cobertura_media_x", y="variantes_detectadas",
                                             color="estado", opacity=.6)), use_container_width=True)

    st.markdown("**Tiempo de cómputo por pipeline (min)**")
    tp = cur.groupby("pipeline")["tiempo_computo_min"].mean().sort_values(ascending=False).head(10).reset_index()
    st.plotly_chart(style_fig(px.bar(tp, x="pipeline", y="tiempo_computo_min"), 320), use_container_width=True)

    alertas = []
    if fallidos > 8: alertas.append(("bad", f"Análisis fallidos sobre umbral: {fallidos:.1f}%"))
    if q30 < 80:     alertas.append(("warn", f"Calidad Q30 media baja: {q30:.1f}%"))
    en_cola = (cur["estado"] == "En Cola").mean()*100
    if en_cola > 10: alertas.append(("warn", f"Backlog en cola elevado: {en_cola:.1f}%"))
    if not alertas: alertas.append(("ok", "Pipelines operando dentro de lo esperado."))
    for lvl, m_ in alertas: alert(lvl, m_)

    with st.expander("🔎 Ver registros"):
        st.dataframe(cur[["fecha", "pipeline", "herramienta_principal", "estado",
                          "tiempo_computo_min", "calidad_q30_pct", "cobertura_media_x",
                          "costo_computo_usd", "empleado"]].head(300),
                     use_container_width=True, hide_index=True)

    charts = [
        _mpl_bar([d.strftime("%b'%y") for d in m["periodo"]], m["valor"], "Análisis/mes", BRAND["primary"],
                 xlabel="Mes", ylabel="Análisis"),
        _mpl_bar(cp["pipeline"], cp["costo_computo_usd"], "Costo x pipeline", BRAND["accent"], horizontal=True,
                 xlabel="USD"),
    ]
    _dv = delta_pct(vol, vol_p); _dct = delta_pct(costo_tot, costo_tot_p)
    kpis = [("Análisis", fmt_int(vol), f"{_dv:+.1f}%" if _dv is not None else ""),
            ("Completados", fmt_pct(compl), ""),
            ("Tiempo cómputo (min)", f"{t_comp:.0f}", ""),
            ("Q30 medio", fmt_pct(q30), ""),
            ("Costo cómputo", fmt_money(costo_tot), f"{_dct:+.1f}%" if _dct is not None else "")]
    report_controls("bio", "Bioinformática / Análisis", periodo_txt, kpis, alertas, charts)


def page_ventas(rango):
    hero("Ventas / Clientes", "Ingresos, mix comercial y salud del portafolio de clientes")
    ini, fin = rango; periodo_txt = f"{ini:%d/%m/%Y} – {fin:%d/%m/%Y}"
    df = load_line("ventas"); cur, prev = slice_periodo(df, ini, fin)
    if cur.empty:
        st.warning("Sin datos en el período seleccionado."); return

    cobrada = cur[cur["estado_orden"] == "Cobrada"]
    cobrada_p = prev[prev["estado_orden"] == "Cobrada"] if len(prev) else prev
    ingreso = cobrada["total_usd"].sum(); ingreso_p = cobrada_p["total_usd"].sum() if len(cobrada_p) else None
    n_ord = len(cur); n_ord_p = len(prev)
    ticket = cur["total_usd"].mean()
    cancel = (cur["estado_orden"] == "Cancelada").mean()*100
    cancel_p = (prev["estado_orden"] == "Cancelada").mean()*100 if len(prev) else None
    desc = cur["descuento_pct"].mean()

    st.markdown(f"<div class='exec-summary'>Ingresos cobrados de <b>{fmt_money(ingreso)}</b> "
                f"sobre <b>{n_ord}</b> órdenes (ticket medio <b>{fmt_money(ticket)}</b>). "
                f"Cancelación <b>{fmt_pct(cancel)}</b>; descuento medio <b>{fmt_pct(desc)}</b>.</div>",
                unsafe_allow_html=True)

    k = st.columns(5)
    kpi_card(k[0], "Ingresos cobrados", fmt_money(ingreso), delta_pct(ingreso, ingreso_p))
    kpi_card(k[1], "Órdenes", fmt_int(n_ord), delta_pct(n_ord, n_ord_p))
    kpi_card(k[2], "Ticket medio", fmt_money(ticket))
    kpi_card(k[3], "Tasa cancelación", fmt_pct(cancel), delta_pct(cancel, cancel_p), inverse=True)
    kpi_card(k[4], "Descuento medio", fmt_pct(desc), inverse=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Ingresos cobrados por mes**")
        m = monthly(cobrada, "total_usd", "sum")
        fig = px.area(m, x="periodo", y="valor", markers=True)
        fig.update_traces(line_color=BRAND["primary"], fillcolor=hex_alpha(BRAND["primary"]))
        st.plotly_chart(style_fig(fig), use_container_width=True)
    with c2:
        st.markdown("**Mix de ingresos por categoría**")
        cat = cobrada.groupby("categoria")["total_usd"].sum().reset_index()
        st.plotly_chart(style_fig(px.pie(cat, names="categoria", values="total_usd", hole=.55)),
                        use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**Ingresos por país**")
        pais = cobrada.groupby("pais")["total_usd"].sum().sort_values(ascending=False).reset_index()
        st.plotly_chart(style_fig(px.bar(pais, x="pais", y="total_usd")), use_container_width=True)
    with c4:
        st.markdown("**Ingresos por canal**")
        can = cobrada.groupby("canal")["total_usd"].sum().reset_index()
        st.plotly_chart(style_fig(px.pie(can, names="canal", values="total_usd", hole=.55)),
                        use_container_width=True)

    c5, c6 = st.columns(2)
    with c5:
        st.markdown("**Top 10 clientes por ingreso**")
        topc = cobrada.groupby("cliente")["total_usd"].sum().sort_values(ascending=False).head(10).reset_index()
        st.plotly_chart(style_fig(px.bar(topc, x="total_usd", y="cliente", orientation="h")
                                  .update_layout(yaxis=dict(autorange="reversed"))), use_container_width=True)
    with c6:
        st.markdown("**Estado de las órdenes**")
        eo = cur["estado_orden"].value_counts().reset_index(); eo.columns = ["estado", "n"]
        st.plotly_chart(style_fig(px.bar(eo, x="estado", y="n", color="estado")
                                  .update_layout(showlegend=False)), use_container_width=True)

    alertas = []
    if cancel > 12: alertas.append(("bad", f"Tasa de cancelación elevada: {cancel:.1f}%"))
    if desc > 18:   alertas.append(("warn", f"Descuento medio alto erosionando margen: {desc:.1f}%"))
    if not topc.empty:
        conc = topc["total_usd"].iloc[0] / ingreso * 100 if ingreso else 0
        if conc > 15: alertas.append(("warn", f"Concentración: el cliente top representa {conc:.1f}% del ingreso"))
    if not alertas: alertas.append(("ok", "Operación comercial saludable."))
    for lvl, m_ in alertas: alert(lvl, m_)

    with st.expander("🔎 Ver registros"):
        st.dataframe(cur[["fecha", "cliente", "pais", "producto", "categoria", "canal",
                          "estado_orden", "cantidad", "descuento_pct", "total_usd", "empleado"]].head(300),
                     use_container_width=True, hide_index=True)

    charts = [
        _mpl_bar([d.strftime("%b'%y") for d in m["periodo"]], m["valor"], "Ingresos/mes", BRAND["primary"],
                 xlabel="Mes", ylabel="USD"),
        _mpl_bar(pais["pais"], pais["total_usd"], "Ingresos por país", BRAND["secondary"],
                 xlabel="País", ylabel="USD"),
    ]
    _di = delta_pct(ingreso, ingreso_p); _dn = delta_pct(n_ord, n_ord_p); _dc = delta_pct(cancel, cancel_p)
    kpis = [("Ingresos cobrados", fmt_money(ingreso), f"{_di:+.1f}%" if _di is not None else ""),
            ("Órdenes", fmt_int(n_ord), f"{_dn:+.1f}%" if _dn is not None else ""),
            ("Ticket medio", fmt_money(ticket), ""),
            ("Tasa cancelación", fmt_pct(cancel), f"{_dc:+.1f}%" if _dc is not None else ""),
            ("Descuento medio", fmt_pct(desc), "")]
    report_controls("ventas", "Ventas / Clientes", periodo_txt, kpis, alertas, charts)


# ═══════════════════════════════════════════════════════════════════════════════
#  9 · APP  (router + sidebar)
# ═══════════════════════════════════════════════════════════════════════════════

PAGES = {
    "🏠  Resumen Ejecutivo": page_overview,
    "🧪  Diagnóstico Molecular": page_diagnostico,
    "🔬  Cultivo Celular": page_cultivo,
    "💻  Bioinformática": page_bio,
    "💰  Ventas / Clientes": page_ventas,
}


def main():
    inject_css()
    if not check_password():
        return

    with st.sidebar:
        if BRAND["logo_url"]:
            st.image(BRAND["logo_url"], use_container_width=True)
        st.markdown(f"## {BRAND['nombre']}")
        st.caption("Cockpit Ejecutivo")
        st.divider()
        choice = st.radio("Línea de negocio", list(PAGES.keys()), label_visibility="collapsed")
        st.divider()

        # Filtro global de fechas
        fechas = load_line("ventas")["fecha"]
        fmin, fmax = fechas.min().date(), fechas.max().date()
        st.markdown("**Período**")
        preset = st.selectbox("Rango rápido",
                              ["Todo", "Último año", "Últimos 6 meses", "Últimos 3 meses", "Personalizado"])
        if preset == "Todo":
            rango = (fmin, fmax)
        elif preset == "Último año":
            rango = (max(fmin, fmax - timedelta(days=365)), fmax)
        elif preset == "Últimos 6 meses":
            rango = (max(fmin, fmax - timedelta(days=182)), fmax)
        elif preset == "Últimos 3 meses":
            rango = (max(fmin, fmax - timedelta(days=91)), fmax)
        else:
            rango = st.date_input("Selecciona rango", (fmin, fmax), min_value=fmin, max_value=fmax)
            if isinstance(rango, (list, tuple)) and len(rango) == 2:
                pass
            else:
                rango = (fmin, fmax)

        st.divider()
        st.caption(f"Fuente: {'Neon' if DATA_SOURCE=='neon' else 'CSV local'}")
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state["auth_ok"] = False
            st.rerun()

    PAGES[choice]((pd.Timestamp(rango[0]), pd.Timestamp(rango[1])))


if __name__ == "__main__":
    main()