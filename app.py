import io
import re
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

st.set_page_config(page_title="Tanulói teljesítmény elemző", layout="wide")

ANGOL_SZINT_LABELS = {
    0: "0. szint - pre-A1 alatti szint",
    1: "1. szint - pre-A1 szint",
    2: "2. szint - A1 szint",
    3: "3. szint - A2 szint",
    4: "4. szint - B1 szint",
    5: "5. szint - B2 szint",
    6: "6. szint - C1 szint vagy fölötte",
}

NYELVI_TERULETEK = ["angol", "német", "nemet", "idegen"]


def clean_text(x) -> str:
    if pd.isna(x):
        return ""
    return " ".join(str(x).replace("\t", " ").split())


def is_year_sheet(name: str) -> bool:
    n = str(name).strip().lower()
    return n != "azonosítók" and n != "azonositok" and not n.startswith("sheet")


def decode_level(value, language=False) -> Optional[float]:
    txt = clean_text(value).lower().replace("–", "-")
    if txt in ["", "nincs", "nan", "none"]:
        return None
    if language:
        if "pre-a1" in txt and "alatti" in txt:
            return 0
        if "pre-a1" in txt:
            return 1
        if re.search(r"\ba1\b", txt):
            return 2
        if re.search(r"\ba2\b", txt):
            return 3
        if re.search(r"\bb1\b", txt):
            return 4
        if re.search(r"\bb2\b", txt):
            return 5
        if re.search(r"\bc1\b", txt):
            return 6
    m = re.search(r"(\d+)", txt)
    return float(m.group(1)) if m else None


def to_number(value) -> Optional[float]:
    if pd.isna(value):
        return None
    txt = clean_text(value).replace(",", ".")
    if txt.lower() in ["", "nincs", "nan", "none"]:
        return None
    try:
        return float(txt)
    except Exception:
        return None


def read_id_sheet(xls: pd.ExcelFile) -> pd.DataFrame:
    sheet = None
    for s in xls.sheet_names:
        if str(s).strip().lower() in ["azonosítók", "azonositok"]:
            sheet = s
            break
    if sheet is None:
        return pd.DataFrame(columns=["id", "name"])
    raw = pd.read_excel(xls, sheet_name=sheet, header=None)
    out = raw.iloc[:, :2].copy()
    out.columns = ["id", "name"]
    out = out.iloc[1:].dropna(how="all")
    out["id"] = out["id"].apply(clean_text)
    out["name"] = out["name"].apply(clean_text)
    out = out[(out["id"] != "") & (out["name"] != "")]
    out["label"] = out["name"] + " (" + out["id"] + ")"
    return out.reset_index(drop=True)


def detect_areas(xls: pd.ExcelFile) -> List[str]:
    areas = []
    for sheet in xls.sheet_names:
        if not is_year_sheet(sheet):
            continue
        raw = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=3)
        row0 = [clean_text(v) for v in raw.iloc[0].tolist()]
        for val in row0[2:]:
            if val and val not in areas:
                areas.append(val)
    return areas



def read_level_boundaries(xls: pd.ExcelFile) -> pd.DataFrame:
    """
    Opcionális munkalap beolvasása képességpont-határokhoz.
    Javasolt munkalapnév: Szint_határok
    Javasolt oszlopok: Kompetenciaterület | Szint | Alsó ponthatár
    Elfogadott alternatívák: Terület, Képességszint, Ponthatár, Képességpont alsó ponthatár
    """
    candidate_names = [
        "szint_határok", "szint_hatarok", "szinthatárok", "szinthatarok",
        "ponthatárok", "ponthatarok", "határok", "hatarok"
    ]
    sheet = None
    for s in xls.sheet_names:
        if str(s).strip().lower() in candidate_names:
            sheet = s
            break
    if sheet is None:
        return pd.DataFrame(columns=["Kompetenciaterület", "Szint", "Alsó ponthatár"])

    raw = pd.read_excel(xls, sheet_name=sheet)
    if raw.empty:
        return pd.DataFrame(columns=["Kompetenciaterület", "Szint", "Alsó ponthatár"])

    colmap = {clean_text(c).lower(): c for c in raw.columns}

    def pick(options):
        for o in options:
            if o in colmap:
                return colmap[o]
        return None

    area_col = pick(["kompetenciaterület", "kompetenciamérési terület", "terület", "terulet", "kompetencia terület"])
    level_col = pick(["szint", "képességszint", "kepessegszint", "képességszint neve"])
    point_col = pick(["alsó ponthatár", "also ponthatar", "ponthatár", "ponthatar", "képességpont alsó ponthatár", "kepessegpont also ponthatar"])

    # Ha nincs pontos oszlopnév, az első három oszlopot próbáljuk használni.
    if area_col is None or level_col is None or point_col is None:
        if raw.shape[1] >= 3:
            area_col = raw.columns[0]
            level_col = raw.columns[1]
            point_col = raw.columns[2]
        else:
            return pd.DataFrame(columns=["Kompetenciaterület", "Szint", "Alsó ponthatár"])

    out = raw[[area_col, level_col, point_col]].copy()
    out.columns = ["Kompetenciaterület", "Szint", "Alsó ponthatár"]
    out["Kompetenciaterület"] = out["Kompetenciaterület"].apply(clean_text)
    out["Szint"] = out["Szint"].apply(clean_text)
    out["Alsó ponthatár"] = out["Alsó ponthatár"].apply(to_number)
    out = out[(out["Kompetenciaterület"] != "") & out["Alsó ponthatár"].notna()]
    return out.reset_index(drop=True)


