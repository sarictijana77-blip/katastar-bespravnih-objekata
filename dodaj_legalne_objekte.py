import psycopg2

DB_HOST = "localhost"
DB_NAME = "katastar_db"
DB_USER = "postgres"
DB_PASSWORD = "admin"   # zameni ako treba
DB_PORT = "5432"

BROJ_PRIMERA = 115  # koliko detekcija "pretvaramo" u legalne objekte


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, database=DB_NAME, user=DB_USER,
        password=DB_PASSWORD, port=DB_PORT
    )


def main():
    conn = get_conn()
    cur = conn.cursor()

    # 1. Uzmi par stvarnih ML detekcija (najveće po površini = verovatnije prave kuće, ne šum)
    cur.execute("""
        SELECT detekcija_id, procenjena_povrsina_m2, ST_AsText(geometrija)
        FROM detektovani_objekti_ml
        ORDER BY procenjena_povrsina_m2 DESC
        LIMIT %s;
    """, (BROJ_PRIMERA,))
    detekcije = cur.fetchall()

    if not detekcije:
        print("Nema detekcija u bazi — prvo pokreni ml_detekcija.py")
        return

    # 2. Napravi jednog test-vlasnika za ove objekte
    cur.execute("""
        INSERT INTO vlasnici (ime, prezime, jmbg, telefon, email, adresa)
        VALUES ('Ivana', 'Ivić', '0101985800099', '064123123', 'ivana@email.com', 'Novi Sad, Adica')
        ON CONFLICT (jmbg) DO NOTHING
        RETURNING vlasnik_id;
    """)
    row = cur.fetchone()
    if row:
        vlasnik_id = row[0]
    else:
        cur.execute("SELECT vlasnik_id FROM vlasnici WHERE jmbg = '0101985800099';")
        vlasnik_id = cur.fetchone()[0]

    uspesno = 0

    for i, (det_id, povrsina, wkt) in enumerate(detekcije, start=1):
        try:
            # 3. Napravi parcelu koja "sadrži" baš taj objekat (mali buffer od 3m oko njega)
            # ST_Dump + ORDER BY povrsina + LIMIT 1 garantuje da uvek dobijemo
            # jedan pojedinačni Polygon, čak i ako bafer slučajno napravi MultiPolygon.
            cur.execute("""
                WITH buff AS (
                    SELECT ST_Buffer(ST_GeomFromText(%s, 4326)::geography, 3)::geometry AS geom
                ),
                delovi AS (
                    SELECT (ST_Dump(geom)).geom AS deo
                    FROM buff
                )
                INSERT INTO parcele (broj_parcele, katastarska_opstina, povrsina_m2, namjena, vlasnik_id, geometrija)
                SELECT %s, 'Adica', %s, 'građevinsko', %s, deo
                FROM delovi
                ORDER BY ST_Area(deo) DESC
                LIMIT 1
                RETURNING parcela_id;
            """, (wkt, f"ADICA-TEST-{i}", povrsina, vlasnik_id))
            parcela_id = cur.fetchone()[0]

            # 4. Napravi legalni objekat sa ISTOM geometrijom kao ta detekcija
            # Isto osiguranje i ovde, za svaki slučaj da wkt nije čist Polygon.
            cur.execute("""
                WITH delovi AS (
                    SELECT (ST_Dump(ST_GeomFromText(%s, 4326))).geom AS deo
                )
                INSERT INTO legalni_objekti (broj_dozvole, spratnost, godina_izgradnje, namjena_objekta, parcela_id, geometrija)
                SELECT %s, 'P+1', 2019, 'stambeni', %s, deo
                FROM delovi
                ORDER BY ST_Area(deo) DESC
                LIMIT 1;
            """, (wkt, f"ROP-ADICA-TEST-{i}", parcela_id))

            uspesno += 1
            print(f"[{i}/{len(detekcije)}] Dodat legalni objekat za detekciju {det_id} (parcela_id={parcela_id})")

        except Exception as e:
            conn.rollback()
            print(f"[{i}/{len(detekcije)}] Preskočena detekcija {det_id} zbog greške: {e}")
            continue

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nGotovo! Uspešno dodato {uspesno} od {len(detekcije)} legalnih objekata.")
    print("Sad ponovo pokreni ml_detekcija.py da vidiš mešovite rezultate.")


if __name__ == "__main__":
    main()