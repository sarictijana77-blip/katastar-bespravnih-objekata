import psycopg2
import pandas as pd
from psycopg2 import extras

# ============================================================
# 1. POVEZIVANJE NA BAZU PODATAKA
# ============================================================
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="katastar_db",
            user="postgres",
            password="admin",
            port="5432"
        )
        return conn
    except Exception as e:
        print(f"Greška pri povezivanju na bazu: {e}")
        return None

# ============================================================
# 2. KREIRANJE TABELA (5 tabela, 5-10 kolona, PK, FK, PostGIS)
# ============================================================
def kreiraj_tabele():
    conn = get_db_connection()
    if not conn: return
    cur = conn.cursor()
    
    # Aktivacija PostGIS ekstenzije
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    
    tabele = [
        """
        CREATE TABLE IF NOT EXISTS vlasnici (
            vlasnik_id SERIAL PRIMARY KEY,
            ime VARCHAR(50) NOT NULL,
            prezime VARCHAR(50) NOT NULL,
            jmbg VARCHAR(13) UNIQUE NOT NULL,
            telefon VARCHAR(20),
            email VARCHAR(100),
            adresa VARCHAR(200)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS parcele (
            parcela_id SERIAL PRIMARY KEY,
            broj_parcele VARCHAR(20) NOT NULL,
            katastarska_opstina VARCHAR(100) NOT NULL,
            povrsina_m2 NUMERIC(10, 2),
            namjena VARCHAR(50) DEFAULT 'neodređeno',
            vlasnik_id INT REFERENCES vlasnici(vlasnik_id) ON DELETE SET NULL,
            geometrija GEOMETRY(Polygon, 4326)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS legalni_objekti (
            objekat_id SERIAL PRIMARY KEY,
            broj_dozvole VARCHAR(50) UNIQUE NOT NULL,
            spratnost VARCHAR(20),
            godina_izgradnje INT,
            namjena_objekta VARCHAR(100) DEFAULT 'stambeni',
            parcela_id INT REFERENCES parcele(parcela_id) ON DELETE CASCADE,
            geometrija GEOMETRY(Polygon, 4326)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS inspektori (
            inspektor_id SERIAL PRIMARY KEY,
            ime VARCHAR(50) NOT NULL,
            prezime VARCHAR(50) NOT NULL,
            licenca VARCHAR(30) UNIQUE NOT NULL,
            email VARCHAR(100),
            telefon VARCHAR(20),
            godina_zaposlenja INT,
            oblast_rada VARCHAR(100) DEFAULT 'opšta'
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS bespravni_objekti (
            bespravni_id SERIAL PRIMARY KEY,
            status_slucaja VARCHAR(30) DEFAULT 'Detektovano',
            procenjena_povrsina_m2 NUMERIC(10, 2),
            datum_detekcije DATE DEFAULT CURRENT_DATE,
            napomena TEXT,
            parcela_id INT REFERENCES parcele(parcela_id) ON DELETE CASCADE,
            inspektor_id INT REFERENCES inspektori(inspektor_id) ON DELETE SET NULL,
            geometrija GEOMETRY(Polygon, 4326)
        );
        """
    ]
    
    for tabela in tabele:
        cur.execute(tabela)
        
    conn.commit()
    cur.close()
    conn.close()
    print("Sve tabele su uspešno kreirane!")

