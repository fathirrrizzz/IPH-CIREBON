from pathlib import Path
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

print("=" * 70)
print("PEMBERSIHAN DATA IPH")
print("=" * 70)


# ------------------------------------------------------------
# Cari file Excel
# ------------------------------------------------------------

files = list(DATA_DIR.glob("*.xlsx")) + list(DATA_DIR.glob("*.xls"))

if not files:
    print("❌ File Excel tidak ditemukan.")
    exit()

file_path = files[0]

print(f"\nFile: {file_path.name}")


# ------------------------------------------------------------
# Baca sheet 360 KabKot
# ------------------------------------------------------------

df = pd.read_excel(
    file_path,
    sheet_name="360 KabKot"
)

print(f"Data awal : {len(df)} baris")


# ------------------------------------------------------------
# Ambil hanya kolom data utama
# ------------------------------------------------------------

columns = [
    "Kode Kabupaten/Kota",
    "Pulau",
    "Provinsi",
    "Kabupaten/Kota",
    "Perubahan IPH",
    "Komoditas Utama Penyumbang",
    "Upaya Pemda (Monev APP)",
    "Saran Kepada Pemda",
    "Fluktuasi Harga Tertinggi Minggu Berjalan",
    "Nilai CV (Nilai fluktuasi)",
    "Disparitas Harga antar Daerah",
    "status",
]

df = df[columns].copy()


# ------------------------------------------------------------
# Bersihkan kode kabupaten/kota
# ------------------------------------------------------------

df["Kode Kabupaten/Kota"] = (
    pd.to_numeric(
        df["Kode Kabupaten/Kota"],
        errors="coerce"
    )
)


# ------------------------------------------------------------
# Bersihkan kolom numerik
# ------------------------------------------------------------

numeric_columns = [
    "Perubahan IPH",
    "Nilai CV (Nilai fluktuasi)",
    "Disparitas Harga antar Daerah",
]

for column in numeric_columns:
    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )


# ------------------------------------------------------------
# Bersihkan teks
# ------------------------------------------------------------

text_columns = [
    "Pulau",
    "Provinsi",
    "Kabupaten/Kota",
    "Komoditas Utama Penyumbang",
    "Upaya Pemda (Monev APP)",
    "Saran Kepada Pemda",
    "Fluktuasi Harga Tertinggi Minggu Berjalan",
    "status",
]

for column in text_columns:
    df[column] = (
        df[column]
        .fillna("")
        .astype(str)
        .str.strip()
    )


# ------------------------------------------------------------
# Buang baris tanpa kabupaten/kota
# ------------------------------------------------------------

df = df[
    df["Kabupaten/Kota"].str.strip() != ""
].copy()


# ------------------------------------------------------------
# Tampilkan hasil
# ------------------------------------------------------------

print(f"Data setelah dibersihkan : {len(df)} baris")

print("\nKolom akhir:")

for number, column in enumerate(df.columns, start=1):
    print(f"{number}. {column}")


print("\n" + "=" * 70)
print("CONTOH DATA SETELAH DIBERSIHKAN")
print("=" * 70)

print(
    df.head(10).to_string(index=False)
)


print("\n" + "=" * 70)
print("JUMLAH DATA KOSONG")
print("=" * 70)

print(df.isna().sum())


# ------------------------------------------------------------
# Simpan hasil sementara
# ------------------------------------------------------------

output_file = DATA_DIR / "iph_clean.csv"

df.to_csv(
    output_file,
    index=False,
    encoding="utf-8-sig"
)

print("\n✅ Data bersih berhasil disimpan:")
print(output_file)