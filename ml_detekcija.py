from pathlib import Path

import cv2
import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import psycopg2
from shapely import wkt
from shapely.geometry import Polygon
from sklearn.cluster import KMeans
from sqlalchemy import create_engine


# ============================================================
# PODEŠAVANJA
# ============================================================

DB_HOST = "localhost"
DB_NAME = "katastar_db"
DB_USER = "postgres"
DB_PASSWORD = "admin"   # ako tvoja šifra nije admin, promeni ovde
DB_PORT = "5432"

CRS_WGS84 = "EPSG:4326"
CRS_METERS = "EPSG:32634"

BASE_DIR = Path(__file__).resolve().parent

IMAGE_PATH = BASE_DIR / "data" / "raw" / "raster" / "novi_sad.png"
AOI_PATH = BASE_DIR / "data" / "raw" / "raster" / "aoi.geojson"

DATA_PROCESSED = BASE_DIR / "data" / "processed"
OUTPUT_MAPS = BASE_DIR / "outputs" / "maps"
OUTPUT_TABLES = BASE_DIR / "outputs" / "tables"
OUTPUT_FIGURES = BASE_DIR / "outputs" / "figures"

DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
OUTPUT_MAPS.mkdir(parents=True, exist_ok=True)
OUTPUT_TABLES.mkdir(parents=True, exist_ok=True)
OUTPUT_FIGURES.mkdir(parents=True, exist_ok=True)

# Parametri koje po potrebi možemo fino podesiti
BROJ_KLASA_KMEANS = 10

# Podižemo prag da ne hvata sitan šum
MIN_POVRSINA_PIKSELA = 120

# Krovovi su uglavnom kompaktniji, ulice su dugačke i tanke
MAKS_ODNOS_STRANICA = 3.5

# Tražimo popunjenije oblike, da izbacimo tanke ivice i senke
MIN_POPUNJENOST_BOUNDING_BOXA = 0.35

# Da mapa ne bude pretrpana
MAKS_BROJ_DETEKCIJA = 300

# Ignorišemo detekcije koje dodiruju samu ivicu slike
MARGINA_IVICE_PX = 10


# ============================================================
# KONEKCIJA SA BAZOM
# ============================================================

def get_db_connection():
    try:
        return psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
    except Exception as e:
        print(f"Greška pri povezivanju na bazu: {e}")
        return None


def napravi_engine():
    url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)


def ucitaj_postgis_tabelu(engine, tabela):
    """
    Čita PostGIS tabelu preko WKT formata.
    Koristimo ovo jer je stabilnije na Windows-u nego direktno WKB čitanje.
    """
    sql = f"""
        SELECT
            *,
            ST_AsText(geometrija) AS wkt_geometry
        FROM {tabela}
        WHERE geometrija IS NOT NULL;
    """

    df = pd.read_sql_query(sql, engine)

    if df.empty:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

    if "geometrija" in df.columns:
        df = df.drop(columns=["geometrija"])

    df["geometry"] = df["wkt_geometry"].apply(wkt.loads)
    df = df.drop(columns=["wkt_geometry"])

    return gpd.GeoDataFrame(df, geometry="geometry", crs=CRS_WGS84)


# ============================================================
# UČITAVANJE SLIKE I AOI
# ============================================================

def ucitaj_sliku():
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(f"Ne postoji ulazna slika: {IMAGE_PATH}")

    slika_bgr = cv2.imread(str(IMAGE_PATH))

    if slika_bgr is None:
        raise ValueError(f"Slika ne može da se učita: {IMAGE_PATH}")

    print(f"Učitana slika: {IMAGE_PATH}")
    print(f"Dimenzije slike: {slika_bgr.shape[1]} x {slika_bgr.shape[0]} px")

    return slika_bgr


def ucitaj_aoi():
    if not AOI_PATH.exists():
        raise FileNotFoundError(f"Ne postoji AOI fajl: {AOI_PATH}")

    aoi = gpd.read_file(AOI_PATH)

    if aoi.empty:
        raise ValueError("AOI GeoJSON je prazan.")

    # Ako GeoJSON nema CRS, pokušavamo da zaključimo da li je WGS84 ili EPSG:32634.
    if aoi.crs is None:
        minx, miny, maxx, maxy = aoi.total_bounds

        if -180 <= minx <= 180 and -90 <= miny <= 90:
            aoi = aoi.set_crs(CRS_WGS84)
        else:
            aoi = aoi.set_crs(CRS_METERS)

    print(f"Učitan AOI: {AOI_PATH}")
    print(f"AOI CRS: {aoi.crs}")

    return aoi