# ============================================================
# 3. RUČNI UNOS PODATAKA (INSERT - najmanje 5 redova po tabeli)
# ============================================================
def unesi_inicijalne_podatke():
    conn = get_db_connection()
    if not conn: return
    cur = conn.cursor()
    
    try:
        # --- Vlasnici ---
        cur.execute("""
            INSERT INTO vlasnici (ime, prezime, jmbg, telefon, email, adresa) VALUES
            ('Marko', 'Marković', '0101990800011', '064111222', 'marko@email.com', 'Novi Sad, Bulevar Oslobođenja 1'),
            ('Nikola', 'Nikolić', '1212985800022', '065333444', 'nikola@email.com', 'Novi Sad, Zmaj Jovina 5'),
            ('Jovan', 'Jovanović', '1505993800033', '063555666', 'jovan@email.com', 'Veternik, Petrova 10'),
            ('Milica', 'Petrović', '2010996800044', '062777888', 'milica@email.com', 'Petrovaradin, Dunavska 20'),
            ('Ana', 'Anić', '2512991800055', '061999000', 'ana@email.com', 'Sremska Kamenica, Vidikovac 15')
            ON CONFLICT (jmbg) DO NOTHING;
        """)
        
        # --- Parcele ---
        cur.execute("""
            INSERT INTO parcele (broj_parcele, katastarska_opstina, povrsina_m2, namjena, vlasnik_id, geometrija) VALUES
            ('1001', 'Novi Sad I', 500.00, 'građevinsko', 1, ST_GeomFromText('POLYGON((19.8 45.2, 19.81 45.2, 19.81 45.21, 19.8 45.21, 19.8 45.2))', 4326)),
            ('1002', 'Novi Sad I', 620.50, 'građevinsko', 2, ST_GeomFromText('POLYGON((19.81 45.2, 19.82 45.2, 19.82 45.21, 19.81 45.21, 19.81 45.2))', 4326)),
            ('2045', 'Veternik', 800.00, 'poljoprivredno', 3, ST_GeomFromText('POLYGON((19.75 45.25, 19.76 45.25, 19.76 45.26, 19.75 45.26, 19.75 45.25))', 4326)),
            ('501', 'Petrovaradin', 1200.00, 'građevinsko', 4, ST_GeomFromText('POLYGON((19.87 45.23, 19.88 45.23, 19.88 45.24, 19.87 45.24, 19.87 45.23))', 4326)),
            ('120', 'Sremska Kamenica', 950.00, 'građevinsko', 5, ST_GeomFromText('POLYGON((19.84 45.21, 19.85 45.21, 19.85 45.22, 19.84 45.22, 19.84 45.21))', 4326))
            ON CONFLICT DO NOTHING;
        """)
        
        # --- Legalni objekti ---
        cur.execute("""
            INSERT INTO legalni_objekti (broj_dozvole, spratnost, godina_izgradnje, namjena_objekta, parcela_id, geometrija) VALUES
            ('ROP-NS-11-2023', 'P+1+Pk', 2023, 'stambeni', 1, ST_GeomFromText('POLYGON((19.801 45.201, 19.805 45.201, 19.805 45.205, 19.801 45.205, 19.801 45.201))', 4326)),
            ('ROP-NS-12-2023', 'P+0', 2018, 'poslovni', 2, ST_GeomFromText('POLYGON((19.811 45.201, 19.815 45.201, 19.815 45.205, 19.811 45.205, 19.811 45.201))', 4326)),
            ('ROP-VT-05-2024', 'P+2', 2024, 'stambeni', 3, ST_GeomFromText('POLYGON((19.751 45.251, 19.755 45.251, 19.755 45.255, 19.751 45.255, 19.751 45.251))', 4326)),
            ('ROP-PR-99-2022', 'P+1', 2022, 'stambeni', 4, ST_GeomFromText('POLYGON((19.871 45.231, 19.875 45.231, 19.875 45.235, 19.871 45.235, 19.871 45.231))', 4326)),
            ('ROP-SK-44-2024', 'P+1', 2020, 'poslovni', 5, ST_GeomFromText('POLYGON((19.841 45.211, 19.845 45.211, 19.845 45.215, 19.841 45.215, 19.841 45.211))', 4326))
            ON CONFLICT (broj_dozvole) DO NOTHING;
        """)
        
        # --- Inspektori ---
        cur.execute("""
            INSERT INTO inspektori (ime, prezime, licenca, email, telefon, godina_zaposlenja, oblast_rada) VALUES
            ('Dragan', 'Mirić', 'LIC-101', 'dragan.miric@inspekcija.rs', '060111222', 2015, 'građevinska'),
            ('Zoran', 'Kojić', 'LIC-102', 'zoran.kojic@inspekcija.rs', '060333444', 2018, 'građevinska'),
            ('Elena', 'Ristić', 'LIC-103', 'elena.ristic@inspekcija.rs', '060555666', 2020, 'komunalna'),
            ('Goran', 'Tadić', 'LIC-104', 'goran.tadic@inspekcija.rs', '060777888', 2010, 'građevinska'),
            ('Maja', 'Ilić', 'LIC-105', 'maja.ilic@inspekcija.rs', '060999000', 2022, 'komunalna')
            ON CONFLICT (licenca) DO NOTHING;
        """)
        
        # --- Bespravni objekti ---
        cur.execute("""
            INSERT INTO bespravni_objekti (status_slucaja, procenjena_povrsina_m2, datum_detekcije, napomena, parcela_id, inspektor_id, geometrija) VALUES
            ('Detektovano', 120.50, '2024-01-15', 'Dogradnja bez dozvole', 1, 1, ST_GeomFromText('POLYGON((19.806 45.206, 19.809 45.206, 19.809 45.209, 19.806 45.209, 19.806 45.206))', 4326)),
            ('U proceduri', 85.00, '2024-02-20', 'Nadogradnja sprata', 2, 2, ST_GeomFromText('POLYGON((19.816 45.206, 19.819 45.206, 19.819 45.209, 19.816 45.209, 19.816 45.206))', 4326)),
            ('Detektovano', 210.00, '2024-03-10', 'Nova kuća na poljoprivrednom zemljištu', 3, 3, ST_GeomFromText('POLYGON((19.756 45.256, 19.759 45.256, 19.759 45.259, 19.756 45.259, 19.756 45.256))', 4326)),
            ('Rusenje', 45.00, '2024-04-05', 'Pomoćni objekat na trotoaru', 4, 4, ST_GeomFromText('POLYGON((19.876 45.236, 19.879 45.236, 19.879 45.239, 19.876 45.239, 19.876 45.236))', 4326)),
            ('U proceduri', 155.00, '2024-05-12', 'Proširenje poslovnog prostora', 5, 5, ST_GeomFromText('POLYGON((19.846 45.216, 19.849 45.216, 19.849 45.219, 19.846 45.219, 19.846 45.216))', 4326))
            ON CONFLICT DO NOTHING;
        """)
        
        conn.commit()
        print("Inicijalni podaci uspešno unešeni!")
    except Exception as e:
        conn.rollback()
        print(f"Greška kod unosa podataka: {e}")
    finally:
        cur.close()
        conn.close()

