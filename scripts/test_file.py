from pathlib import Path
import pandas as pd


# ============================================================
# KONFIGURASI
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

KODE_CIREBON = "3209"


# ============================================================
# FUNGSI MEMBERSIHKAN NILAI
# ============================================================

def clean_value(value):
    if pd.isna(value):
        return ""

    value = str(value).strip()

    # 3209.0 → 3209
    if value.endswith(".0"):
        value = value[:-2]

    return value


# ============================================================
# FUNGSI MENCARI KOLOM KODE
# ============================================================

def find_code_column(columns):

    for column in columns:

        nama = str(column).strip().lower()

        if "kode kabupaten/kota" in nama:
            return column

        if "kode kabupaten kota" in nama:
            return column

        if "kode kabkot" in nama:
            return column

        if "kode kab/kota" in nama:
            return column

    return None


# ============================================================
# FUNGSI MENCARI DATA CIREBON
# ============================================================

def find_cirebon(df, sumber):

    print()
    print("-" * 60)
    print(f"Menganalisis: {sumber}")
    print("-" * 60)

    if df.empty:
        print("⚠ Data kosong.")
        return None

    print(f"Jumlah baris : {len(df)}")
    print(f"Jumlah kolom : {len(df.columns)}")

    # Cari kolom kode
    code_column = find_code_column(df.columns)

    if code_column is None:

        print("❌ Kolom 'Kode Kabupaten/Kota' tidak ditemukan.")

        print("\nKolom yang tersedia:")

        for column in df.columns:
            print(f"  - {column}")

        return None

    print(f"✓ Kolom kode ditemukan: {code_column}")

    # Bersihkan kode
    kode_data = df[code_column].apply(clean_value)

    # Cari kode 3209
    hasil = df[kode_data == KODE_CIREBON].copy()

    if hasil.empty:

        print(f"❌ Kode {KODE_CIREBON} tidak ditemukan.")

        return None

    print()
    print(f"✓ Kode {KODE_CIREBON} ditemukan!")

    print()
    print("=" * 60)
    print("DATA KABUPATEN CIREBON")
    print("=" * 60)

    print(hasil.to_string(index=False))

    return hasil


# ============================================================
# PROGRAM UTAMA
# ============================================================

print("=" * 60)
print("IMPORTER DATA IPH")
print("=" * 60)


# ============================================================
# CEK FOLDER DATA
# ============================================================

if not DATA_DIR.exists():

    print("❌ Folder data tidak ditemukan.")

    print(f"Lokasi yang dicari:")
    print(DATA_DIR)

    exit()


# ============================================================
# CARI FILE EXCEL / CSV
# ============================================================

supported_extensions = {
    ".xlsx",
    ".xls",
    ".csv",
}

files = [
    file
    for file in DATA_DIR.iterdir()
    if file.is_file()
    and file.suffix.lower() in supported_extensions
]


if not files:

    print("❌ Tidak ada file Excel/CSV di folder data.")

    exit()


# ============================================================
# TAMPILKAN FILE
# ============================================================

print()
print("File yang ditemukan:")

for nomor, file in enumerate(files, start=1):

    print(f"{nomor}. {file.name}")


# ============================================================
# PILIH FILE PERTAMA
# ============================================================

file_path = files[0]

print()
print("=" * 60)
print("FILE YANG AKAN DIBACA")
print("=" * 60)

print(file_path.name)


# ============================================================
# JIKA EXCEL
# ============================================================

if file_path.suffix.lower() in {".xlsx", ".xls"}:

    print()
    print("Format: EXCEL")

    try:

        excel = pd.ExcelFile(file_path)

        print()
        print("Sheet yang ditemukan:")

        for sheet in excel.sheet_names:
            print(f"  - {sheet}")

    except Exception as error:

        print()
        print("❌ Gagal membaca file Excel.")
        print(f"Error: {error}")

        exit()


    # ========================================================
    # TENTUKAN SHEET YANG DIPRIORITASKAN
    # ========================================================

    preferred_sheets = []

    for sheet in excel.sheet_names:

        sheet_clean = (
            str(sheet)
            .lower()
            .replace(" ", "")
            .replace("_", "")
        )

        if (
            "360kab" in sheet_clean
            or "kabkot" in sheet_clean
            or "kabkota" in sheet_clean
            or "kabupaten" in sheet_clean
        ):

            preferred_sheets.append(sheet)


    # ========================================================
    # JIKA SHEET KAB/KOTA DITEMUKAN
    # ========================================================

    if preferred_sheets:

        sheets_to_check = preferred_sheets

        print()
        print("Sheet Kab/Kota yang akan diperiksa:")

        for sheet in sheets_to_check:
            print(f"  ✓ {sheet}")

    else:

        sheets_to_check = excel.sheet_names

        print()
        print("⚠ Sheet Kab/Kota tidak terdeteksi.")

        print("Semua sheet akan diperiksa.")


    # ========================================================
    # PERIKSA SHEET
    # ========================================================

    ditemukan = False

    for sheet in sheets_to_check:

        try:

            df = pd.read_excel(
                file_path,
                sheet_name=sheet
            )

            hasil = find_cirebon(
                df,
                f"{file_path.name} → {sheet}"
            )

            if hasil is not None:

                ditemukan = True

                # Berhenti setelah Cirebon ditemukan
                break

        except Exception as error:

            print()
            print(f"❌ Gagal membaca sheet: {sheet}")
            print(f"Error: {error}")


    if not ditemukan:

        print()
        print("=" * 60)
        print("❌ DATA 3209 TIDAK DITEMUKAN")
        print("=" * 60)


# ============================================================
# JIKA CSV
# ============================================================

elif file_path.suffix.lower() == ".csv":

    print()
    print("Format: CSV")

    try:

        df = pd.read_csv(
            file_path,
            sep=None,
            engine="python",
            encoding="utf-8-sig"
        )

    except UnicodeDecodeError:

        print()
        print("⚠ UTF-8 gagal.")
        print("Mencoba encoding latin-1...")

        try:

            df = pd.read_csv(
                file_path,
                sep=None,
                engine="python",
                encoding="latin-1"
            )

        except Exception as error:

            print()
            print("❌ Gagal membaca CSV.")
            print(f"Error: {error}")

            exit()

    except Exception as error:

        print()
        print("❌ Gagal membaca CSV.")
        print(f"Error: {error}")

        exit()


    # Cari Cirebon
    hasil = find_cirebon(
        df,
        file_path.name
    )

    if hasil is None:

        print()
        print("=" * 60)
        print("❌ DATA 3209 TIDAK DITEMUKAN")
        print("=" * 60)


# ============================================================
# SELESAI
# ============================================================

print()
print("=" * 60)
print("PROGRAM SELESAI")
print("=" * 60)