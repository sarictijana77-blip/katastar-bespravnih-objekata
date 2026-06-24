# Projekat: Katastar bespravnih objekata — Python SQL + GEO + ML

## 📋 Pregled projekta

Projekat se bavi detekcijom i analizom bespravnih objekata na teritoriji Novog Sada i okoline korišćenjem PostgreSQL/PostGIS baze podataka, geoprostornih analiza i mašinskog učenja.

---

## 📁 Struktura fajlova

```
c:\geo\
├── baza.py                   # Deo 1 – Python SQL (kreiranje tabela, CRUD, JOIN upiti)
├── README.md                 # Ova dokumentacija
├── dataset/
│   └── generisi_dataset.py   # Generator sintetičkog dataset-a (opciono)
└── query/                    # (prazan folder)
```

---

## Deo 1 – Šta radi `baza.py`?

`baza.py` je glavni Python skript koji implementira **Deo 1 projekta** — povezivanje sa PostgreSQL bazom, kreiranje tabela, unos podataka, CRUD operacije i JOIN upite.

### Šta sve sadrži:

| Funkcija | Opis |
|----------|------|
| `get_db_connection()` | Povezuje se na PostgreSQL bazu `katastar_db` na localhost:5432 |
| `kreiraj_tabele()` | Kreira 5 tabela sa PostGIS geometrijom, PK i FK |
| `unesi_inicijalne_podatke()` | Unosi 5+ redova po tabeli (INSERT) |
| `ucitaj_tabelu_u_df()` | Učitava tabelu u **pandas DataFrame** (geometrija → WKT) |
| `crud_dodaj_vlasnika(...)` | CREATE – dodaje novog vlasnika |
| `crud_prikazi_vlasnike()` | READ – prikazuje sve vlasnike |
| `crud_azuriraj_vlasnika(...)` | UPDATE – ažurira podatke vlasnika |
| `crud_obrisi_vlasnika(...)` | DELETE – briše vlasnika |
| `crud_dodaj_parcelu(...)` | CREATE – dodaje novu parcelu sa geometrijom |
| `crud_dodaj_bespravni(...)` | CREATE – dodaje bespravni objekat |
| `crud_azuriraj_status_objekta(...)` | UPDATE – menja status bespravnog objekta |
| `crud_obrisi_bespravni(...)` | DELETE – briše bespravni objekat |
| `crud_obrisi_inspektora(...)` | DELETE – briše inspektora |
| `izvrsi_kompleksne_upite()` | Izvršava **8 JOIN upita** sa WHERE filtriranjem |

### Tabele u bazi:

| Tabela | Kolone | PK | FK |
|--------|--------|----|----|
| `vlasnici` | vlasnik_id, ime, prezime, jmbg, telefon, email, adresa | vlasnik_id | — |
| `parcele` | parcela_id, broj_parcele, katastarska_opstina, povrsina_m2, namjena, vlasnik_id, geometrija (PostGIS) | parcela_id | vlasnik_id → vlasnici |
| `legalni_objekti` | objekat_id, broj_dozvole, spratnost, godina_izgradnje, namjena_objekta, parcela_id, geometrija (PostGIS) | objekat_id | parcela_id → parcele |
| `inspektori` | inspektor_id, ime, prezime, licenca, email, telefon, godina_zaposlenja, oblast_rada | inspektor_id | — |
| `bespravni_objekti` | bespravni_id, status_slucaja, procenjena_povrsina_m2, datum_detekcije, napomena, parcela_id, inspektor_id, geometrija (PostGIS) | bespravni_id | parcela_id → parcele, inspektor_id → inspektori |

### Kako pokrenuti `baza.py`:

```bash
python baza.py
```

---

## 🗄️ Instalacija PostgreSQL + PostGIS

### 1. Instalacija PostgreSQL (16 ili 17)

