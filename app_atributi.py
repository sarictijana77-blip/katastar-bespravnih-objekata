import pandas as pd
import psycopg2
from sqlalchemy import create_engine

# ============================================================
# PODEŠAVANJA
# ============================================================

DB_HOST = "localhost"
DB_NAME = "katastar_db"
DB_USER = "postgres"
DB_PASSWORD = "admin"   # ako tvoja šifra nije admin, promeni ovde
DB_PORT = "5432"

DOZVOLJENI_STATUSI = [
    "Kandidat - bespravni objekat",
    "Podudara se sa legalnim objektom",
    "U proceduri",
    "Potvrđeno bespravno",
    "Odbačeno - lažna detekcija",
    "Rušenje"
]


def get_db_connection():
    try:
        return psycopg2.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER,
            password=DB_PASSWORD, port=DB_PORT
        )
    except Exception as e:
        print(f"Greška pri povezivanju na bazu: {e}")
        return None


def napravi_engine():
    url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)


# ============================================================
# PRIKAZ (READ)
# ============================================================

def prikazi_sve_detekcije():
    engine = napravi_engine()
    sql = """
        SELECT detekcija_id, status_slucaja, procenjena_povrsina_m2,
               datum_detekcije, confidence, parcela_id, inspektor_id, napomena
        FROM detektovani_objekti_ml
        ORDER BY detekcija_id;
    """
    df = pd.read_sql_query(sql, engine)
    if df.empty:
        print("Nema detekcija u bazi.")
    else:
        print(df.to_string(index=False))
    return df


def prikazi_detekcije_po_statusu(status):
    engine = napravi_engine()
    sql = """
        SELECT detekcija_id, status_slucaja, procenjena_povrsina_m2,
               datum_detekcije, confidence, parcela_id, inspektor_id
        FROM detektovani_objekti_ml
        WHERE status_slucaja = %s
        ORDER BY detekcija_id;
    """
    df = pd.read_sql_query(sql, engine, params=(status,))
    if df.empty:
        print(f"Nema detekcija sa statusom '{status}'.")
    else:
        print(df.to_string(index=False))
    return df


def prikazi_jednu_detekciju(detekcija_id):
    engine = napravi_engine()
    sql = """
        SELECT d.*, p.broj_parcele, p.katastarska_opstina,
               i.ime AS inspektor_ime, i.prezime AS inspektor_prezime
        FROM detektovani_objekti_ml d
        LEFT JOIN parcele p ON d.parcela_id = p.parcela_id
        LEFT JOIN inspektori i ON d.inspektor_id = i.inspektor_id
        WHERE d.detekcija_id = %s;
    """
    df = pd.read_sql_query(sql, engine, params=(detekcija_id,))
    if df.empty:
        print(f"Detekcija sa ID {detekcija_id} ne postoji.")
    else:
        print(df.drop(columns=["geometrija"], errors="ignore").T)
    return df


def prikazi_inspektore():
    engine = napravi_engine()
    df = pd.read_sql_query(
        "SELECT inspektor_id, ime, prezime, oblast_rada FROM inspektori;", engine
    )
    print(df.to_string(index=False))
    return df


def prikazi_statistiku():
    engine = napravi_engine()
    sql = """
        SELECT status_slucaja, COUNT(*) AS broj,
               COALESCE(SUM(procenjena_povrsina_m2), 0) AS ukupna_povrsina_m2
        FROM detektovani_objekti_ml
        GROUP BY status_slucaja
        ORDER BY broj DESC;
    """
    df = pd.read_sql_query(sql, engine)
    if df.empty:
        print("Nema podataka za statistiku.")
    else:
        print(df.to_string(index=False))
    return df


# ============================================================
# IZMENA ATRIBUTA (UPDATE)
# ============================================================

def detekcija_postoji(cur, detekcija_id):
    cur.execute("SELECT 1 FROM detektovani_objekti_ml WHERE detekcija_id = %s;", (detekcija_id,))
    return cur.fetchone() is not None


def promeni_status(detekcija_id, novi_status):
    if novi_status not in DOZVOLJENI_STATUSI:
        print(f"Nepoznat status. Dozvoljeni statusi:")
        for s in DOZVOLJENI_STATUSI:
            print(f"  - {s}")
        return

    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        if not detekcija_postoji(cur, detekcija_id):
            print(f"Detekcija sa ID {detekcija_id} ne postoji.")
            return

        cur.execute(
            "UPDATE detektovani_objekti_ml SET status_slucaja = %s WHERE detekcija_id = %s;",
            (novi_status, detekcija_id)
        )
        conn.commit()
        print(f"Status detekcije {detekcija_id} promenjen na '{novi_status}'.")
    except Exception as e:
        conn.rollback()
        print(f"Greška: {e}")
    finally:
        cur.close()
        conn.close()