# ============================================================
# ML SEGMENTACIJA SLIKE
# ============================================================


def napravi_masku_kmeans(slika_bgr):
    """
    Nenadgledani ML algoritam: KMeans segmentacija boja.

    Ovde ciljano izdvajamo klase koje liče na krovove:
    - crveni / narandžasti / braon krovovi
    - svetliji sivi/beli krovovi
    Izbacujemo vegetaciju, vodu, ulice i jako tamne senke.
    """
    print("Pokrećem KMeans segmentaciju slike...")

    slika_hsv = cv2.cvtColor(slika_bgr, cv2.COLOR_BGR2HSV)
    slika_lab = cv2.cvtColor(slika_bgr, cv2.COLOR_BGR2LAB)

    h, w = slika_bgr.shape[:2]

    lab = slika_lab.reshape(-1, 3).astype(np.float32)
    hsv = slika_hsv.reshape(-1, 3).astype(np.float32)

    karakteristike = np.column_stack([
        lab[:, 0],
        lab[:, 1],
        lab[:, 2],
        hsv[:, 0] * 0.7,
        hsv[:, 1],
        hsv[:, 2],
    ])

    broj_piksela = karakteristike.shape[0]
    velicina_uzorka = min(80000, broj_piksela)

    rng = np.random.default_rng(42)
    indeksi = rng.choice(broj_piksela, size=velicina_uzorka, replace=False)
    uzorak = karakteristike[indeksi]

    model = KMeans(
        n_clusters=BROJ_KLASA_KMEANS,
        random_state=42,
        n_init=10
    )

    model.fit(uzorak)
    klase = model.predict(karakteristike).reshape(h, w)

    maska = np.zeros((h, w), dtype=np.uint8)

    for klasa in range(BROJ_KLASA_KMEANS):
        pikseli = slika_hsv[klase == klasa]

        if len(pikseli) == 0:
            continue

        srednji_h = float(np.mean(pikseli[:, 0]))
        srednji_s = float(np.mean(pikseli[:, 1]))
        srednji_v = float(np.mean(pikseli[:, 2]))

        # Vegetacija je uglavnom zelena
        zeleno = 35 <= srednji_h <= 90 and srednji_s > 35

        # Voda/plavi tonovi
        plavo = 90 <= srednji_h <= 135 and srednji_s > 35

        # Asfalt/ulice su često sive i srednje svetle,
        # pa ih izbacujemo ako su skoro bez zasićenja i nisu baš svetli krovovi.
        asfalt_sivo = srednji_s < 35 and 70 <= srednji_v <= 190

        # Jako tamne senke
        senka = srednji_v < 45

        # Jako svetli UI/ivice/sjaj
        previse_svetlo = srednji_v > 245

        # Tipični crveni/narandžasti/braon krovovi
        crveni_krov = (
            (srednji_h <= 18 or srednji_h >= 165)
            and srednji_s > 40
            and 55 <= srednji_v <= 235
        )

        narandzasti_braon_krov = (
            8 <= srednji_h <= 32
            and srednji_s > 35
            and 50 <= srednji_v <= 230
        )

        # Svetli beli/sivi krovovi: slabija zasićenost, ali dosta svetli
        svetli_krov = (
            srednji_s <= 45
            and 185 <= srednji_v <= 245
        )

        kandidat = (
            (crveni_krov or narandzasti_braon_krov or svetli_krov)
            and not zeleno
            and not plavo
            and not asfalt_sivo
            and not senka
            and not previse_svetlo
        )

        print(
            f"Klasa {klasa}: H={srednji_h:.1f}, S={srednji_s:.1f}, V={srednji_v:.1f}, "
            f"kandidat={kandidat}"
        )

        if kandidat:
            maska[klase == klasa] = 255

    # Čišćenje maske
    kernel_mali = np.ones((3, 3), np.uint8)

    # Manje spajamo objekte nego ranije, da se ne povezuju cele ulice/blokovi
    maska = cv2.morphologyEx(maska, cv2.MORPH_OPEN, kernel_mali)

    putanja_maske = OUTPUT_FIGURES / "ml_maska_detekcije.png"
    cv2.imwrite(str(putanja_maske), maska)

    print(f"Maska detekcije sačuvana: {putanja_maske}")

    return maska


