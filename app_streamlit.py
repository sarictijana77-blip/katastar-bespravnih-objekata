import io
import contextlib
from pathlib import Path

import pandas as pd
import streamlit as st

# Sve funkcije za konekciju i CRUD logiku uvozimo direktno iz app_atributi.py,
# da ne bismo duplirale kod - Streamlit je samo "vizuelni sloj" oko iste logike.
from app_atributi import (
    DOZVOLJENI_STATUSI,
    napravi_engine,
    get_db_connection,
    prikazi_sve_detekcije,
    prikazi_jednu_detekciju,
    prikazi_inspektore,
    prikazi_statistiku,
    promeni_status,
    promeni_napomenu,
    dodeli_inspektora,
    obrisi_detekciju,
)

BASE_DIR = Path(__file__).resolve().parent
MAPA_ML = BASE_DIR / "outputs" / "maps" / "ml_mapa.html"
MAPA_GEO = BASE_DIR / "outputs" / "maps" / "geo_mapa.html"
FIGURES = BASE_DIR / "outputs" / "figures"


# ============================================================
# POMOĆNA FUNKCIJA - hvata print() poruke iz app_atributi.py
# funkcija i prikazuje ih kao Streamlit poruku, umesto da
# nestanu u terminalu.
# ============================================================

def pozovi_i_prikazi_poruku(funkcija, *args, uspeh=True, **kwargs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        funkcija(*args, **kwargs)
    poruka = buffer.getvalue().strip()
    if poruka:
        if uspeh:
            st.success(poruka)
        else:
            st.error(poruka)


# ============================================================
# PODEŠAVANJE STRANICE
# ============================================================

st.set_page_config(
    page_title="Katastar bespravnih objekata - Adica",
    page_icon="🏘️",
    layout="wide"
)

st.title("🏘️ Katastar bespravno izgrađenih objekata - Adice, Novi Sad")

stranica = st.sidebar.radio(
    "Navigacija",
    ["Pregled i statistika", "Mapa", "Izmena atributa"]
)


# ============================================================
# STRANICA 1 - PREGLED I STATISTIKA
# ============================================================

if stranica == "Pregled i statistika":
    st.header("Pregled ML detekcija")

    engine = napravi_engine()
    df = pd.read_sql_query(
        """
        SELECT detekcija_id, status_slucaja, procenjena_povrsina_m2,
               datum_detekcije, confidence, parcela_id, inspektor_id, napomena
        FROM detektovani_objekti_ml
        ORDER BY detekcija_id;
        """,
        engine
    )

    statusi_filter = st.multiselect(
        "Filtriraj po statusu",
        options=DOZVOLJENI_STATUSI,
        default=[]
    )

    df_prikaz = df if not statusi_filter else df[df["status_slucaja"].isin(statusi_filter)]

    col1, col2, col3 = st.columns(3)
    col1.metric("Ukupno detekcija", len(df))
    col2.metric("Kandidati za bespravne", (df["status_slucaja"] == "Kandidat - bespravni objekat").sum())
    col3.metric("Podudara se sa legalnim", (df["status_slucaja"] == "Podudara se sa legalnim objektom").sum())

    st.dataframe(df_prikaz, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Statistika po statusu")
    statistika = prikazi_statistiku()
    if statistika is not None and not statistika.empty:
        st.dataframe(statistika, use_container_width=True, hide_index=True)

        fig_col1, fig_col2 = st.columns(2)
        with fig_col1:
            st.bar_chart(statistika.set_index("status_slucaja")["broj"])
        with fig_col2:
            st.bar_chart(statistika.set_index("status_slucaja")["ukupna_povrsina_m2"])

    st.divider()
    st.subheader("Sačuvani grafikoni (iz geo_analiza.py i ml_detekcija.py)")

    slike = sorted(FIGURES.glob("*.png")) if FIGURES.exists() else []
    if slike:
        kolone = st.columns(3)
        for i, slika in enumerate(slike):
            with kolone[i % 3]:
                st.image(str(slika), caption=slika.stem, use_container_width=True)
    else:
        st.info("Nema sačuvanih grafikona u outputs/figures. Pokreni prvo geo_analiza.py i ml_detekcija.py.")


# ============================================================
# STRANICA 2 - MAPA
# ============================================================

elif stranica == "Mapa":
    st.header("Interaktivne mape")

    tab1, tab2 = st.tabs(["ML mapa (Deo 3)", "Geo mapa (Deo 2)"])

    with tab1:
        if MAPA_ML.exists():
            html_sadrzaj = MAPA_ML.read_text(encoding="utf-8")
            st.components.v1.html(html_sadrzaj, height=650, scrolling=True)
        else:
            st.warning(f"Mapa nije pronađena: {MAPA_ML}. Pokreni prvo ml_detekcija.py.")

    with tab2:
        if MAPA_GEO.exists():
            html_sadrzaj = MAPA_GEO.read_text(encoding="utf-8")
            st.components.v1.html(html_sadrzaj, height=650, scrolling=True)
        else:
            st.warning(f"Mapa nije pronađena: {MAPA_GEO}. Pokreni prvo geo_analiza.py.")


# ============================================================
# STRANICA 3 - IZMENA ATRIBUTA
# ============================================================

elif stranica == "Izmena atributa":
    st.header("Izmena atributa ML detekcija")

    engine = napravi_engine()
    df_ids = pd.read_sql_query(
        "SELECT detekcija_id, status_slucaja FROM detektovani_objekti_ml ORDER BY detekcija_id;",
        engine
    )

    if df_ids.empty:
        st.info("Nema detekcija u bazi.")
        st.stop()

    opcije = [f"{row.detekcija_id} - {row.status_slucaja}" for row in df_ids.itertuples()]
    izbor = st.selectbox("Izaberi detekciju", opcije)
    detekcija_id = int(izbor.split(" - ")[0])

    df_detalji = prikazi_jednu_detekciju(detekcija_id)
    if df_detalji is not None and not df_detalji.empty:
        red = df_detalji.iloc[0]

        st.subheader(f"Detekcija #{detekcija_id}")
        info_col1, info_col2, info_col3 = st.columns(3)
        info_col1.metric("Status", red.get("status_slucaja", "-"))
        info_col2.metric("Površina (m²)", red.get("procenjena_povrsina_m2", "-"))
        info_col3.metric("Confidence", red.get("confidence", "-"))

        st.caption(
            f"Parcela: {red.get('broj_parcele', '-')} | "
            f"Katastarska opština: {red.get('katastarska_opstina', '-')} | "
            f"Inspektor: {red.get('inspektor_ime', '-')} {red.get('inspektor_prezime', '')}"
        )

        st.divider()

        # --- Promena statusa ---
        st.subheader("Promeni status slučaja")
        novi_status = st.selectbox(
            "Novi status",
            DOZVOLJENI_STATUSI,
            index=DOZVOLJENI_STATUSI.index(red["status_slucaja"]) if red["status_slucaja"] in DOZVOLJENI_STATUSI else 0
        )
        if st.button("💾 Sačuvaj status"):
            pozovi_i_prikazi_poruku(promeni_status, detekcija_id, novi_status)
            st.rerun()

        st.divider()

        # --- Promena napomene ---
        st.subheader("Promeni napomenu")
        nova_napomena = st.text_area("Napomena", value=red.get("napomena") or "")
        if st.button("💾 Sačuvaj napomenu"):
            pozovi_i_prikazi_poruku(promeni_napomenu, detekcija_id, nova_napomena)
            st.rerun()

        st.divider()

        # --- Dodela inspektora ---
        st.subheader("Dodeli inspektora")
        inspektori_df = prikazi_inspektore()
        if inspektori_df is not None and not inspektori_df.empty:
            inspektor_opcije = [
                f"{row.inspektor_id} - {row.ime} {row.prezime} ({row.oblast_rada})"
                for row in inspektori_df.itertuples()
            ]
            izbor_inspektora = st.selectbox("Inspektor", inspektor_opcije)
            inspektor_id = int(izbor_inspektora.split(" - ")[0])

            if st.button("👤 Dodeli inspektora"):
                pozovi_i_prikazi_poruku(dodeli_inspektora, detekcija_id, inspektor_id)
                st.rerun()
        else:
            st.info("Nema inspektora u bazi.")

        st.divider()

        # --- Brisanje ---
        st.subheader("Obriši detekciju")
        st.warning("Ova akcija je trajna i ne može se poništiti.")
        potvrda = st.checkbox(f"Potvrđujem da želim da obrišem detekciju #{detekcija_id}")
        if st.button("🗑️ Obriši detekciju", disabled=not potvrda):
            pozovi_i_prikazi_poruku(obrisi_detekciju, detekcija_id, uspeh=False)
            st.rerun()