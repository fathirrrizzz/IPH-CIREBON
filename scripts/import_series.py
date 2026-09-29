from pathlib import Path
import sys
import os
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

from iph.models import Region, IPHSeries


# ============================================================
# KONFIGURASI
# ============================================================

FILE_PATH = BASE_DIR / "data" / "SERIES IPH-KABKOT JABAR.xlsx"
SHEET_NAME = "SERIES IPH"

TARGET_REGION_CODE = "3209"

# Jumlah minggu yang akan disimpan sebagai series terbaru
JUMLAH_MINGGU = 4


# ============================================================
# HELPER
# ============================================================

def clean_text(value):
    if pd.isna(value):
        return ""

    return str(value).strip()


def clean_name(value):
    return clean_text(value).upper()


def to_decimal(value):
    if pd.isna(value):
        return None

    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def month_to_number(month):
    """
    Mengubah nama bulan Excel menjadi angka.
    """

    months = {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MEI": 5,
        "JUN": 6,
        "JUL": 7,
        "AGU": 8,
        "AGS": 8,
        "SEP": 9,
        "OKT": 10,
        "NOV": 11,
        "DES": 12,
    }

    return months.get(
        clean_name(month)
    )


def week_to_number(value):
    """
    Mengubah M1, M2, M3, dst menjadi angka.
    """

    value = clean_name(value)

    if value.startswith("M"):

        try:
            return int(value[1:])
        except ValueError:
            return None

    return None


# ============================================================
# MULAI
# ============================================================

print("=" * 70)
print("IMPORT SERIES IPH KABUPATEN CIREBON")
print("=" * 70)

print(f"\nFile  : {FILE_PATH}")
print(f"Sheet : {SHEET_NAME}")


# ============================================================
# VALIDASI FILE
# ============================================================

if not FILE_PATH.exists():

    print("\n❌ File Excel tidak ditemukan.")

    sys.exit(1)


# ============================================================
# BACA EXCEL
# ============================================================

df = pd.read_excel(
    FILE_PATH,
    sheet_name=SHEET_NAME,
    header=None,
)

print(
    f"\nUkuran data: "
    f"{df.shape[0]} baris x {df.shape[1]} kolom"
)


# ============================================================
# CARI BARIS CIREBON
# ============================================================

cirebon_rows = []

for row_index in range(len(df)):

    for column_index in range(len(df.columns)):

        value = clean_name(
            df.iat[row_index, column_index]
        )

        if value == "CIREBON":

            cirebon_rows.append(
                (
                    row_index,
                    column_index,
                )
            )


print("\nLokasi CIREBON yang ditemukan:")

for row_index, column_index in cirebon_rows:

    print(
        f"- Excel baris {row_index + 1}, "
        f"kolom {column_index + 1}"
    )


# ============================================================
# TARGET BARIS
# ============================================================

TARGET_ROW = 13

if TARGET_ROW >= len(df):

    print("\n❌ Baris Cirebon tidak ditemukan.")

    sys.exit(1)


row = df.iloc[TARGET_ROW]


print("\nMenggunakan:")

print(
    f"Excel baris : {TARGET_ROW + 1}"
)

print(
    f"Python index: {TARGET_ROW}"
)


# ============================================================
# REGION DATABASE
# ============================================================

try:

    region = Region.objects.get(
        kode_kabkota=TARGET_REGION_CODE
    )

except Region.DoesNotExist:

    print(
        f"\n❌ Region "
        f"{TARGET_REGION_CODE} "
        f"tidak ditemukan."
    )

    sys.exit(1)


print("\nRegion database:")

print(
    f"Kode : {region.kode_kabkota}"
)

print(
    f"Nama : {region.nama}"
)


# ============================================================
# MEMBACA HEADER PERIODE
# ============================================================

print("\n" + "=" * 70)
print("MEMBACA PERIODE SERIES")
print("=" * 70)


series_data = []


# Tahun terakhir yang diketahui
current_year = 2025

# Bulan terakhir yang diketahui
current_month = None


# ------------------------------------------------------------
# PEMETAAN BULAN
# ------------------------------------------------------------

month_map = {
    "JAN": 1,
    "JANUARI": 1,

    "FEB": 2,
    "FEBRUARI": 2,

    "MAR": 3,
    "MARET": 3,

    "APR": 4,
    "APRIL": 4,

    "MEI": 5,

    "JUN": 6,
    "JUNI": 6,

    "JUL": 7,
    "JULI": 7,

    "AGU": 8,
    "AGS": 8,
    "AGUSTUS": 8,

    "SEP": 9,
    "SEPTEMBER": 9,

    "OKT": 10,
    "OKTOBER": 10,

    "NOV": 11,
    "NOVEMBER": 11,

    "DES": 12,
    "DESEMBER": 12,
}


# ------------------------------------------------------------
# BACA SETIAP KOLOM
# ------------------------------------------------------------