def get_area_boundaries(boundaries: pd.DataFrame, area: str) -> pd.DataFrame:
    if boundaries is None or boundaries.empty:
        return pd.DataFrame(columns=["Kompetenciaterület", "Szint", "Alsó ponthatár"])
    area_norm = clean_text(area).lower()
    b = boundaries[boundaries["Kompetenciaterület"].apply(lambda x: clean_text(x).lower()) == area_norm].copy()
    if b.empty:
        # Részleges egyezés, ha pl. az Excelben "Matematika" helyett "matematika kompetencia" szerepel.
        b = boundaries[boundaries["Kompetenciaterület"].apply(lambda x: area_norm in clean_text(x).lower() or clean_text(x).lower() in area_norm)].copy()
    return b.sort_values("Alsó ponthatár").reset_index(drop=True)

def area_columns(raw: pd.DataFrame, area: str) -> List[int]:
    row0 = [clean_text(v) for v in raw.iloc[0].tolist()]
    cols = [i for i, v in enumerate(row0) if v == area]
    if not cols:
        return []
    # Az Excelben az első sorban csak az adott terület első cellája van kitöltve.
    start = cols[0]
    next_starts = [i for i in range(start + 1, len(row0)) if row0[i] != ""]
    end = next_starts[0] if next_starts else raw.shape[1]
    return list(range(start, end))


def extract_student_records(xls: pd.ExcelFile, student_id: str, area: str) -> pd.DataFrame:
    records = []
    language = any(k in area.lower() for k in NYELVI_TERULETEK)
    for sheet in xls.sheet_names:
        if not is_year_sheet(sheet):
            continue
        raw = pd.read_excel(xls, sheet_name=sheet, header=None)
        if raw.shape[0] < 4:
            continue
        cols = area_columns(raw, area)
        if not cols:
            continue
        ids = raw.iloc[3:, 0].apply(clean_text)
        matches = ids[ids == student_id]
        if matches.empty:
            continue
        ridx = matches.index[0]
        for c in cols:
            period = clean_text(raw.iat[1, c])
            metric = clean_text(raw.iat[2, c])
            if not period or metric not in ["Képességpont", "Képességszint"]:
                continue
            p_low = period.lower()
            # Egy tanévben két oszlopcsoportot használunk: előzetes és végleges.
            if "előzetes" in p_low or "elozetes" in p_low:
                status = "Előzetes"
            elif "végleges" in p_low or "vegleges" in p_low:
                status = "Végleges"
            else:
                continue
            val_raw = raw.iat[ridx, c]
            value = to_number(val_raw) if metric == "Képességpont" else decode_level(val_raw, language)
            records.append({
                "Munkalap": sheet,
                "Tanév": sheet,
                "Kompetenciaterület": area,
                "Eredménytípus": status,
                "Mutató": metric,
                "Érték": value,
                "Eredeti érték": clean_text(val_raw),
            })
    return pd.DataFrame(records)


