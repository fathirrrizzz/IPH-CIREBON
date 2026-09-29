from pathlib import Path
import sys
import os
import re
from decimal import Decimal, InvalidOperation

import pandas as pd


# ============================================================
# SETUP DJANGO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

import django

django.setup()


from iph.models import (
    Region,
    ReportPeriod,
    ImportBatch,
    Commodity,
    WeeklyIPH,
    CommodityContribution,
)


# ============================================================
# KONFIGURASI
# ============================================================

DATA_DIR = BASE_DIR / "data"

SHEET_NAME = "360 KabKot"


# ============================================================
# HELPER
# ============================================================

def clean_text(value):
    """
    Mengubah nilai kosong/NaN menjadi string kosong.
    """
    if pd.isna(value):
        return ""

    return str(value).strip()


def to_decimal(value):
    """
    Mengubah angka Pandas menjadi Decimal.
    """
    if pd.isna(value) or value == "":
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def normalize_commodity_name(name):
    """
    Normalisasi nama komoditas.
    """
    name = clean_text(name)

    name = re.sub(r"\s+", " ", name)

    return name.strip().upper()


def parse_status(value):
    """
    Mengubah status Excel menjadi:
    naik / turun / stabil
    """

    value = clean_text(value).lower()

    if "naik" in value:
        return "naik"

    if "turun" in value:
        return "turun"

    if "stabil" in value:
        return "stabil"

    return ""


def parse_contributions(value):
    """
    Membaca kolom:

    Komoditas Utama Penyumbang

    Contoh:

    Cabai Merah(8,177),
    Cabai Rawit(0,9237),
    Bawang Putih(0,1469)

    Menghasilkan:

    [
        ("Cabai Merah", 8.177),
        ("Cabai Rawit", 0.9237),
        ("Bawang Putih", 0.1469),
    ]
    """

    value = clean_text(value)

    if not value:
        return []

    pattern = r"(.+?)\s*\(\s*([-+]?\d+(?:[,.]\d+)?)\s*\)"

    matches = re.findall(pattern, value)

    result = []

    for commodity_name, contribution in matches:

        commodity_name = commodity_name.strip()

        contribution = contribution.replace(",", ".")

        try:
            contribution = Decimal(contribution)
        except InvalidOperation:
            continue

        result.append(
            (
                commodity_name,
                contribution,
            )
        )

    return result


# ============================================================
# CARI FILE EXCEL
# ============================================================

files = list(DATA_DIR.glob("*.xlsx"))

if not files:
    print("❌ Tidak ditemukan file .xlsx di folder data.")

    print(f"Folder: {DATA_DIR}")

    sys.exit(1)


print("=" * 70)
print("IMPORT DATA IPH KE DATABASE")
print("=" * 70)

print()

print("File Excel yang ditemukan:")

for number, file in enumerate(files, start=1):
    print(f"{number}. {file.name}")


# Untuk sekarang gunakan file pertama
file_path = files[0]

print()
print(f"File yang digunakan : {file_path.name}")
print(f"Sheet                : {SHEET_NAME}")


# ============================================================
# BACA EXCEL
# ============================================================

try:

    df = pd.read_excel(
        file_path,
        sheet_name=SHEET_NAME,
    )

except Exception as error:

    print()
    print("❌ Gagal membaca Excel.")
    print(f"Error: {error}")

    sys.exit(1)


print()
print(f"Jumlah baris Excel : {len(df)}")
print(f"Jumlah kolom       : {len(df.columns)}")


# ============================================================
# VALIDASI KOLOM
# ============================================================