# ============================================================
# KONTURE U POLIGONE
# ============================================================

def piksel_u_koordinate(col, row, width, height, bounds):
    """
    Pretvara piksel koordinate u prostorne koordinate.
    Pretpostavka: slika pokriva bounding box AOI poligona.
    """
    minx, miny, maxx, maxy = bounds

    x = minx + (col / width) * (maxx - minx)
    y = maxy - (row / height) * (maxy - miny)

    return x, y


def konture_u_geometrije(maska, aoi, slika_bgr):
    """
    Pretvara detektovane konture iz piksela u vektorske poligone.
    """
    print("Pretvaram detektovane konture u poligone...")

    h, w = maska.shape[:2]

    aoi_crs = aoi.crs
    bounds = aoi.total_bounds

    konture, _ = cv2.findContours(
        maska,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    zapisi = []
    nacrtana = slika_bgr.copy()

    for kontura in konture:
        povrsina_px = cv2.contourArea(kontura)

        if povrsina_px < MIN_POVRSINA_PIKSELA:
            continue

        x, y, bw, bh = cv2.boundingRect(kontura)

        if bw == 0 or bh == 0:
            continue
        # Preskačemo konture koje dodiruju ivicu slike,
        # jer su to često rubovi screenshot-a ili isečeni objekti.
        if (
            x <= MARGINA_IVICE_PX
            or y <= MARGINA_IVICE_PX
            or x + bw >= w - MARGINA_IVICE_PX
            or y + bh >= h - MARGINA_IVICE_PX
        ):
            continue
        odnos_stranica = max(bw / bh, bh / bw)
        popunjenost = povrsina_px / float(bw * bh)

        # Izbacujemo jako dugačke oblike, jer su to često ulice, senke ili linije.
        if odnos_stranica > MAKS_ODNOS_STRANICA:
            continue

        # Izbacujemo tanke/nepopunjene oblike.
        if popunjenost < MIN_POPUNJENOST_BOUNDING_BOXA:
            continue

        epsilon = 0.01 * cv2.arcLength(kontura, True)
        aproks = cv2.approxPolyDP(kontura, epsilon, True)

        if len(aproks) < 4:
            continue

        koordinate = []

        for tacka in aproks:
            col = float(tacka[0][0])
            row = float(tacka[0][1])
            px, py = piksel_u_koordinate(col, row, w, h, bounds)
            koordinate.append((px, py))

        if len(koordinate) < 4:
            continue

        poligon = Polygon(koordinate)

        if not poligon.is_valid:
            poligon = poligon.buffer(0)

        if poligon.is_empty or poligon.geom_type != "Polygon":
            continue

        zapisi.append({
            "status_slucaja": "Detektovano ML",
            "confidence": round(min(0.95, 0.45 + popunjenost), 3),
            "izvor_snimka": "GeoSrbija ortofoto snimak",
            "model": "KMeans segmentacija slike",
            "napomena": "Automatski detektovan kandidat za objekat/krov sa ortofoto snimka",
            "povrsina_px": round(float(povrsina_px), 2),
            "odnos_stranica": round(float(odnos_stranica), 2),
            "popunjenost": round(float(popunjenost), 2),
            "geometry": poligon
        })

        cv2.drawContours(nacrtana, [kontura], -1, (0, 0, 255), 2)
        cv2.rectangle(nacrtana, (x, y), (x + bw, y + bh), (0, 0, 255), 1)

    if not zapisi:
        print("Nije pronađena nijedna detekcija. Kasnije ćemo podesiti parametre ako treba.")
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=aoi_crs)

    gdf = gpd.GeoDataFrame(zapisi, geometry="geometry", crs=aoi_crs)

    # Previše detekcija može da uspori mapu, zato ograničavamo broj.
    if len(gdf) > MAKS_BROJ_DETEKCIJA:
        gdf = gdf.sort_values("povrsina_px", ascending=False).head(MAKS_BROJ_DETEKCIJA).copy()

    # Površina se računa u metrima.
    gdf_m = gdf.to_crs(CRS_METERS)
    gdf["procenjena_povrsina_m2"] = gdf_m.geometry.area.round(2)

    # Čuvamo za PostGIS u WGS84.
    gdf = gdf.to_crs(CRS_WGS84)

    putanja_obelezeno = OUTPUT_FIGURES / "ml_obelezeni_objekti.png"
    cv2.imwrite(str(putanja_obelezeno), nacrtana)

    print(f"Obeležena slika sačuvana: {putanja_obelezeno}")
    print(f"Broj detektovanih kandidata: {len(gdf)}")

    return gdf


