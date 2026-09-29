from pathlib import Path
import pandas as pd


# Lokasi project Django
BASE_DIR = Path(__file__).resolve().parent.parent

# Folder data
DATA_DIR = BASE_DIR / "data"

print("=" * 70)
print("MEMBACA STRUKTUR DATA IPH")
print("=" * 70)


# Cari file Excel / CSV
supported_extensions = {".xlsx", ".xls", ".csv"}

files = [
    file
    for file in DATA_DIR.iterdir()
    if file.is_file()
    and file.suffix.lower() in supported_extensions
]

if not files:
    print("Tidak ada file Excel/CSV di folder data.")
    exit()


# Gunakan file pertama
file_path = files[0]

print(f"\nFile: {file_path.name}")


# ============================================================
# EXCEL
# ============================================================

if file_path.suffix.lower() in {".xlsx", ".xls"}:

    excel = pd.ExcelFile(file_path)

    print("\nSheet yang tersedia:")

    for number, sheet in enumerate(excel.sheet_names, start=1):
        print(f"{number}. {sheet}")

    # Untuk sementara gunakan sheet pertama
    sheet_name = excel.sheet_names[0]

    print(f"\nMembaca sheet: {sheet_name}")

    df = pd.read_excel(
        file_path,
        sheet_name=sheet_name
    )


# ============================================================
# CSV
# ============================================================

else:

    df = pd.read_csv(
        file_path,
        sep=None,
        engine="python",
        encoding="utf-8-sig"
    )


# ============================================================
# INFORMASI DATA
# ============================================================

print("\n" + "=" * 70)
print("INFORMASI DATA")
print("=" * 70)

print(f"Jumlah baris  : {len(df)}")
print(f"Jumlah kolom  : {len(df.columns)}")


print("\nKolom yang ditemukan:")

for number, column in enumerate(df.columns, start=1):
    print(f"{number}. {column}")


print("\n" + "=" * 70)
print("5 BARIS PERTAMA")
print("=" * 70)

print(df.head().to_string())


print("\n" + "=" * 70)
print("TIPE DATA")
print("=" * 70)

print(df.dtypes)