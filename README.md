# Projekat: Katastar bespravno izgrađenih objekata — Adica, Novi Sad

## 📋 Pregled projekta

Projekat se bavi evidencijom, geoprostornom analizom i automatskom detekcijom bespravno izgrađenih objekata u naselju **Adica** (Novi Sad), korišćenjem PostgreSQL/PostGIS baze podataka, geoprostornih analiza (geopandas/folium) i mašinskog učenja (KMeans segmentacija).

Projekat je podeljen na tri celine:
- **Deo 1 — Python SQL**: baza podataka, CRUD operacije, JOIN upiti
- **Deo 2 — Python GEO**: OSM podaci, prostorne analize, interaktivna mapa
- **Deo 3 — Python ML**: detekcija objekata sa ortofoto snimka, klasifikacija legalno/bespravno, aplikacije za upravljanje rezultatima

---

## 📁 Struktura fajlova

```
katastar-bespravnih-objekata/
├── baza.py                     # Deo 1 – baza, CRUD, JOIN upiti
├── geo_analiza.py               # Deo 2 – OSM podaci, prostorne analize, geo_mapa.html
├── ml_detekcija.py               # Deo 3 – ML detekcija, klasifikacija, ml_mapa.html
├── dodaj_legalne_objekte.py      # Pomoćna skripta – test-podaci za legalne objekte
├── app_atributi.py                # Deo 3 – konzolna CRUD aplikacija za ML detekcije
├── app_streamlit.py               # Deo 3 – Streamlit (GUI) aplikacija
├── requirements.txt
├── .gitignore
├── README.md
├── data/
│   ├── raw/
│   │   └── raster/
│   │       ├── novi_sad.png      # Ortofoto snimak Adice (GeoSrbija)
│   │       └── aoi.geojson       # Granica obuhvata snimka (AOI)
│   └── processed/                 # Generisani GeoJSON slojevi (nije u git-u)
├── outputs/
│   ├── maps/                       # geo_mapa.html, ml_mapa.html (nije u git-u)
│   ├── figures/                    # Grafikoni i obeležene slike (nije u git-u)
│   └── tables/                     # CSV izvozi analiza (nije u git-u)
└── query/
```

> **Napomena o `.gitignore`:** folderi `outputs/` i `data/processed/` se ne prate na GitHub-u (generišu se ponovo pri svakom pokretanju koda). Ulazni podaci (`data/raw/raster/`) se prate, jer su neophodni da bi se projekat mogao pokrenuti od nule.

---

## Deo 1 – `baza.py`

Povezivanje na PostgreSQL/PostGIS bazu, kreiranje tabela, unos podataka, CRUD operacije i JOIN upiti.

### Tabele u bazi

| Tabela | Kolone | PK | FK |
|--------|--------|----|----|
| `vlasnici` | vlasnik_id, ime, prezime, jmbg, telefon, email, adresa | vlasnik_id | — |
| `parcele` | parcela_id, broj_parcele, katastarska_opstina, povrsina_m2, namjena, vlasnik_id, geometrija | parcela_id | vlasnik_id → vlasnici |
| `legalni_objekti` | objekat_id, broj_dozvole, spratnost, godina_izgradnje, namjena_objekta, parcela_id, geometrija | objekat_id | parcela_id → parcele |
| `inspektori` | inspektor_id, ime, prezime, licenca, email, telefon, godina_zaposlenja, oblast_rada | inspektor_id | — |
| `bespravni_objekti` | bespravni_id, status_slucaja, procenjena_povrsina_m2, datum_detekcije, napomena, parcela_id, inspektor_id, geometrija | bespravni_id | parcela_id → parcele, inspektor_id → inspektori |

### CRUD funkcije (pun CRUD za sve tabele)

| Tabela | Create | Read | Update | Delete |
|--------|--------|------|--------|--------|
| Vlasnici | `crud_dodaj_vlasnika` | `crud_prikazi_vlasnike` | `crud_azuriraj_vlasnika` | `crud_obrisi_vlasnika` |
| Parcele | `crud_dodaj_parcelu` | `crud_prikazi_parcele` | `crud_azuriraj_parcelu` | `crud_obrisi_parcelu` |
| Legalni objekti | `crud_dodaj_legalni_objekat` | `crud_prikazi_legalne_objekte` | `crud_azuriraj_legalni_objekat` | `crud_obrisi_legalni_objekat` |
| Inspektori | `crud_dodaj_inspektora` | `crud_prikazi_inspektore` | `crud_azuriraj_inspektora` | `crud_obrisi_inspektora` |
| Bespravni objekti | `crud_dodaj_bespravni` | `crud_prikazi_bespravne` | `crud_azuriraj_status_objekta` | `crud_obrisi_bespravni` |