for column_index in range(2, len(df.columns)):

    # Ambil nilai header dari baris 0-11
    header_values = []

    for header_row in range(12):

        value = df.iat[
            header_row,
            column_index
        ]

        if not pd.isna(value):

            header_values.append(
                clean_text(value)
            )


    # --------------------------------------------------------
    # CEK TAHUN
    # --------------------------------------------------------

    for value in header_values:

        if value.isdigit():

            number = int(value)

            if 2000 <= number <= 2100:

                current_year = number


    # --------------------------------------------------------
    # CEK BULAN
    # --------------------------------------------------------

    detected_month = None

    for value in header_values:

        value_upper = value.upper()

        if value_upper in month_map:

            detected_month = month_map[
                value_upper
            ]

            break


    if detected_month is not None:

        current_month = detected_month


    # --------------------------------------------------------
    # CEK MINGGU
    # --------------------------------------------------------

    detected_week = None

    for value in header_values:

        value_upper = value.upper()

        if value_upper.startswith("M"):

            try:

                detected_week = int(
                    value_upper.replace("M", "")
                )

                break

            except ValueError:

                pass


    # --------------------------------------------------------
    # VALIDASI
    # --------------------------------------------------------

    if (
        current_year is None
        or current_month is None
        or detected_week is None
    ):

        continue


    # --------------------------------------------------------
    # NILAI IPH
    # --------------------------------------------------------

    nilai = to_decimal(
        row.iloc[column_index]
    )


    if nilai is None:

        continue


    series_data.append(
        {
            "tahun": current_year,
            "bulan": current_month,
            "minggu": detected_week,
            "nilai_iph": nilai,
            "kolom_excel": column_index,
        }
    )


# ============================================================
# KHUSUS VALIDASI BLOK TERAKHIR
# ============================================================

print("\nPeriode yang berhasil dibaca:")

for item in series_data[-10:]:

    print(
        f"Kolom {item['kolom_excel']} | "
        f"{item['tahun']} | "
        f"bulan {item['bulan']} | "
        f"M{item['minggu']} | "
        f"{item['nilai_iph']}"
    )


# ============================================================
# HAPUS DUPLIKAT PERIODE
# ============================================================

unique_series = {}

for item in series_data:

    key = (
        item["tahun"],
        item["bulan"],
        item["minggu"],
    )

    unique_series[key] = item


series_data = list(
    unique_series.values()
)


# ============================================================
# URUTKAN
# ============================================================

series_data.sort(
    key=lambda item: (
        item["tahun"],
        item["bulan"],
        item["minggu"],
    )
)


print(
    f"\nTotal periode valid ditemukan: "
    f"{len(series_data)}"
)


# ============================================================
# AMBIL 4 PERIODE TERBARU
# ============================================================

latest_series = series_data[
    -JUMLAH_MINGGU:
]


print("\n" + "=" * 70)
print("4 MINGGU TERBARU")
print("=" * 70)


for item in latest_series:

    print(
        f"{item['tahun']} - "
        f"bulan {item['bulan']} - "
        f"M{item['minggu']} : "
        f"{item['nilai_iph']}"
    )


# ============================================================
# VALIDASI 4 MINGGU
# ============================================================

if len(latest_series) < JUMLAH_MINGGU:

    print(
        "\n❌ Data valid kurang dari "
        f"{JUMLAH_MINGGU} minggu."
    )

    sys.exit(1)


# ============================================================
# HAPUS DUPLIKAT PERIODE
# ============================================================

unique_series = {}

for item in series_data:

    key = (
        item["tahun"],
        item["bulan"],
        item["minggu"],
    )

    unique_series[key] = item


series_data = list(
    unique_series.values()
)


# ============================================================
# URUTKAN PERIODE
# ============================================================

series_data.sort(
    key=lambda item: (
        item["tahun"],
        item["bulan"],
        item["minggu"],
    )
)


print(
    f"\nTotal periode valid ditemukan: "
    f"{len(series_data)}"
)


# ============================================================
# AMBIL 4 PERIODE TERBARU
# ============================================================

latest_series = series_data[
    -JUMLAH_MINGGU:
]


print("\n" + "=" * 70)
print("4 MINGGU TERBARU")
print("=" * 70)


for item in latest_series:

    print(
        f"{item['tahun']} - "
        f"bulan {item['bulan']} - "
        f"M{item['minggu']} : "
        f"{item['nilai_iph']}"
    )


# ============================================================
# VALIDASI
# ============================================================

if len(latest_series) < JUMLAH_MINGGU:

    print(
        "\n❌ Data valid kurang dari "
        f"{JUMLAH_MINGGU} minggu."
    )

    sys.exit(1)


# ============================================================
# SIMPAN KE DATABASE
# ============================================================

print("\n" + "=" * 70)
print("MENYIMPAN KE DATABASE")
print("=" * 70)


jumlah_baru = 0
jumlah_update = 0


for item in latest_series:

    obj, created = IPHSeries.objects.update_or_create(

        region=region,

        tahun=item["tahun"],

        bulan=item["bulan"],

        minggu=item["minggu"],

        defaults={
            "nilai_iph": item["nilai_iph"],
        },
    )

    if created:

        jumlah_baru += 1

        print(
            f"✓ INSERT "
            f"{item['tahun']} "
            f"M{item['minggu']} "
            f"= {item['nilai_iph']}"
        )

    else:

        jumlah_update += 1

        print(
            f"↻ UPDATE "
            f"{item['tahun']} "
            f"M{item['minggu']} "
            f"= {item['nilai_iph']}"
        )


# ============================================================
# SELESAI
# ============================================================

print("\n" + "=" * 70)
print("IMPORT SERIES SELESAI")
print("=" * 70)

print(
    f"\nData baru   : {jumlah_baru}"
)

print(
    f"Data update : {jumlah_update}"
)

print(
    f"Total series Cirebon di database: "
    f"{IPHSeries.objects.filter(region=region).count()}"
)