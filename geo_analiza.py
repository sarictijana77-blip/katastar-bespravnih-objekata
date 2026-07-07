import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import geopandas as gpd
import folium
import osmnx as ox
from sqlalchemy import create_engine
from shapely import wkt

# ============================================================
# PODESAVANJA
# ============================================================

DB_HOST = "localhost"
DB_NAME = "katastar_db"
DB_USER = "postgres"
DB_PASSWORD = "admin"   # ako tvoja sifra nije admin, promeni ovde
DB_PORT = "5432"

PLACE_NAME = "Novi Sad, Serbia"

CRS_WGS84 = "EPSG:4326"
CRS_METERS = "EPSG:32634"  # UTM zona za Srbiju, koristi se za povrsine i buffer u metrima

BASE_DIR = Path(__file__).resolve().parent
DATA_PROCESSED = BASE_DIR / "data" / "processed"
OUTPUT_MAPS = BASE_DIR / "outputs" / "maps"
OUTPUT_TABLES = BASE_DIR / "outputs" / "tables"

DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
OUTPUT_MAPS.mkdir(parents=True, exist_ok=True)
OUTPUT_TABLES.mkdir(parents=True, exist_ok=True)

# Da mapa ne bude ogromna i da se ne koci u browseru
MAX_FEATURES_ON_MAP = 1500


# ============================================================
# KONEKCIJA SA BAZOM
# ============================================================

def napravi_engine():
    url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)