def make_chart(data: pd.DataFrame, student_name: str, area: str, metric: str, boundaries: Optional[pd.DataFrame] = None) -> plt.Figure:
    d = data[data["Mutató"] == metric].copy()
    years = sorted(d["Tanév"].unique().tolist())[:5]
    statuses = ["Előzetes", "Végleges"]
    pivot = d.pivot_table(index="Tanév", columns="Eredménytípus", values="Érték", aggfunc="first").reindex(years)
    fig, ax = plt.subplots(figsize=(12, 5.5))
    x = np.arange(len(years))
    width = 0.35
    for i, status in enumerate(statuses):
        vals = [pivot.loc[y, status] if status in pivot.columns and pd.notna(pivot.loc[y, status]) else np.nan for y in years]
        bars = ax.bar(x + (i - 0.5) * width, vals, width, label=status)
        for bar, val in zip(bars, vals):
            if pd.notna(val):
                label = f"{int(val)}" if abs(val - int(val)) < 1e-9 else f"{val:.1f}"
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), label, ha="center", va="bottom", fontsize=9)
    ax.set_title(f"{student_name} - {area} - {metric} több tanév alapján")
    ax.set_xlabel("Mérési tanév")
    ax.set_ylabel(metric)
    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=0)
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    if metric == "Képességpont":
        ax.set_ylim(800, 2200)
        area_boundaries = get_area_boundaries(boundaries, area) if boundaries is not None else pd.DataFrame()
        if not area_boundaries.empty:
            for _, row in area_boundaries.iterrows():
                y = row["Alsó ponthatár"]
                if pd.notna(y) and 800 <= y <= 2200:
                    label = clean_text(row["Szint"])
                    label = label if label else f"{int(y)} pont"
                    ax.axhline(y, color="gray", linestyle="--", linewidth=1, alpha=0.75)
                    ax.text(
                        len(years) - 0.45, y + 8,
                        f"{label}: {int(y)}",
                        ha="right", va="bottom", fontsize=8, color="dimgray",
                        bbox=dict(facecolor="white", edgecolor="none", alpha=0.65, pad=1.5),
                    )
    if metric == "Képességszint":
        language = any(k in area.lower() for k in NYELVI_TERULETEK)
        if language:
            ax.set_yticks(list(ANGOL_SZINT_LABELS.keys()))
            ax.set_yticklabels([ANGOL_SZINT_LABELS[i] for i in ANGOL_SZINT_LABELS], fontsize=8)
            ax.set_ylim(0, 6.6)
        else:
            mx = max([v for v in d["Érték"].dropna().tolist()] + [7])
            ax.set_yticks(np.arange(0, int(max(7, mx)) + 1, 1))
            ax.set_ylim(0, max(7, mx) + 0.6)
    fig.tight_layout()
    return fig


def make_pdf(data: pd.DataFrame, student_name: str, student_id: str, area: str, selected_metric: str, boundaries: Optional[pd.DataFrame] = None) -> bytes:
    """PDF egy kompetenciaterülethez. Csak diagramokat tartalmaz, adattáblát nem."""
    bio = io.BytesIO()
    metrics = [selected_metric, "Képességpont" if selected_metric == "Képességszint" else "Képességszint"]
    with PdfPages(bio) as pdf:
        for metric in metrics:
            if data[data["Mutató"] == metric]["Érték"].notna().any():
                fig = make_chart(data, student_name, area, metric, boundaries)
                pdf.savefig(fig)
                plt.close(fig)
    bio.seek(0)
    return bio.getvalue()


def make_pdf_all_areas(xls: pd.ExcelFile, areas: List[str], student_name: str, student_id: str, selected_metric: str, boundaries: Optional[pd.DataFrame] = None) -> bytes:
    """PDF az összes kompetenciaterülethez. Területenként csak diagramokat tartalmaz."""
    bio = io.BytesIO()
    metrics = [selected_metric, "Képességpont" if selected_metric == "Képességszint" else "Képességszint"]
    with PdfPages(bio) as pdf:
        has_any_page = False
        for area in areas:
            data = extract_student_records(xls, student_id, area)
            if data.empty:
                continue
            data = data.sort_values(["Tanév", "Eredménytípus", "Mutató"])
            for metric in metrics:
                if data[data["Mutató"] == metric]["Érték"].notna().any():
                    fig = make_chart(data, student_name, area, metric, boundaries)
                    pdf.savefig(fig)
                    plt.close(fig)
                    has_any_page = True
        if not has_any_page:
            fig, ax = plt.subplots(figsize=(11.7, 8.3))
            ax.axis("off")
            ax.text(0.5, 0.5, "Nem található megjeleníthető adat.", ha="center", va="center", fontsize=16)
            pdf.savefig(fig)
            plt.close(fig)
    bio.seek(0)
    return bio.getvalue()