required_columns = [
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


missing_columns = [
    column
    for column in required_columns
    if column not in df.columns
]


if missing_columns:

    print()
    print("❌ Kolom berikut tidak ditemukan:")

    for column in missing_columns:
        print(f"- {column}")

    sys.exit(1)


print()
print("✅ Semua kolom utama ditemukan.")


# ============================================================
# REPORT PERIOD
# ============================================================

# Karena file yang digunakan adalah:
# M4 Juli 2026

period, created = ReportPeriod.objects.get_or_create(
    tahun=2026,
    minggu=4,
    defaults={
        "bulan": 7,
        "tanggal_awal": None,
        "tanggal_akhir": None,
        "label": "M4 Juli 2026",
    },
)

print()
print("Report Period:")
print(f"- {period.label}")


# ============================================================
# IMPORT BATCH
# ============================================================

import_batch = ImportBatch.objects.create(
    nama_file=file_path.name,
    sheet_name=SHEET_NAME,
    jumlah_baris=len(df),
    status="proses",
)


print()
print("Import Batch dibuat:")
print(f"- ID     : {import_batch.id}")
print(f"- Status : {import_batch.status}")


# ============================================================
# PROSES DATA
# ============================================================

region_count = 0
weekly_count = 0
commodity_count = 0
contribution_count = 0


try:

    for index, row in df.iterrows():

        # ----------------------------------------------------
        # REGION
        # ----------------------------------------------------

        kode = clean_text(row["Kode Kabupaten/Kota"])

        nama = clean_text(row["Kabupaten/Kota"])

        provinsi = clean_text(row["Provinsi"])

        pulau = clean_text(row["Pulau"])


        if not kode or not nama:
            continue


        region, created = Region.objects.get_or_create(
            kode_kabkota=kode,
            defaults={
                "nama": nama,
                "provinsi": provinsi,
                "pulau": pulau,
            },
        )


        if created:
            region_count += 1

        else:

            # Update informasi wilayah
            region.nama = nama
            region.provinsi = provinsi
            region.pulau = pulau
            region.save()


        # ----------------------------------------------------
        # WEEKLY IPH
        # ----------------------------------------------------

        perubahan_iph = to_decimal(
            row["Perubahan IPH"]
        )

        fluktuasi_tertinggi = clean_text(
            row["Fluktuasi Harga Tertinggi Minggu Berjalan"]
        )

        nilai_cv = to_decimal(
            row["Nilai CV (Nilai fluktuasi)"]
        )

        disparitas_harga = to_decimal(
            row["Disparitas Harga antar Daerah"]
        )

        status = parse_status(
            row["status"]
        )

        upaya_pemda = clean_text(
            row["Upaya Pemda (Monev APP)"]
        )

        saran_pemda = clean_text(
            row["Saran Kepada Pemda"]
        )


        if perubahan_iph is None:
            perubahan_iph = Decimal("0")


        weekly, created = WeeklyIPH.objects.update_or_create(

            region=region,

            period=period,

            defaults={
                "perubahan_iph": perubahan_iph,
                "fluktuasi_tertinggi": fluktuasi_tertinggi,
                "nilai_cv": nilai_cv,
                "disparitas_harga": disparitas_harga,
                "status": status,
                "upaya_pemda": upaya_pemda,
                "saran_pemda": saran_pemda,
                "import_batch": import_batch,
            },
        )


        if created:
            weekly_count += 1


        # ----------------------------------------------------
        # KOMODITAS + KONTRIBUSI
        # ----------------------------------------------------

        contributions = parse_contributions(
            row["Komoditas Utama Penyumbang"]
        )


        for commodity_name, nilai_andil in contributions:

            normalized = normalize_commodity_name(
                commodity_name
            )


            if not normalized:
                continue


            commodity, created = Commodity.objects.get_or_create(

                nama_normalized=normalized,

                defaults={
                    "nama": commodity_name,
                },
            )


            if created:
                commodity_count += 1


            CommodityContribution.objects.update_or_create(

                weekly_iph=weekly,

                commodity=commodity,

                defaults={
                    "nilai_andil": nilai_andil,
                },
            )

            contribution_count += 1


        # ----------------------------------------------------
        # PROGRESS
        # ----------------------------------------------------

        if (index + 1) % 50 == 0:

            print(
                f"Progress: {index + 1}/{len(df)} baris"
            )


    # ========================================================
    # BERHASIL
    # ========================================================

    import_batch.status = "berhasil"

    import_batch.save()


    print()
    print("=" * 70)
    print("IMPORT BERHASIL")
    print("=" * 70)

    print(f"Region baru              : {region_count}")
    print(f"Weekly IPH baru          : {weekly_count}")
    print(f"Commodity baru           : {commodity_count}")
    print(f"Commodity contribution   : {contribution_count}")
    print()

    print("Status ImportBatch: berhasil")


except Exception as error:

    import_batch.status = "gagal"

    import_batch.pesan_error = str(error)

    import_batch.save()

    print()
    print("=" * 70)
    print("❌ IMPORT GAGAL")
    print("=" * 70)

    print(error)

    raise