# ============================================================
# POSTGIS TABELA I UPIS
# ============================================================

def kreiraj_tabelu_ml():
    conn = get_db_connection()

    if conn is None:
        return

    cur = conn.cursor()

    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS detektovani_objekti_ml (
                detekcija_id SERIAL PRIMARY KEY,
                status_slucaja VARCHAR(50) DEFAULT 'Detektovano ML',
                procenjena_povrsina_m2 NUMERIC(10, 2),
                datum_detekcije DATE DEFAULT CURRENT_DATE,
                confidence NUMERIC(5, 3),
                izvor_snimka VARCHAR(150),
                model VARCHAR(100),
                napomena TEXT,
                parcela_id INT REFERENCES parcele(parcela_id) ON DELETE SET NULL,
                inspektor_id INT REFERENCES inspektori(inspektor_id) ON DELETE SET NULL,
                geometrija GEOMETRY(Polygon, 4326)
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_detektovani_objekti_ml_geom
            ON detektovani_objekti_ml
            USING GIST (geometrija);
        """)

        conn.commit()
        print("Tabela detektovani_objekti_ml je spremna.")

    except Exception as e:
        conn.rollback()
        print(f"Greška pri kreiranju ML tabele: {e}")

    finally:
        cur.close()
        conn.close()


def dodeli_inspektora(engine):
    try:
        df = pd.read_sql_query(
            "SELECT inspektor_id FROM inspektori ORDER BY inspektor_id LIMIT 1;",
            engine
        )

        if df.empty:
            return None

        return int(df.iloc[0]["inspektor_id"])

    except Exception:
        return None


def dodeli_parcele(detekcije, parcele, engine):
    detekcije = detekcije.copy()
    detekcije["parcela_id"] = None
    detekcije["broj_parcele"] = None
    detekcije["katastarska_opstina"] = None

    if not parcele.empty and not detekcije.empty:
        spoj = gpd.sjoin(
            detekcije,
            parcele[["parcela_id", "broj_parcele", "katastarska_opstina", "geometry"]],
            how="left",
            predicate="intersects"
        )

        spoj = spoj[~spoj.index.duplicated(keep="first")]

        for idx, red in spoj.iterrows():
            if "parcela_id_right" in spoj.columns and pd.notna(red.get("parcela_id_right")):
                detekcije.loc[idx, "parcela_id"] = int(red["parcela_id_right"])

            if "broj_parcele_right" in spoj.columns and pd.notna(red.get("broj_parcele_right")):
                detekcije.loc[idx, "broj_parcele"] = red["broj_parcele_right"]

            if "katastarska_opstina_right" in spoj.columns and pd.notna(red.get("katastarska_opstina_right")):
                detekcije.loc[idx, "katastarska_opstina"] = red["katastarska_opstina_right"]

    detekcije["inspektor_id"] = dodeli_inspektora(engine)

    return detekcije


def upisi_u_postgis(detekcije):
    conn = get_db_connection()

    if conn is None:
        return

    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM detektovani_objekti_ml;")

        for _, red in detekcije.iterrows():
            parcela_id = red.get("parcela_id")
            inspektor_id = red.get("inspektor_id")

            if pd.isna(parcela_id):
                parcela_id = None

            if pd.isna(inspektor_id):
                inspektor_id = None

            cur.execute("""
                INSERT INTO detektovani_objekti_ml (
                    status_slucaja,
                    procenjena_povrsina_m2,
                    confidence,
                    izvor_snimka,
                    model,
                    napomena,
                    parcela_id,
                    inspektor_id,
                    geometrija
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    ST_GeomFromText(%s, 4326)
                );
            """, (
                red["status_slucaja"],
                float(red["procenjena_povrsina_m2"]),
                float(red["confidence"]),
                red["izvor_snimka"],
                red["model"],
                red["napomena"],
                parcela_id,
                inspektor_id,
                red.geometry.wkt
            ))

        conn.commit()
        print(f"Upisano {len(detekcije)} detekcija u PostGIS tabelu detektovani_objekti_ml.")

    except Exception as e:
        conn.rollback()
        print(f"Greška pri upisu u PostGIS: {e}")

    finally:
        cur.close()
        conn.close()


# ============================================================
# ČUVANJE REZULTATA
# ============================================================

def pripremi_za_geojson(gdf):
    gdf = gdf.copy()

    for kolona in gdf.columns:
        if kolona != "geometry":
            gdf[kolona] = gdf[kolona].astype(str)

    return gdf


def sacuvaj_rezultate(detekcije):
    if detekcije.empty:
        print("Nema detekcija za čuvanje.")
        return

    geojson_path = DATA_PROCESSED / "detektovani_objekti_ml.geojson"
    csv_path = OUTPUT_TABLES / "detektovani_objekti_ml.csv"

    pripremi_za_geojson(detekcije).to_file(geojson_path, driver="GeoJSON")

    tabela = pd.DataFrame(detekcije.drop(columns="geometry"))
    tabela.to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"GeoJSON sačuvan: {geojson_path}")
    print(f"CSV tabela sačuvana: {csv_path}")


# ============================================================
# PROSTORNE ANALIZE
# ============================================================

def prostorne_analize(detekcije, parcele, legalni, bespravni, aoi):
    rezultati = {}

    if detekcije.empty:
        return rezultati

    # 1. Detekcije koje se seku sa parcelama
    if not parcele.empty:
        rezultati["ml_spoj_sa_parcelama"] = gpd.sjoin(
            detekcije,
            parcele[["parcela_id", "broj_parcele", "katastarska_opstina", "geometry"]],
            how="left",
            predicate="intersects"
        )

    # 2. Detekcije koje se seku sa legalnim objektima
    if not legalni.empty:
        rezultati["ml_presek_sa_legalnim_objektima"] = gpd.sjoin(
            detekcije,
            legalni[["objekat_id", "broj_dozvole", "namjena_objekta", "geometry"]],
            how="inner",
            predicate="intersects"
        )

    # 3. Detekcije u blizini ranije evidentiranih bespravnih objekata
    if not bespravni.empty:
        bespravni_m = bespravni.to_crs(CRS_METERS)
        buffer_m = bespravni_m.copy()
        buffer_m["geometry"] = buffer_m.geometry.buffer(100)
        buffer_100m = buffer_m.to_crs(CRS_WGS84)

        rezultati["buffer_bespravni_100m"] = buffer_100m

        rezultati["ml_u_bufferu_bespravnih_100m"] = gpd.sjoin(
            detekcije,
            buffer_100m[["bespravni_id", "status_slucaja", "geometry"]],
            how="inner",
            predicate="intersects"
        )

    # 4. Buffer oko ML detekcija
    detekcije_m = detekcije.to_crs(CRS_METERS)
    buffer_ml = detekcije_m.copy()
    buffer_ml["geometry"] = buffer_ml.geometry.buffer(25)
    rezultati["buffer_ml_25m"] = buffer_ml.to_crs(CRS_WGS84)

    # 5. Detekcije unutar AOI
    aoi_wgs = aoi.to_crs(CRS_WGS84)
    rezultati["ml_unutar_aoi"] = gpd.sjoin(
        detekcije,
        aoi_wgs[["geometry"]],
        how="inner",
        predicate="within"
    )

    for naziv, gdf in rezultati.items():
        if gdf.empty:
            continue

        geojson_path = DATA_PROCESSED / f"{naziv}.geojson"
        csv_path = OUTPUT_TABLES / f"{naziv}.csv"

        pripremi_za_geojson(gdf).to_file(geojson_path, driver="GeoJSON")
        pd.DataFrame(gdf.drop(columns="geometry", errors="ignore")).to_csv(
            csv_path,
            index=False,
            encoding="utf-8-sig"
        )

        print(f"Sačuvana prostorna analiza: {naziv}")

    return rezultati


# ============================================================
# MAPA
# ============================================================

def dodaj_sloj(mapa, gdf, naziv, boja, show=True, fill=True):
    if gdf is None or gdf.empty:
        return

    gdf_map = pripremi_za_geojson(gdf.to_crs(CRS_WGS84))

    tooltip_kolone = [c for c in gdf_map.columns if c != "geometry"][:6]

    folium.GeoJson(
        gdf_map,
        name=naziv,
        show=show,
        style_function=lambda feature, boja=boja, fill=fill: {
            "color": boja,
            "weight": 2,
            "fillColor": boja,
            "fillOpacity": 0.35 if fill else 0.0,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_kolone,
            aliases=tooltip_kolone,
            sticky=True
        ) if tooltip_kolone else None
    ).add_to(mapa)


def napravi_mapu(detekcije, aoi, parcele, legalni, bespravni, rezultati):
    aoi_wgs = aoi.to_crs(CRS_WGS84)
    centar = aoi_wgs.geometry.union_all().centroid

    mapa = folium.Map(
        location=[centar.y, centar.x],
        zoom_start=17,
        tiles="OpenStreetMap"
    )

    folium.TileLayer("CartoDB positron", name="Svetla raster podloga").add_to(mapa)
    folium.TileLayer("CartoDB dark_matter", name="Tamna raster podloga").add_to(mapa)
    folium.TileLayer(
        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr="OpenStreetMap",
        name="OpenStreetMap podloga"
    ).add_to(mapa)

    dodaj_sloj(mapa, aoi_wgs, "AOI - obuhvat snimka", "blue", show=True, fill=False)
    dodaj_sloj(mapa, detekcije, "ML detektovani objekti", "red", show=True, fill=True)

    dodaj_sloj(mapa, parcele, "Parcele iz baze", "purple", show=False, fill=True)
    dodaj_sloj(mapa, legalni, "Legalni objekti iz baze", "green", show=False, fill=True)
    dodaj_sloj(mapa, bespravni, "Bespravni objekti iz baze", "orange", show=False, fill=True)

    dodaj_sloj(mapa, rezultati.get("buffer_ml_25m"), "Buffer 25m oko ML detekcija", "black", show=False, fill=False)
    dodaj_sloj(mapa, rezultati.get("buffer_bespravni_100m"), "Buffer 100m oko bespravnih objekata", "pink", show=False, fill=True)
    dodaj_sloj(mapa, rezultati.get("ml_presek_sa_legalnim_objektima"), "ML detekcije koje se seku sa legalnim", "green", show=False, fill=True)

    folium.LayerControl(collapsed=False).add_to(mapa)

    mapa_path = OUTPUT_MAPS / "ml_mapa.html"
    mapa.save(mapa_path)

    print(f"ML mapa sačuvana: {mapa_path}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("DEO 3 - PYTHON ML DETEKCIJA OBJEKATA")
    print("=" * 70)

    engine = napravi_engine()

    print("Učitavam podatke iz baze...")
    parcele = ucitaj_postgis_tabelu(engine, "parcele")
    legalni = ucitaj_postgis_tabelu(engine, "legalni_objekti")
    bespravni = ucitaj_postgis_tabelu(engine, "bespravni_objekti")

    print(f"Parcele iz baze: {len(parcele)}")
    print(f"Legalni objekti iz baze: {len(legalni)}")
    print(f"Bespravni objekti iz baze: {len(bespravni)}")

    slika_bgr = ucitaj_sliku()
    aoi = ucitaj_aoi()

    kreiraj_tabelu_ml()

    maska = napravi_masku_kmeans(slika_bgr)
    detekcije = konture_u_geometrije(maska, aoi, slika_bgr)

    if detekcije.empty:
        print("Nema detekcija. Probaj da približiš snimak ili ćemo podesiti parametre segmentacije.")
        return

    detekcije = dodeli_parcele(detekcije, parcele, engine)

    sacuvaj_rezultate(detekcije)
    upisi_u_postgis(detekcije)

    rezultati = prostorne_analize(
        detekcije=detekcije,
        parcele=parcele,
        legalni=legalni,
        bespravni=bespravni,
        aoi=aoi
    )

    napravi_mapu(
        detekcije=detekcije,
        aoi=aoi,
        parcele=parcele,
        legalni=legalni,
        bespravni=bespravni,
        rezultati=rezultati
    )

    print("=" * 70)
    print("ML DETEKCIJA ZAVRŠENA")
    print("=" * 70)


if __name__ == "__main__":
    main()