Preuzmi installer sa: [https://www.postgresql.org/download/windows/](https://www.postgresql.org/download/windows/)

Pokreni instalaciju i **zapamti šifru koju uneseš** (podrazumevano: `admin`).

### 2. Instalacija PostGIS ekstenzije

PostGIS se može instalirati na dva načina:

**Opcija A — Stack Builder (preporučeno):**
1. Posle instalacije PostgreSQL, pokreni **Stack Builder** (Start → PostgreSQL → Stack Builder)
2. Izaberi svoju PostgreSQL instalaciju
3. U listi kategorija proširi **Spatial Extensions**
4. Označi **PostGIS 3.x Bundle** i instaliraj
5. Tokom instalacije će te pitati da instaliraš i **shapefile** konektor — potvrdi

**Opcija B — Direktno preuzimanje (ako Stack Builder ne radi):**
- Preuzmi sa: [https://download.osgeo.org/postgis/windows/pgXX/](https://download.osgeo.org/postgis/windows/pgXX/)
- Zameni `pgXX` sa tvojom verzijom (npr. `pg17`)

### 3. Kreiranje baze i aktivacija PostGIS

Otvorí **SQL Shell (psql)** ili **pgAdmin** (instalira se uz PostgreSQL):

```sql
-- Kreiranje baze podataka (samo prvi put)
CREATE DATABASE katastar_db;

-- Poveži se na bazu (u psql: \c katastar_db)
-- Aktiviraj PostGIS ekstenziju
CREATE EXTENSION IF NOT EXISTS postgis;

-- Provjera da li je PostGIS instaliran
SELECT PostGIS_Version();
```

### 4. Podešavanje konekcije u `baza.py`

U `baza.py` na liniji 8-16 se nalaze parametri za konekciju:

```python
conn = psycopg2.connect(
    host="localhost",
    database="katastar_db",
    user="postgres",
    password="admin",      ← ZAMIJENI SA SVOJOM ŠIFROM
    port="5432"
)
```

Ako si postavio/la drugu šifru prilikom instalacije PostgreSQL, promijeni je u kodu.

---

## Deo 2 – Python GEO: Preporučeni datasetovi

### 🎯 Cilj:
Preuzeti **shapefile (shp) podatke za područje od interesa u Srbiji** (Novi Sad i okolina), učitati ih pomoću `geopandas`, napraviti prostorne analize (overlay tehnike) i prikazati na mapi sa raster podlogom.

### 📥 Preporučeni izvori podataka:

#### 1. Geofabrik — Serbia shapefiles (PRIMARNI IZVOR ⭐)

Ovo je glavni izvor za vektorske podatke. Preuzima se cijela Srbija u .shp formatu.

| Link | Opis |
|------|------|
| [https://download.geofabrik.de/europe/serbia-latest-free.shp.zip](https://download.geofabrik.de/europe/serbia-latest-free.shp.zip) | **Glavni zip fajl** — sadrži sve OSM slojeve za Srbiju (površine 600 MB) |
| [https://download.geofabrik.de/europe/serbia.html](https://download.geofabrik.de/europe/serbia.html) | **Stranica sa detaljima** — pregled svih slojeva, datuma izmjene, statistika |

**Šta se nalazi u zip fajlu (slojevi koji su relevantni):**

| Shapefile | Sadržaj | Veza sa bazom |
|-----------|---------|---------------|
| `gis_osm_buildings_a_free_1.shp` | **Zgrade (poligoni)** — svi objekti, površine, namjene | → `legalni_objekti` i `bespravni_objekti` |
| `gis_osm_landuse_a_free_1.shp` | **Namjena zemljišta** — građevinsko, poljoprivredno, šume | → `parcele.namjena` |
| `gis_osm_roads_free_1.shp` | **Saobraćajnice** — putevi, ulice (za kontekst i prostorne upite) |
| `gis_osm_water_a_free_1.shp` | **Vodene površine** — rijeke, jezera (za prostorne upite) |
| `gis_osm_places_a_free_1.shp` | **Naseljena mjesta** — gradovi, sela (za filtriranje po lokaciji) |
| `gis_osm_natural_free_1.shp` | **Prirodne površine** — parkovi, zelenilo (za overlay analize) |

#### 2. OpenStreetMap preko `osmnx` biblioteke (opciono)

Može se direktno preuzeti podatke za Novi Sad iz koda:

```python
import osmnx as ox

# Preuzmi zgrade za Novi Sad
gdf = ox.features_from_place("Novi Sad, Serbia", tags={"building": True})
```

#### 3. GeoSrbija — katastarski podaci

| Link | Opis |
|------|------|
| [https://geosrbija.rs/](https://geosrbija.rs/) | Nacionalni geoportal — katastar, parcele, objekti (za referencu) |

> **Napomena:** GeoSrbija nema direktan download .shp fajlova, ali se može koristiti kao referentni sloj na mapi.

### ✅ Kompatibilnost sa bazom

Tabela `parcele` u bazi sadrži kolone:
- `broj_parcele`, `katastarska_opstina`, `povrsina_m2`, `namjena`, `geometrija`

Shapefile `gis_osm_landuse_a_free_1.shp` sadrži:
- `fclass` (tip zemljišta — residential, commercial, industrial, farmland → mapira se na `namjena`)
- Geometrija (Polygon) → direktno se može učitati u `geometrija` kolonu

Shapefile `gis_osm_buildings_a_free_1.shp` sadrži:
- `type` (tip zgrade), `name` (naziv), geometrija (Polygon) → mapira se na `legalni_objekti`

**Baza je kompatibilna!** Potrebno je samo mapirati kolone iz shapefile-a u kolone iz baze (npr. `fclass` → `namjena`, `type` → `namjena_objekta`).

### 📦 Biblioteke potrebne za Deo 2:

```bash
pip install geopandas matplotlib contextily folium rasterio osmnx
```

---

## Deo 3 – Python ML: Preporučeni datasetovi

### 🎯 Cilj:
Upotrebom algoritama mašinskog učenja (YOLO / segmentacija) detektovati objekte na satelitskim snimcima, konvertovati ih u vektorski format (GeoJSON/shapefile), učitati u PostGIS bazu i prikazati na mapi.

### 📥 Preporučeni izvori podataka:

#### 1. Copernicus Sentinel-2 satelitski snimci (PRIMARNI IZVOR ⭐)

Besplatni satelitski snimci visoke rezolucije (10m/piksel).

| Link | Opis |
|------|------|
| [https://dataspace.copernicus.eu/](https://dataspace.copernicus.eu/) | **Copernicus Data Space** — glavni portal za preuzimanje |
| [https://browser.dataspace.copernicus.eu/](https://browser.dataspace.copernicus.eu/) | **EO Browser** — vizuelni preglednik, biraj područje i preuzmi |

**Kako preuzeti:**
1. Otvori [EO Browser](https://browser.dataspace.copernicus.eu/)
2. Izaberi **Sentinel-2 L2A** (True Color)
3. Zumiraj na **Novi Sad** (45.267°N, 19.833°E)
4. Izaberi datum s minimalnom oblačnošću (cloud cover < 10%)
5. Klikni na "Download" → biraj **GeoTIFF format** (za raster podlogu)

#### 2. Google Earth Engine (napredna opcija)

| Link | Opis |
|------|------|
| [https://code.earthengine.google.com/](https://code.earthengine.google.com/) | Google Earth Engine Code Editor |
| [https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED) | Sentinel-2 dataset u GEE |

**Zahtijeva:** Google nalog i aktivaciju Earth Engine pristupa.

#### 3. OpenAerialMap — satelitski i dron snimci

| Link | Opis |
|------|------|
| [https://openaerialmap.org/](https://openaerialmap.org/) | Besplatni satelitski i dron snimci (za područje Srbije ima ograničeno) |

#### 4. Prethodno obučeni modeli (YOLO) — za detekciju objekata

| Link | Opis |
|------|------|
| [https://github.com/ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) | **YOLOv11** — najnovija verzija, instalira se sa `pip install ultralytics` |
| [https://docs.ultralytics.com/datasets/detect/coco/](https://docs.ultralytics.com/datasets/detect/coco/) | COCO dataset (80 klasa, uključuje "building") |
| [https://universe.roboflow.com/](https://universe.roboflow.com/) | **Roboflow** — hiljade datasetova za detekciju objekata na satelitskim snimcima |

**Preporučeni datasetovi sa Roboflow-a** (pretraži "building satellite detection"):
- `satellite-building-detection` — detekcija zgrada na satelitskim snimcima
- `xview-building-detection` — detekcija zgrada iz xView takmičenja

### 📦 Biblioteke potrebne za Deo 3:

```bash
pip install torch torchvision ultralytics opencv-python pillow rasterio folium geopandas
```

### ✅ Kompatibilnost sa bazom

Detektovani objekti iz YOLO modela se konvertuju u **GeoJSON** format (poligoni sa koordinatama), a zatim se mogu učitati u tabelu `bespravni_objekti`:

```python
import geopandas as gpd
from shapely.geometry import Polygon

# Primjer: Konverzija YOLO bounding box-a u poligon
# (x1, y1, x2, y2) → POLYGON u WGS84
poligon = Polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])
gdf = gpd.GeoDataFrame({'procenjena_povrsina_m2': [povrsina]}, geometry=[poligon], crs="EPSG:4326")

# Učitavanje u PostGIS
from sqlalchemy import create_engine
engine = create_engine('postgresql://postgres:admin@localhost:5432/katastar_db')
gdf.to_postgis('bespravni_objekti', engine, if_exists='append')
```

---

## 📊 Pregled datasetova — tabela

| Deo | Dataset | Format | Veličina | Link |
|-----|---------|--------|----------|------|
| **Deo 2** | Geofabrik Serbia (OSM) | Shapefile (.shp) | 600 MB | [Preuzmi](https://download.geofabrik.de/europe/serbia-latest-free.shp.zip) |
| **Deo 2** | OSM Novi Sad (buildings) | GeoJSON/GPKG | ~50 MB | Preko `osmnx` biblioteke |
| **Deo 3** | Copernicus Sentinel-2 | GeoTIFF | 100-500 MB | [EO Browser](https://browser.dataspace.copernicus.eu/) |
| **Deo 3** | Copernicus Sentinel-2 (GEE) | ImageCollection | — | [GEE Catalog](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED) |
| **Deo 3** | Roboflow building detection | COCO/YOLO format | Promjenljivo | [Roboflow](https://universe.roboflow.com/) |
| **Deo 3** | YOLOv11 pretrenirani model | .pt (PyTorch) | ~50 MB | `pip install ultralytics` → `yolov11n.pt` |

---

## 🚀 Brzi start (korak po korak)

### 1. Instaliraj PostgreSQL

```bash
# Preuzmi sa: https://www.postgresql.org/download/windows/
# Pokreni installer → zapamti šifru
```

### 2. Instaliraj PostGIS

```bash
# Preko Stack Buildera: Start → PostgreSQL → Stack Builder → Spatial Extensions → PostGIS
# Ili ručno preuzmi sa: https://download.osgeo.org/postgis/windows/
```

### 3. Kreiraj bazu

```sql
-- U SQL Shell (psql) ili pgAdmin:
CREATE DATABASE katastar_db;
\c katastar_db
CREATE EXTENSION postgis;
SELECT PostGIS_Version();  -- treba da vrati npr. "3.4 USE_GEOS=1 USE_PROJ=1"
```

### 4. Instaliraj Python biblioteke

```bash
pip install psycopg2 pandas geopandas matplotlib contextily folium rasterio
pip install torch torchvision ultralytics opencv-python  # za Deo 3
```

### 5. Pokreni baza.py

```bash
python baza.py
```

Očekivani izlaz:
```
============================================================
KREIRANJE TABELA U BAZI
============================================================
Sve tabele su uspešno kreirane!

============================================================
UNOS INICIJALNIH PODATAKA
============================================================
Inicijalni podaci uspešno unešeni!

...
```

### 6. Preuzmi podatke za Deo 2

```bash
# Ručno preuzmi zip: https://download.geofabrik.de/europe/serbia-latest-free.shp.zip
# Raspakuj u folder c:\geo\geo_podaci\
```

### 7. Preuzmi satelitski snimak za Deo 3

```bash
# Otvori EO Browser: https://browser.dataspace.copernicus.eu/
# Zumiraj na Novi Sad → Download → GeoTIFF
```

---

## ❗ Napomene

- **Šifra za PostgreSQL** u `baza.py` je podešena na `admin`. Ako si postavio/la drugu šifru, **obavezno je promijeni** u kodu (linija 13).
- **Geofabrik shapefile-ovi** su veliki (~600 MB), preporučuje se dobra internet konekcija.
- **Copernicus snimci** zahtijevaju registraciju (besplatno) na [dataspace.copernicus.eu](https://dataspace.copernicus.eu/).
- **YOLO model** će raditi i na CPU, ali je znatno brži na GPU (NVIDIA CUDA).
- Ako ne želiš da instaliraš PostgreSQL lokalno, možeš koristiti **Docker**:

```bash
docker run --name postgis -e POSTGRES_PASSWORD=admin -p 5432:5432 -d postgis/postgis:16-3.4
```