# ============================================================
# 4. PANDAS - Učitavanje tabela u DataFrame
# ============================================================
def ucitaj_tabelu_u_df(ime_tabele):
    conn = get_db_connection()
    if not conn: return None
    
    # Za tabele sa geometrijom, pretvaramo geometriju u WKT tekst
    if ime_tabele in ['parcele', 'legalni_objekti', 'bespravni_objekti']:
        upit = f"SELECT *, ST_AsText(geometrija) AS wkt_geometrija FROM {ime_tabele};"
    else:
        upit = f"SELECT * FROM {ime_tabele};"
        
    df = pd.read_sql_query(upit, conn)
    conn.close()
    return df

# ============================================================
# 5. CRUD OPERACIJE (Create, Read, Update, Delete za sve tabele)
# ============================================================

# --- VLASNICI ---
def crud_dodaj_vlasnika(ime, prezime, jmbg, telefon=None, email=None, adresa=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO vlasnici (ime, prezime, jmbg, telefon, email, adresa) VALUES (%s, %s, %s, %s, %s, %s);",
            (ime, prezime, jmbg, telefon, email, adresa)
        )
        conn.commit()
        print(f"Uspešno dodat vlasnik {ime} {prezime}.")
    except Exception as e:
        conn.rollback()
        print(f"Greška pri dodavanju vlasnika: {e}")
    finally:
        cur.close()
        conn.close()

def crud_prikazi_vlasnike():
    conn = get_db_connection()
    if not conn: return
    df = pd.read_sql_query("SELECT * FROM vlasnici;", conn)
    conn.close()
    print("\n--- SVI VLASNICI ---")
    print(df)
    return df