Dodatno: `izvrsi_kompleksne_upite()` izvršava **8 JOIN upita** sa WHERE filtriranjem po više tabela.

### Pokretanje

```bash
python baza.py
```

---

## 🗄️ Instalacija PostgreSQL + PostGIS

### 1. Instalacija PostgreSQL (16 ili 17)

Preuzmi installer sa: [https://www.postgresql.org/download/windows/](https://www.postgresql.org/download/windows/)

Pokreni instalaciju i **zapamti šifru koju uneseš** (podrazumevano: `admin`).

### 2. Instalacija PostGIS ekstenzije

**Opcija A — Stack Builder (preporučeno):**
1. Posle instalacije PostgreSQL, pokreni **Stack Builder** (Start → PostgreSQL → Stack Builder)
2. Izaberi svoju PostgreSQL instalaciju
3. U listi kategorija proširi **Spatial Extensions**
4. Označi **PostGIS 3.x Bundle** i instaliraj

**Opcija B — Direktno preuzimanje:**
- Preuzmi sa: [https://download.osgeo.org/postgis/windows/pgXX/](https://download.osgeo.org/postgis/windows/pgXX/) (zameni `pgXX` sa svojom verzijom)

### 3. Kreiranje baze i aktivacija PostGIS

U **SQL Shell (psql)** ili **pgAdmin**:

```sql
CREATE DATABASE katastar_db;
\c katastar_db
CREATE EXTENSION postgis;
SELECT PostGIS_Version();
```

### 4. Podešavanje konekcije

U svakom `.py` fajlu (`baza.py`, `geo_analiza.py`, `ml_detekcija.py`, `app_atributi.py`) na vrhu fajla:

```python
DB_HOST = "localhost"
DB_NAME = "katastar_db"
DB_USER = "postgres"
DB_PASSWORD = "admin"   # zameni ako je tvoja šifra drugačija
DB_PORT = "5432"
```

---

## Deo 2 – `geo_analiza.py`

### Izvor podataka

Umesto ručnog preuzimanja `.shp` fajlova sa Geofabrik-a, podaci se preuzimaju **direktno kroz kod** pomoću biblioteke `osmnx` (isti tip OSM podataka — zgrade, putevi, voda, namena zemljišta — za teritoriju Novog Sada).

### Šta radi

1. **Učitava tabele iz Dela 1** (`parcele`, `legalni_objekti`, `bespravni_objekti`) kao GeoDataFrame preko PostGIS-a
2. **Preuzima OSM slojeve** za Novi Sad: zgrade, putevi, voda, namena zemljišta
3. **Računa površine** u projektovanom CRS-u (EPSG:32634 — UTM zona 34N za Srbiju)
4. **Prostorne analize** (7 primera, funkcija `napravi_geo_analize`):

| # | Analiza | Tehnika |
|---|---------|---------|
| 1 | `clip_zgrade_oko_parcela` | **Clip** — OSM zgrade isečene po granici parcela iz baze (+200m bafer) |
| 2 | `buffer_50m_oko_puteva` | **Buffer** — 50m zona oko puteva |
| 3 | `zgrade_spojene_sa_namenom_zemljista` | **Spatial join (intersects)** |
| 4 | `intersection_zgrade_poljoprivredno` | **Intersection overlay** — zgrade na poljoprivrednom zemljištu |
| 5 | `within_bespravni_unutar_parcela` | **Within** — bespravni objekti unutar parcela |
| 6 | `zgrade_u_bufferu_puteva` | Zgrade unutar buffer zone puteva |
| 7 | `osm_zgrade_spojene_sa_parcelama_baze` | **Spajanje shapefile (OSM) podataka sa tabelom iz Dela 1** — OSM zgrade spojene sa parcelama iz baze po lokaciji |

5. **Grafikoni** (`napravi_grafikone`, čuvaju se u `outputs/figures/`):
   - `zgrade_po_nameni_zemljista.png` — bar grafikon broja OSM zgrada po nameni zemljišta
   - `bespravni_po_opstini.png` — bar grafikon broja bespravnih objekata po katastarskoj opštini

6. **Interaktivna mapa** (`outputs/maps/geo_mapa.html`) — Folium mapa sa uključivanjem/isključivanjem slojeva (LayerControl) i različitom simbologijom (bojom) po sloju:
   - Parcele, legalni objekti, bespravni objekti (iz baze)
   - OSM zgrade, putevi, voda, namena zemljišta
   - Svih 7 rezultata prostornih analiza
   - **ML detekcije iz Dela 3** (`detektovani_objekti_ml`), razdvojene po statusu — kandidati za bespravne (crimson) i podudarni sa legalnim (limegreen)
   - Raster podloge (CartoDB svetla/tamna, OpenStreetMap)

### Pokretanje

```bash
python geo_analiza.py
```

---

## Deo 3 – Detekcija, klasifikacija i aplikacije

### `ml_detekcija.py`

**Ulazni podaci:** `data/raw/raster/novi_sad.png` (ortofoto snimak Adice sa GeoSrbija sajta) i `data/raw/raster/aoi.geojson` (granica obuhvata snimka).

> **Tehnička napomena:** `aoi.geojson` ima pogrešno upisan CRS tag u samom fajlu (deklariše EPSG:4326), dok su stvarne koordinate u metrima (UTM, EPSG:32634). Kod ovo ispravlja prinudno (`set_crs(CRS_METERS, allow_override=True)`) — ako se ikad zameni ulazni AOI fajl, ovo treba proveriti.

**ML metoda:** KMeans segmentacija boje (nenadgledano učenje, `scikit-learn`) — grupiše piksele snimka po boji (HSV + LAB prostor), izdvaja klase koje liče na krovove (crveni/braon/svetli), izbacuje vegetaciju, vodu, asfalt i senke. Konture iz maske se pretvaraju u poligone (`shapely`), sa filterima za minimalnu površinu, odnos stranica i popunjenost bounding box-a (da se izbegnu lažne detekcije ulica/senki).

**Poznato ograničenje:** metoda zasnovana na boji ima ograničenu preciznost (recall) za atipične krovove — tamne, u senci, ili nepravilnog oblika. Nadgledani model (npr. YOLO treniran na anotiranim podacima) bi bio precizniji, ali zahteva trening podatke koji nisu bili dostupni za ovaj projekat.

**Tok obrade:**
1. Učitavanje slike i AOI granice
2. KMeans segmentacija → maska kandidata
3. Konture → poligoni (georeferencirani preko AOI granice)
4. Spajanje sa parcelama iz baze (`dodeli_parcele`) — dodela `parcela_id` svakoj detekciji
5. **Klasifikacija legalno/bespravno** (`oznaci_bespravne`) — spatial join detekcija sa `legalni_objekti` tabelom (sa 1m baferom): ako se detekcija preklapa sa legalnim objektom → status `"Podudara se sa legalnim objektom"`; ako ne → `"Kandidat - bespravni objekat"`
6. Upis u PostGIS tabelu `detektovani_objekti_ml`
7. **Prostorne analize nad rezultatima** (5 primera): spoj sa parcelama, presek sa legalnim objektima, buffer 100m oko ranije evidentiranih bespravnih objekata, buffer 25m oko ML detekcija, detekcije unutar AOI
8. **Grafikoni** (`napravi_grafikone_ml`): `ml_odnos_legalno_bespravno.png` (pie chart), `ml_histogram_povrsina.png` (histogram raspodele površina)
9. Interaktivna mapa `outputs/maps/ml_mapa.html`

**Tabela `detektovani_objekti_ml`:**

| Kolona | Opis |
|--------|------|
| detekcija_id | PK |
| status_slucaja | "Kandidat - bespravni objekat" / "Podudara se sa legalnim objektom" |
| procenjena_povrsina_m2 | računa se u EPSG:32634 |
| confidence | procenjena pouzdanost detekcije (na osnovu popunjenosti oblika) |
| izvor_snimka, model | metapodaci o poreklu detekcije |
| parcela_id, inspektor_id | FK → parcele, inspektori |
| geometrija | GEOMETRY(Polygon, 4326) |

#### Pokretanje

```bash
python ml_detekcija.py
```

### `dodaj_legalne_objekte.py`

Pomoćna, jednokratna skripta koja generiše **realistične test-podatke** za `legalni_objekti`/`parcele`: uzima N najvećih ML detekcija (podrazumevano 115 od ukupno ~172) i za svaku pravi odgovarajuću parcelu i legalni objekat sa identičnom geometrijom — simulirajući da ti objekti imaju građevinsku dozvolu. Ovo omogućava da klasifikacija u `ml_detekcija.py` ima realan, mešoviti rezultat (npr. ~116 legalnih / ~56 kandidata za bespravne) umesto da originalni, geografski neciljani test-podaci iz `baza.py` daju 0 poklapanja.

> **Napomena za izveštaj:** ovo su sintetički test-podaci, ne zvanični podaci RGZ-a/građevinske inspekcije (koji nisu javno dostupni). Sistem je dizajniran da radi ispravno sa pravim podacima kad/ako postanu dostupni.

**Redosled pokretanja (bitno):**
```bash
python ml_detekcija.py              # 1. generiše sve detekcije (sve ispadaju "bespravne")
python dodaj_legalne_objekte.py     # 2. generiše test legalne objekte na osnovu detekcija
python ml_detekcija.py              # 3. ponovo - sad klasifikacija ima realan rezultat
```

### `app_atributi.py` — konzolna CRUD aplikacija

Tekstualna (terminalska) aplikacija za pregled i izmenu ML detekcija: prikaz svih/filtriranih po statusu, prikaz detalja jedne detekcije, promena statusa, promena napomene, dodela inspektora, brisanje (sa potvrdom), statistika po statusu.

```bash
python app_atributi.py
```

### `app_streamlit.py` — GUI aplikacija

Streamlit aplikacija koja **ponovo koristi funkcije iz `app_atributi.py`** (bez duplog koda) i dodaje vizuelni sloj: tri stranice (Pregled i statistika, Mapa, Izmena atributa), sa direktno ugrađenim interaktivnim mapama (`geo_mapa.html`, `ml_mapa.html`) i automatskim prikazom svih sačuvanih grafikona.

```bash
pip install streamlit
python -m streamlit run app_streamlit.py
```

Otvara se u browseru na `localhost:8501` (radi potpuno lokalno, ne zahteva internet).

---

## 🚀 Redosled pokretanja celog projekta (od nule)

```bash
# 1. Baza (Deo 1)
python baza.py

# 2. Geo analiza (Deo 2)
python geo_analiza.py

# 3. ML detekcija - prvi prolaz (Deo 3)
python ml_detekcija.py

# 4. Generisanje test legalnih objekata na stvarnim koordinatama
python dodaj_legalne_objekte.py

# 5. Geo analiza ponovo - sad uključuje i ML sloj sa realnim poklapanjima
python geo_analiza.py

# 6. ML detekcija ponovo - sad klasifikacija ima realan rezultat
python ml_detekcija.py

# 7. Aplikacija za upravljanje atributima (konzolna ili GUI)
python app_atributi.py
# ili
python -m streamlit run app_streamlit.py
```

---

## 📦 Instalacija Python biblioteka

```bash
pip install -r requirements.txt
pip install streamlit
```

Ako `geopandas`/`rasterio`/`shapely` prave probleme preko pip-a na Windows-u, koristiti conda:
```bash
conda install -c conda-forge geopandas rasterio shapely
```

---

## ❗ Napomene

- **Test/sintetički podaci**: baza sadrži kombinaciju originalnih ručno unetih test-redova (Deo 1) i generisanih test-podataka baziranih na stvarnim ML detekcijama (`dodaj_legalne_objekte.py`) — ovo je jasno naznačeno jer zvanični podaci RGZ-a o vlasništvu/dozvolama nisu javno dostupni za preuzimanje.
- **CRS pažnja**: `aoi.geojson` ima netačno deklarisan CRS u samom fajlu — kod to ispravlja programski, ali treba imati na umu ako se ulazni podaci ikad menjaju.
- **`.gitignore`**: `outputs/` i `data/processed/` nisu deo git repozitorijuma (generišu se pokretanjem koda); `data/raw/raster/` **jeste** deo repozitorijuma (neophodni ulazni podaci za reprodukciju).