def promeni_napomenu(detekcija_id, nova_napomena):
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        if not detekcija_postoji(cur, detekcija_id):
            print(f"Detekcija sa ID {detekcija_id} ne postoji.")
            return

        cur.execute(
            "UPDATE detektovani_objekti_ml SET napomena = %s WHERE detekcija_id = %s;",
            (nova_napomena, detekcija_id)
        )
        conn.commit()
        print(f"Napomena detekcije {detekcija_id} ažurirana.")
    except Exception as e:
        conn.rollback()
        print(f"Greška: {e}")
    finally:
        cur.close()
        conn.close()


def dodeli_inspektora(detekcija_id, inspektor_id):
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        if not detekcija_postoji(cur, detekcija_id):
            print(f"Detekcija sa ID {detekcija_id} ne postoji.")
            return

        cur.execute("SELECT 1 FROM inspektori WHERE inspektor_id = %s;", (inspektor_id,))
        if cur.fetchone() is None:
            print(f"Inspektor sa ID {inspektor_id} ne postoji.")
            return

        cur.execute(
            "UPDATE detektovani_objekti_ml SET inspektor_id = %s WHERE detekcija_id = %s;",
            (inspektor_id, detekcija_id)
        )
        conn.commit()
        print(f"Inspektor {inspektor_id} dodeljen detekciji {detekcija_id}.")
    except Exception as e:
        conn.rollback()
        print(f"Greška: {e}")
    finally:
        cur.close()
        conn.close()


# ============================================================
# BRISANJE (DELETE)
# ============================================================

def obrisi_detekciju(detekcija_id):
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        if not detekcija_postoji(cur, detekcija_id):
            print(f"Detekcija sa ID {detekcija_id} ne postoji.")
            return

        cur.execute("DELETE FROM detektovani_objekti_ml WHERE detekcija_id = %s;", (detekcija_id,))
        conn.commit()
        print(f"Detekcija {detekcija_id} obrisana.")
    except Exception as e:
        conn.rollback()
        print(f"Greška: {e}")
    finally:
        cur.close()
        conn.close()


# ============================================================
# UNOS SA PROVEROM (da aplikacija ne puca na loš unos)
# ============================================================

def unesi_broj(poruka):
    while True:
        vrednost = input(poruka).strip()
        try:
            return int(vrednost)
        except ValueError:
            print("Molim unesi ceo broj.")


def izaberi_status():
    print("\nDostupni statusi:")
    for i, s in enumerate(DOZVOLJENI_STATUSI, start=1):
        print(f"  {i}. {s}")
    while True:
        izbor = input("Izaberi broj statusa: ").strip()
        try:
            idx = int(izbor)
            if 1 <= idx <= len(DOZVOLJENI_STATUSI):
                return DOZVOLJENI_STATUSI[idx - 1]
        except ValueError:
            pass
        print("Nevažeći izbor, pokušaj ponovo.")


# ============================================================
# MENI
# ============================================================

def prikazi_meni():
    print("\n" + "=" * 60)
    print("APLIKACIJA ZA UPRAVLJANJE ML DETEKCIJAMA")
    print("=" * 60)
    print("1. Prikaži sve detekcije")
    print("2. Prikaži detekcije po statusu")
    print("3. Prikaži jednu detekciju (detalji)")
    print("4. Promeni status slučaja")
    print("5. Promeni napomenu")
    print("6. Dodeli/promeni inspektora")
    print("7. Obriši detekciju")
    print("8. Prikaži listu inspektora")
    print("9. Prikaži statistiku po statusima")
    print("0. Izlaz")


def main():
    while True:
        prikazi_meni()
        izbor = input("\nIzaberi opciju: ").strip()

        if izbor == "1":
            prikazi_sve_detekcije()

        elif izbor == "2":
            status = izaberi_status()
            prikazi_detekcije_po_statusu(status)

        elif izbor == "3":
            did = unesi_broj("Unesi ID detekcije: ")
            prikazi_jednu_detekciju(did)

        elif izbor == "4":
            did = unesi_broj("Unesi ID detekcije: ")
            novi = izaberi_status()
            promeni_status(did, novi)

        elif izbor == "5":
            did = unesi_broj("Unesi ID detekcije: ")
            napomena = input("Unesi novu napomenu: ").strip()
            promeni_napomenu(did, napomena)

        elif izbor == "6":
            prikazi_inspektore()
            did = unesi_broj("Unesi ID detekcije: ")
            iid = unesi_broj("Unesi ID inspektora: ")
            dodeli_inspektora(did, iid)

        elif izbor == "7":
            did = unesi_broj("Unesi ID detekcije za brisanje: ")
            potvrda = input(f"Sigurno želiš da obrišeš detekciju {did}? (da/ne): ").strip().lower()
            if potvrda == "da":
                obrisi_detekciju(did)
            else:
                print("Brisanje otkazano.")

        elif izbor == "8":
            prikazi_inspektore()

        elif izbor == "9":
            prikazi_statistiku()

        elif izbor == "0":
            print("Izlaz iz aplikacije.")
            break

        else:
            print("Nepoznata opcija, pokušaj ponovo.")


if __name__ == "__main__":
    main()