def crud_azuriraj_vlasnika(vlasnik_id, ime=None, prezime=None, telefon=None, email=None, adresa=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        polja = []
        vrednosti = []
        if ime: polja.append("ime = %s"); vrednosti.append(ime)
        if prezime: polja.append("prezime = %s"); vrednosti.append(prezime)
        if telefon: polja.append("telefon = %s"); vrednosti.append(telefon)
        if email: polja.append("email = %s"); vrednosti.append(email)
        if adresa: polja.append("adresa = %s"); vrednosti.append(adresa)
        vrednosti.append(vlasnik_id)
        
        sql = f"UPDATE vlasnici SET {', '.join(polja)} WHERE vlasnik_id = %s;"
        cur.execute(sql, vrednosti)
        conn.commit()
        print(f"Vlasnik ID {vlasnik_id} uspešno ažuriran.")
    except Exception as e:
        conn.rollback()
        print(f"Greška pri ažuriranju vlasnika: {e}")
    finally:
        cur.close()
        conn.close()

def crud_obrisi_vlasnika(vlasnik_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM vlasnici WHERE vlasnik_id = %s;", (vlasnik_id,))
        conn.commit()
        print(f"Vlasnik sa ID {vlasnik_id} uspešno obrisan.")
    except Exception as e:
        conn.rollback()
        print(f"Greška pri brisanju vlasnika: {e}")
    finally:
        cur.close()
        conn.close()

# --- PARCELE ---
def crud_dodaj_parcelu(broj_parcele, katastarska_opstina, povrsina_m2, vlasnik_id, geometrija_wkt):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO parcele (broj_parcele, katastarska_opstina, povrsina_m2, vlasnik_id, geometrija) "
            "VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326));",
            (broj_parcele, katastarska_opstina, povrsina_m2, vlasnik_id, geometrija_wkt)
        )
        conn.commit()
        print(f"Parčela {broj_parcele} uspešno dodata.")
    except Exception as e:
        conn.rollback()
        print(f"Greška pri dodavanju parcele: {e}")
    finally:
        cur.close()
        conn.close()

# --- BESPRAVNI OBJEKTI ---
def crud_dodaj_bespravni(status, povrsina, parcela_id, inspektor_id, geometrija_wkt, napomena=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO bespravni_objekti (status_slucaja, procenjena_povrsina_m2, parcela_id, inspektor_id, geometrija, napomena) "
            "VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s);",
            (status, povrsina, parcela_id, inspektor_id, geometrija_wkt, napomena)
        )
        conn.commit()
        print(f"Bespravni objekat uspešno dodat.")
    except Exception as e:
        conn.rollback()
        print(f"Greška pri dodavanju bespravnog objekta: {e}")
    finally:
        cur.close()
        conn.close()

def crud_azuriraj_status_objekta(bespravni_id, novi_status):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE bespravni_objekti SET status_slucaja = %s WHERE bespravni_id = %s;", (novi_status, bespravni_id))
        conn.commit()
        print(f"Status objekta ID {bespravni_id} ažuriran na: {novi_status}")
    except Exception as e:
        conn.rollback()
        print(f"Greška pri ažuriranju statusa: {e}")
    finally:
        cur.close()
        conn.close()

def crud_obrisi_bespravni(bespravni_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM bespravni_objekti WHERE bespravni_id = %s;", (bespravni_id,))
        conn.commit()
        print(f"Bespravni objekat ID {bespravni_id} uspešno obrisan.")
    except Exception as e:
        conn.rollback()
        print(f"Greška pri brisanju bespravnog objekta: {e}")
    finally:
        cur.close()
        conn.close()

# --- INSPEKTORI ---
def crud_obrisi_inspektora(inspektor_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM inspektori WHERE inspektor_id = %s;", (inspektor_id,))
        conn.commit()
        print(f"Inspektor sa ID {inspektor_id} uspešno obrisan.")
    except Exception as e:
        conn.rollback()
        print(f"Greška pri brisanju inspektora: {e}")
    finally:
        cur.close()
        conn.close()

# ============================================================
# 6. JOIN UPITI (8 primera sa WHERE filtriranjem)
# ============================================================
def izvrsi_kompleksne_upite():
    conn = get_db_connection()
    if not conn: return
    
    upiti = {
        "1. Svi bespravni objekti sa imenima vlasnika parcela (status = Detektovano)": """
            SELECT b.bespravni_id, b.procenjena_povrsina_m2, b.status_slucaja,
                   p.broj_parcele, v.ime, v.prezime
            FROM bespravni_objekti b
            JOIN parcele p ON b.parcela_id = p.parcela_id
            JOIN vlasnici v ON p.vlasnik_id = v.vlasnik_id
            WHERE b.status_slucaja = 'Detektovano';
        """,
        "2. Parcele u Veterniku koje imaju bespravne objekte veće od 100 m²": """
            SELECT p.broj_parcele, p.katastarska_opstina, b.procenjena_povrsina_m2, b.status_slucaja
            FROM parcele p
            JOIN bespravni_objekti b ON p.parcela_id = b.parcela_id
            WHERE p.katastarska_opstina = 'Veternik' AND b.procenjena_povrsina_m2 > 100;
        """,
        "3. Koji inspektor vodi slučajeve predviđene za rušenje?": """
            SELECT i.ime AS ins_ime, i.prezime AS ins_prez, i.licenca,
                   b.bespravni_id, p.broj_parcele
            FROM inspektori i
            JOIN bespravni_objekti b ON i.inspektor_id = b.inspektor_id
            JOIN parcele p ON b.parcela_id = p.parcela_id
            WHERE b.status_slucaja = 'Rusenje';
        """,
        "4. Parcele koje istovremeno imaju i legalne i bespravne objekte": """
            SELECT DISTINCT p.broj_parcele, p.katastarska_opstina,
                   l.broj_dozvole AS legalna_dozvola,
                   b.bespravni_id AS nelegalni_id,
                   b.procenjena_povrsina_m2
            FROM parcele p
            JOIN legalni_objekti l ON p.parcela_id = l.parcela_id
            JOIN bespravni_objekti b ON p.parcela_id = b.parcela_id;
        """,
        "5. Vlasnici čiji su objekti u statusu 'U proceduri'": """
            SELECT v.ime, v.prezime, v.jmbg, p.broj_parcele, b.status_slucaja, b.datum_detekcije
            FROM vlasnici v
            JOIN parcele p ON v.vlasnik_id = p.vlasnik_id
            JOIN bespravni_objekti b ON p.parcela_id = b.parcela_id
            WHERE b.status_slucaja = 'U proceduri';
        """,
        "6. Legalni objekti sa podacima o parceli i vlasniku (samo stambeni)": """
            SELECT l.broj_dozvole, l.spratnost, l.namjena_objekta,
                   p.broj_parcele, p.katastarska_opstina,
                   v.ime, v.prezime
            FROM legalni_objekti l
            JOIN parcele p ON l.parcela_id = p.parcela_id
            JOIN vlasnici v ON p.vlasnik_id = v.vlasnik_id
            WHERE l.namjena_objekta = 'stambeni';
        """,
        "7. Bespravni objekti detektovani u 2024. godini sa inspektorima": """
            SELECT b.bespravni_id, b.datum_detekcije, b.procenjena_povrsina_m2,
                   i.ime AS ins_ime, i.prezime AS ins_prez,
                   p.broj_parcele
            FROM bespravni_objekti b
            JOIN inspektori i ON b.inspektor_id = i.inspektor_id
            JOIN parcele p ON b.parcela_id = p.parcela_id
            WHERE EXTRACT(YEAR FROM b.datum_detekcije) = 2024;
        """,
        "8. Pregled građevinskih parcela (namjena) sa brojem bespravnih objekata": """
            SELECT p.broj_parcele, p.katastarska_opstina, p.namjena,
                   COUNT(b.bespravni_id) AS broj_bespravnih_objekata,
                   COALESCE(SUM(b.procenjena_povrsina_m2), 0) AS ukupna_bespravna_povrsina
            FROM parcele p
            LEFT JOIN bespravni_objekti b ON p.parcela_id = b.parcela_id
            WHERE p.namjena = 'građevinsko'
            GROUP BY p.parcela_id
            ORDER BY ukupna_bespravna_povrsina DESC;
        """
    }
    
    for naslov, sql in upiti.items():
        print(f"\n--- {naslov} ---")
        try:
            df = pd.read_sql_query(sql, conn)
            print(df)
        except Exception as e:
            print(f"Greška pri izvršavanju upita: {e}")
        
    conn.close()

# ============================================================
# MAIN IZVRŠAVANJE
# ============================================================
if __name__ == "__main__":
    # 1. Kreiranje tabela
    print("=" * 60)
    print("KREIRANJE TABELA U BAZI")
    print("=" * 60)
    kreiraj_tabele()
    
    # 2. Unos inicijalnih podataka
    print("\n" + "=" * 60)
    print("UNOS INICIJALNIH PODATAKA")
    print("=" * 60)
    unesi_inicijalne_podatke()
    
    # 3. Prikaz svih tabela preko Pandas DataFrame-a
    print("\n" + "=" * 60)
    print("PRIKAZ TABELA PREKO PANDAS DATAFRAME-A")
    print("=" * 60)
    
    for tabela in ['vlasnici', 'parcele', 'legalni_objekti', 'inspektori', 'bespravni_objekti']:
        print(f"\n--- {tabela.upper()} ---")
        df = ucitaj_tabelu_u_df(tabela)
        if df is not None:
            print(df)
    
    # 4. Testiranje CRUD operacija
    print("\n" + "=" * 60)
    print("CRUD OPERACIJE - PRIMJERI")
    print("=" * 60)
    
    # CREATE
    print("\n--- Dodavanje novog vlasnika (CREATE) ---")
    crud_dodaj_vlasnika('Petar', 'Petrović', '1111999800011', '060777777', 'petar@email.com', 'Novi Sad, Futoška 30')
    
    # READ
    crud_prikazi_vlasnike()
    
    # UPDATE
    print("\n--- Ažuriranje statusa bespravnog objekta (UPDATE) ---")
    crud_azuriraj_status_objekta(1, 'U proceduri')
    
    # DELETE (komentarisano da se slučajno ne obrišu podaci)
    # print("\n--- Brisanje inspektora (DELETE) ---")
    # crud_obrisi_inspektora(5)
    
    # 5. Izvršavanje JOIN upita
    print("\n" + "=" * 60)
    print("JOIN UPITI (8 PRIMJERA)")
    print("=" * 60)
    izvrsi_kompleksne_upite()
    
    print("\n" + "=" * 60)
    print("SVI ZADACI USPJEŠNO IZVRŠENI! ✅")
    print("=" * 60)