st.title("Tanulói teljesítmény elemző - több tanév")
st.caption("Egy kiválasztott tanuló előzetes és végleges eredményeinek megjelenítése kompetenciaterületenként.")

uploaded = st.file_uploader("Excel fájl feltöltése", type=["xlsx"])
if uploaded is None:
    st.info("Töltsd fel a több tanévet tartalmazó Excel fájlt.")
    st.stop()

try:
    xls = pd.ExcelFile(uploaded)
except Exception as e:
    st.error(f"Nem sikerült beolvasni az Excelt: {e}")
    st.stop()

ids = read_id_sheet(xls)
areas = detect_areas(xls)
boundaries = read_level_boundaries(xls)
if ids.empty:
    st.error("Nem található használható 'Azonosítók' munkalap.")
    st.stop()
if not areas:
    st.error("Nem sikerült felismerni a kompetenciaterületeket.")
    st.stop()

col1, col2, col3 = st.columns(3)
with col1:
    student_search = st.text_input("Tanuló keresése", placeholder="Kezdj el gépelni: név vagy mérési azonosító")
    labels = ids["label"].tolist()
    if student_search.strip():
        q = student_search.strip().lower()
        filtered_labels = [label for label in labels if q in label.lower()]
    else:
        filtered_labels = labels
    if not filtered_labels:
        st.warning("Nincs találat erre a keresésre.")
        st.stop()
    selected_label = st.selectbox("Tanuló", filtered_labels)
with col2:
    selected_area = st.selectbox("Kompetenciamérési terület", areas)
with col3:
    selected_metric = st.radio("Megjelenített mutató", ["Képességpont", "Képességszint"], horizontal=False)

student_row = ids[ids["label"] == selected_label].iloc[0]
student_id = student_row["id"]
student_name = student_row["name"]

data = extract_student_records(xls, student_id, selected_area)
if data.empty:
    st.warning("Ehhez a tanulóhoz és területhez nem találtam előzetes/végleges adatot a tanévi füleken.")
    st.stop()

data = data.sort_values(["Tanév", "Eredménytípus", "Mutató"])
area_boundaries = get_area_boundaries(boundaries, selected_area)

if selected_metric == "Képességpont":
    if area_boundaries.empty:
        st.info("Nem találtam ehhez a kompetenciaterülethez képességpont-határokat. Ha szeretnéd a szaggatott szintvonalakat, adj az Excelhez egy 'Szint_határok' munkalapot.")
    else:
        with st.expander("Képességpont-határok ehhez a területhez"):
            st.dataframe(area_boundaries[["Szint", "Alsó ponthatár"]], use_container_width=True, hide_index=True)

st.subheader("Diagram")
fig = make_chart(data, student_name, selected_area, selected_metric, boundaries)
st.pyplot(fig, use_container_width=True)
plt.close(fig)

with st.expander("Másik mutató diagramja"):
    other_metric = "Képességszint" if selected_metric == "Képességpont" else "Képességpont"
    if data[data["Mutató"] == other_metric]["Érték"].notna().any():
        fig2 = make_chart(data, student_name, selected_area, other_metric, boundaries)
        st.pyplot(fig2, use_container_width=True)
        plt.close(fig2)
    else:
        st.info("A másik mutatóhoz nincs megjeleníthető adat.")

st.subheader("PDF jelentések")
pdf_bytes = make_pdf(data, student_name, student_id, selected_area, selected_metric, boundaries)
file_safe = re.sub(r"[^0-9A-Za-z_áéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+", "_", f"{student_name}_{selected_area}_{selected_metric}")
st.download_button(
    "PDF letöltése - kiválasztott kompetenciaterület",
    data=pdf_bytes,
    file_name=f"{file_safe}.pdf",
    mime="application/pdf",
    type="primary",
)

all_pdf_bytes = make_pdf_all_areas(xls, areas, student_name, student_id, selected_metric, boundaries)
all_file_safe = re.sub(r"[^0-9A-Za-z_áéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+", "_", f"{student_name}_osszes_kompetenciaterulet_{selected_metric}")
st.download_button(
    "PDF letöltése - összes kompetenciaterület",
    data=all_pdf_bytes,
    file_name=f"{all_file_safe}.pdf",
    mime="application/pdf",
    type="secondary",
)

st.caption("Az alkalmazás legfeljebb 5 tanévi munkalapot jelenít meg a diagramon. A névlista az 'Azonosítók' munkalapról töltődik be. A PDF-ek csak diagramokat tartalmaznak, adattáblát nem.")