def ucitaj_postgis_tabelu(engine, tabela, id_kolona):
    """
    Ucitava PostGIS tabelu kao GeoDataFrame.
    Geometriju citamo kao WKT tekst, pa je pretvaramo u shapely geometriju.
    Ovo je stabilnije na Windows-u nego direktno citanje EWKB formata.
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
        print(f"Tabela {tabela} je prazna.")
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

    # Originalna PostGIS kolona nam vise ne treba,
    # jer cemo aktivnu geometriju napraviti iz WKT kolone.
    if "geometrija" in df.columns:
        df = df.drop(columns=["geometrija"])

    # WKT tekst -> shapely geometry
    df["geometry"] = df["wkt_geometry"].apply(wkt.loads)
    df = df.drop(columns=["wkt_geometry"])

    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=CRS_WGS84)

    # Cuvamo i tabelarni CSV bez geometry kolone
    df_tabela = pd.DataFrame(gdf.drop(columns="geometry"))
    df_tabela.to_csv(
        OUTPUT_TABLES / f"{tabela}.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print(f"Ucitana tabela iz baze: {tabela} ({len(gdf)} redova)")
    return gdf


# ============================================================
# OSM PODACI
# ============================================================

def osm_features_from_place(place_name, tags):
    """
    Kompatibilno sa novijim i starijim verzijama OSMnx-a.
    """
    if hasattr(ox, "features_from_place"):
        return ox.features_from_place(place_name, tags)

    return ox.features.features_from_place(place_name, tags)


def ucitaj_osm_sloj(naziv, tags, dozvoljeni_tipovi=None):
    """
    Preuzima OSM sloj za Novi Sad i vraca GeoDataFrame.
    """
    print(f"Preuzimam OSM sloj: {naziv}...")

    try:
        gdf = osm_features_from_place(PLACE_NAME, tags)
        gdf = gdf.reset_index()

        if gdf.crs is None:
            gdf = gdf.set_crs(CRS_WGS84)

        gdf = gdf.to_crs(CRS_WGS84)

        if dozvoljeni_tipovi is not None:
            gdf = gdf[gdf.geometry.geom_type.isin(dozvoljeni_tipovi)].copy()

        gdf = sredi_geometrije(gdf)

        print(f"OSM sloj '{naziv}' preuzet: {len(gdf)} objekata")
        return gdf

    except Exception as e:
        print(f"Neuspesno preuzimanje sloja '{naziv}': {e}")
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)


def sredi_geometrije(gdf):
    """
    Uklanja prazne i nevalidne geometrije.
    """
    if gdf.empty:
        return gdf

    gdf = gdf[gdf.geometry.notnull()].copy()
    gdf = gdf[~gdf.geometry.is_empty].copy()

    try:
        gdf["geometry"] = gdf.geometry.make_valid()
    except Exception:
        # fallback ako verzija biblioteka ne podrzava make_valid
        gdf["geometry"] = gdf.geometry.buffer(0)

    return gdf


def pripremi_za_geojson(gdf):
    """
    GeoJSON nekad ne voli liste/dict vrednosti u kolonama,
    zato sve ne-geometrijske kolone pretvaramo u string.
    """
    if gdf.empty:
        return gdf

    gdf = gdf.copy()

    for col in gdf.columns:
        if col != "geometry":
            gdf[col] = gdf[col].astype(str)

    return gdf


def sacuvaj_geojson(gdf, naziv_fajla):
    """
    Cuva GeoDataFrame kao GeoJSON.
    """
    if gdf.empty:
        print(f"Preskacem cuvanje {naziv_fajla}, sloj je prazan.")
        return

    putanja = DATA_PROCESSED / naziv_fajla
    gdf_out = pripremi_za_geojson(gdf.to_crs(CRS_WGS84))
    gdf_out.to_file(putanja, driver="GeoJSON")
    print(f"Sacuvano: {putanja}")


# ============================================================
# GEO ANALIZE
# ============================================================

def izracunaj_povrsinu(gdf, naziv_kolone="povrsina_m2"):
    """
    Povrsina se racuna u projektovanom CRS-u, ne u EPSG:4326.
    """
    if gdf.empty:
        return gdf

    gdf_m = gdf.to_crs(CRS_METERS)
    gdf = gdf.copy()
    gdf[naziv_kolone] = gdf_m.geometry.area.round(2)

    return gdf

def napravi_clip_zgrada(buildings, parcele):
    """
    PRAVI clip: iseca OSM zgrade na oblast definisanu granicama parcela
    iz baze (Deo 1 tabela), sa baferom od 200m da uhvatimo i okolinu.
    """
    if buildings.empty or parcele.empty:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

    parcele_m = parcele.to_crs(CRS_METERS)
    granica_m = parcele_m.geometry.union_all().buffer(200)
    granica = gpd.GeoDataFrame(geometry=[granica_m], crs=CRS_METERS).to_crs(CRS_WGS84)

    try:
        return gpd.clip(buildings, granica)
    except Exception as e:
        print(f"Clip analiza nije uspela: {e}")
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

def napravi_geo_analize(buildings, roads, water, landuse, parcele, bespravni):
    """
    Pravi nekoliko osnovnih prostornih analiza.
    Ovo su primeri za Deo 2:
    1. clip
    2. buffer
    3. spatial join / intersects
    4. intersection
    5. within
    """

    rezultati = {}

    # 1) CLIP - pravi isečak OSM zgrada po granici parcela iz baze
    rezultati["clip_zgrade_oko_parcela"] = napravi_clip_zgrada(buildings, parcele)

    # 2) BUFFER - zona 50 m oko puteva
    if not roads.empty:
        roads_m = roads.to_crs(CRS_METERS)
        buffer_putevi_m = roads_m.copy()
        buffer_putevi_m["geometry"] = roads_m.geometry.buffer(50)
        buffer_putevi_m = buffer_putevi_m.dissolve()
        buffer_putevi = buffer_putevi_m.to_crs(CRS_WGS84)
        rezultati["buffer_50m_oko_puteva"] = buffer_putevi
    else:
        rezultati["buffer_50m_oko_puteva"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

    # 3) SPATIAL JOIN / INTERSECTS - zgrade koje dodiruju ili seku neku namenu zemljista
    if not buildings.empty and not landuse.empty:
        landuse_simple = landuse[["geometry"] + [c for c in ["landuse", "name"] if c in landuse.columns]].copy()
        zgrade_landuse = gpd.sjoin(
            buildings,
            landuse_simple,
            how="left",
            predicate="intersects"
        )
        rezultati["zgrade_spojene_sa_namenom_zemljista"] = zgrade_landuse
    else:
        rezultati["zgrade_spojene_sa_namenom_zemljista"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

    # 4) INTERSECTION - zgrade na poljoprivrednom zemljistu
    if not buildings.empty and not landuse.empty and "landuse" in landuse.columns:
        poljoprivredno = landuse[
            landuse["landuse"].astype(str).isin(["farmland", "farmyard", "orchard", "vineyard", "meadow"])
        ].copy()

        if not poljoprivredno.empty:
            try:
                zgrade_na_poljoprivrednom = gpd.overlay(
                    buildings,
                    poljoprivredno[["landuse", "geometry"]],
                    how="intersection"
                )
                rezultati["intersection_zgrade_poljoprivredno"] = zgrade_na_poljoprivrednom
            except Exception as e:
                print(f"Intersection analiza nije uspela: {e}")
                rezultati["intersection_zgrade_poljoprivredno"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)
        else:
            rezultati["intersection_zgrade_poljoprivredno"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)
    else:
        rezultati["intersection_zgrade_poljoprivredno"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

    # 5) WITHIN - bespravni objekti iz baze koji su unutar parcela iz baze
    if not bespravni.empty and not parcele.empty:
        try:
            bespravni_u_parcelama = gpd.sjoin(
                bespravni,
                parcele[["parcela_id", "broj_parcele", "katastarska_opstina", "geometry"]],
                how="left",
                predicate="within"
            )
            rezultati["within_bespravni_unutar_parcela"] = bespravni_u_parcelama
        except Exception as e:
            print(f"Within analiza nije uspela: {e}")
            rezultati["within_bespravni_unutar_parcela"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)
    else:
        rezultati["within_bespravni_unutar_parcela"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

    # 6) DODATNI PROSTORNI UPIT - zgrade blizu puteva, unutar buffer zone
    if not buildings.empty and not rezultati["buffer_50m_oko_puteva"].empty:
        try:
            zgrade_blizu_puteva = gpd.sjoin(
                buildings,
                rezultati["buffer_50m_oko_puteva"][["geometry"]],
                how="inner",
                predicate="intersects"
            )
            rezultati["zgrade_u_bufferu_puteva"] = zgrade_blizu_puteva
        except Exception as e:
            print(f"Analiza zgrada u bufferu puteva nije uspela: {e}")
            rezultati["zgrade_u_bufferu_puteva"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)
    else:
        rezultati["zgrade_u_bufferu_puteva"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

    # 7) SPAJANJE SHAPEFILE (OSM) PODATAKA SA TABELOM IZ DELA 1
        # OSM zgrade spojene sa parcelama IZ BAZE - direktno spajanje shp+baza
    if not buildings.empty and not parcele.empty:
        try:
            rezultati["osm_zgrade_spojene_sa_parcelama_baze"] = gpd.sjoin(
                buildings,
                parcele[["parcela_id", "broj_parcele", "katastarska_opstina", "namjena", "geometry"]],
                how="inner",
                predicate="intersects"
            )
        except Exception as e:
            print(f"Spajanje OSM zgrada sa parcelama iz baze nije uspelo: {e}")
            rezultati["osm_zgrade_spojene_sa_parcelama_baze"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)
    else:
        rezultati["osm_zgrade_spojene_sa_parcelama_baze"] = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

    return rezultati

# ============================================================
# GRAFIKONI (STATIČNI, ZA IZVEŠTAJ)
# ============================================================

def napravi_grafikone(rezultati, bespravni_sa_opstinom):
    """
    Pravi dva bar grafikona i cuva ih kao PNG u outputs/figures.
    """
    figures_dir = BASE_DIR / "outputs" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # 1) Zgrade po nameni zemljišta
    zgrade_namena = rezultati.get("zgrade_spojene_sa_namenom_zemljista")

    # Napomena: i OSM zgrade i OSM landuse sloj imaju kolonu "landuse",
    # pa sjoin automatski preimenuje u "landuse_left"/"landuse_right".
    # Nas zanima "landuse_right" (dolazi iz landuse sloja, ne iz zgrada).
    kolona_namene = None
    if zgrade_namena is not None and not zgrade_namena.empty:
        if "landuse_right" in zgrade_namena.columns:
            kolona_namene = "landuse_right"
        elif "landuse" in zgrade_namena.columns:
            kolona_namene = "landuse"

    if kolona_namene is not None:
        brojac = zgrade_namena[kolona_namene].fillna("nepoznato").value_counts()

        plt.figure(figsize=(9, 5))
        brojac.plot(kind="bar", color="steelblue")
        plt.title("Broj OSM zgrada po nameni zemljišta")
        plt.xlabel("Namena zemljišta")
        plt.ylabel("Broj zgrada")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        putanja = figures_dir / "zgrade_po_nameni_zemljista.png"
        plt.savefig(putanja, dpi=150)
        plt.close()
        print(f"Grafikon sačuvan: {putanja}")

    # 2) Bespravni objekti po katastarskoj opštini
    if bespravni_sa_opstinom is not None and not bespravni_sa_opstinom.empty and "katastarska_opstina" in bespravni_sa_opstinom.columns:
        brojac2 = bespravni_sa_opstinom["katastarska_opstina"].fillna("nepoznato").value_counts()

        plt.figure(figsize=(9, 5))
        brojac2.plot(kind="bar", color="indianred")
        plt.title("Broj bespravnih objekata po katastarskoj opštini")
        plt.xlabel("Katastarska opština")
        plt.ylabel("Broj bespravnih objekata")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        putanja2 = figures_dir / "bespravni_po_opstini.png"
        plt.savefig(putanja2, dpi=150)
        plt.close()
        print(f"Grafikon sačuvan: {putanja2}")

# ============================================================
# MAPA
# ============================================================

def skrati_za_mapu(gdf, max_features=MAX_FEATURES_ON_MAP):
    """
    Folium mapa moze da se ukoci ako ubacimo previse objekata.
    Zato za prikaz uzimamo prvih max_features, a puni fajl cuvamo kao GeoJSON.
    """
    if gdf.empty:
        return gdf

    if len(gdf) > max_features:
        return gdf.head(max_features).copy()

    return gdf


def dodaj_geojson_sloj(mapa, gdf, naziv, boja, fill=True, show=True):
    """
    Dodaje GeoJSON sloj na Folium mapu.
    """
    if gdf is None or gdf.empty:
        return

    gdf_map = skrati_za_mapu(gdf).to_crs(CRS_WGS84)
    gdf_map = pripremi_za_geojson(gdf_map)

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
            fields=[c for c in gdf_map.columns if c != "geometry"][:5],
            aliases=[c for c in gdf_map.columns if c != "geometry"][:5],
            sticky=True
        ) if len([c for c in gdf_map.columns if c != "geometry"]) > 0 else None
    ).add_to(mapa)


def napravi_mapu(parcele, legalni, bespravni, buildings, roads, water, landuse, rezultati, ml_detekcije):
    """
    Pravi interaktivnu HTML mapu sa slojevima.
    """

    # Centar Novog Sada
    mapa = folium.Map(
        location=[45.2671, 19.8335],
        zoom_start=12,
        tiles="OpenStreetMap"
    )

    # Raster / tile podloge
    folium.TileLayer("CartoDB positron", name="Raster podloga - svetla").add_to(mapa)
    folium.TileLayer("CartoDB dark_matter", name="Raster podloga - tamna").add_to(mapa)

    # Slojevi iz baze
    dodaj_geojson_sloj(mapa, parcele, "Parcele iz PostGIS baze", "blue", fill=True, show=True)
    dodaj_geojson_sloj(mapa, legalni, "Legalni objekti iz baze", "green", fill=True, show=True)
    dodaj_geojson_sloj(mapa, bespravni, "Bespravni objekti iz baze", "red", fill=True, show=True)

    # ML detekcije (Deo 3) - razdvojene po statusu klasifikacije
    if not ml_detekcije.empty and "status_slucaja" in ml_detekcije.columns:
        ml_bespravni = ml_detekcije[ml_detekcije["status_slucaja"] == "Kandidat - bespravni objekat"]
        ml_legalno = ml_detekcije[ml_detekcije["status_slucaja"] == "Podudara se sa legalnim objektom"]
    else:
        ml_bespravni = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)
        ml_legalno = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_WGS84)

    dodaj_geojson_sloj(mapa, ml_bespravni, "ML: kandidati za bespravne objekte", "crimson", fill=True, show=True)
    dodaj_geojson_sloj(mapa, ml_legalno, "ML: podudara se sa legalnim", "limegreen", fill=True, show=False)
    
    # OSM slojevi
    dodaj_geojson_sloj(mapa, buildings, "OSM zgrade", "gray", fill=True, show=False)
    dodaj_geojson_sloj(mapa, roads, "OSM putevi", "black", fill=False, show=False)
    dodaj_geojson_sloj(mapa, water, "OSM voda", "cyan", fill=True, show=False)
    dodaj_geojson_sloj(mapa, landuse, "OSM namena zemljista", "orange", fill=True, show=False)

    # Rezultati analiza
    dodaj_geojson_sloj(
        mapa,
        rezultati.get("buffer_50m_oko_puteva"),
        "Buffer 50m oko puteva",
        "purple",
        fill=True,
        show=False
    )

    dodaj_geojson_sloj(
        mapa,
        rezultati.get("intersection_zgrade_poljoprivredno"),
        "Zgrade na poljoprivrednom zemljistu",
        "red",
        fill=True,
        show=True
    )

    dodaj_geojson_sloj(
        mapa,
        rezultati.get("zgrade_u_bufferu_puteva"),
        "Zgrade u bufferu puteva",
        "pink",
        fill=True,
        show=False
    )
    dodaj_geojson_sloj(
        mapa,
        rezultati.get("clip_zgrade_oko_parcela"),
        "Clip - zgrade oko parcela",
        "darkgreen",
        fill=True,
        show=False
    )

    dodaj_geojson_sloj(
        mapa,
        rezultati.get("osm_zgrade_spojene_sa_parcelama_baze"),
        "OSM zgrade spojene sa parcelama iz baze",
        "gold",
        fill=True,
        show=True
    )

    folium.LayerControl(collapsed=False).add_to(mapa)

    putanja_mape = OUTPUT_MAPS / "geo_mapa.html"
    mapa.save(putanja_mape)

    print(f"Mapa je sacuvana: {putanja_mape}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("DEO 2 - PYTHON GEO ANALIZA")
    print("=" * 70)

    # 1. Ucitavanje tabela iz PostGIS baze
    engine = napravi_engine()

    parcele = ucitaj_postgis_tabelu(engine, "parcele", "parcela_id")
    legalni = ucitaj_postgis_tabelu(engine, "legalni_objekti", "objekat_id")
    bespravni = ucitaj_postgis_tabelu(engine, "bespravni_objekti", "bespravni_id")
    ml_detekcije = ucitaj_postgis_tabelu(engine, "detektovani_objekti_ml", "detekcija_id")

    # 2. Ucitavanje OSM slojeva za Novi Sad
    buildings = ucitaj_osm_sloj(
        "zgrade",
        {"building": True},
        dozvoljeni_tipovi=["Polygon", "MultiPolygon"]
    )

    roads = ucitaj_osm_sloj(
        "putevi",
        {"highway": True},
        dozvoljeni_tipovi=["LineString", "MultiLineString"]
    )

    water = ucitaj_osm_sloj(
        "voda",
        {"natural": "water"},
        dozvoljeni_tipovi=["Polygon", "MultiPolygon"]
    )

    landuse = ucitaj_osm_sloj(
        "namena zemljista",
        {"landuse": True},
        dozvoljeni_tipovi=["Polygon", "MultiPolygon"]
    )

    # 3. Racunanje povrsina
    buildings = izracunaj_povrsinu(buildings, "osm_povrsina_m2")
    parcele = izracunaj_povrsinu(parcele, "povrsina_iz_geometrije_m2")
    legalni = izracunaj_povrsinu(legalni, "povrsina_iz_geometrije_m2")
    bespravni = izracunaj_povrsinu(bespravni, "povrsina_iz_geometrije_m2")

    # 4. Cuvanje osnovnih slojeva
    sacuvaj_geojson(parcele, "parcele_iz_baze.geojson")
    sacuvaj_geojson(legalni, "legalni_objekti_iz_baze.geojson")
    sacuvaj_geojson(bespravni, "bespravni_objekti_iz_baze.geojson")
    sacuvaj_geojson(ml_detekcije, "detektovani_objekti_ml_iz_baze.geojson")
    sacuvaj_geojson(buildings, "osm_zgrade_novi_sad.geojson")
    sacuvaj_geojson(roads, "osm_putevi_novi_sad.geojson")
    sacuvaj_geojson(water, "osm_voda_novi_sad.geojson")
    sacuvaj_geojson(landuse, "osm_landuse_novi_sad.geojson")

    # 5. Geo analize
    rezultati = napravi_geo_analize(
        buildings=buildings,
        roads=roads,
        water=water,
        landuse=landuse,
        parcele=parcele,
        bespravni=bespravni
    )

    napravi_grafikone(rezultati, rezultati.get("within_bespravni_unutar_parcela"))
    

    for naziv, gdf in rezultati.items():
        sacuvaj_geojson(gdf, f"{naziv}.geojson")

        if not gdf.empty:
            tabela = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))
            tabela.to_csv(OUTPUT_TABLES / f"{naziv}.csv", index=False, encoding="utf-8-sig")

    # 6. Mapa
    napravi_mapu(
        parcele=parcele,
        legalni=legalni,
        bespravni=bespravni,
        buildings=buildings,
        roads=roads,
        water=water,
        landuse=landuse,
        rezultati=rezultati,
        ml_detekcije=ml_detekcije
    )

    print("=" * 70)
    print("GEO ANALIZA ZAVRSENA")
    print("=" * 70)


if __name__ == "__main__":
    main()