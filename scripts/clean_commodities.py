from pathlib import Path
import sys
import os

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

from iph.models import Commodity


# ============================================================
# NORMALISASI NAMA
# ============================================================

def clean_name(name):
    name = str(name).strip()

    # Hapus koma di awal nama
    name = name.lstrip(",")

    # Rapikan spasi
    name = " ".join(name.split())

    # Standarisasi nama komoditas
    name_upper = name.upper()

    if "IKAN KEMBUNG" in name_upper:
       return "Ikan Kembung"

    if name_upper == "UDANG BASAH":
       return "Udang"

    if name_upper == "MIE KERING INSTANT":
       return "Mie Instan"

    if name_upper == "SUSU BUBUK":
       return "Susu Bubuk"

    return name.strip()


# ============================================================
# PROSES
# ============================================================

print("=" * 70)
print("MEMBERSIHKAN DATA COMMODITY")
print("=" * 70)

commodities = list(
    Commodity.objects.all().order_by("id")
)

for commodity in commodities:

    nama_bersih = clean_name(
        commodity.nama
    )

    normalized_bersih = nama_bersih.upper()

    # Cari commodity lain dengan nama normalized yang sama
    sudah_ada = (
        Commodity.objects
        .filter(
            nama_normalized=normalized_bersih
        )
        .exclude(
            id=commodity.id
        )
        .first()
    )

    if sudah_ada:

        print(
            f"Hapus duplikat: "
            f"'{commodity.nama}' "
            f"-> gunakan ID {sudah_ada.id}"
        )

        # Pindahkan contribution ke commodity yang benar
        commodity.contributions.update(
            commodity=sudah_ada
        )

        commodity.delete()

    else:

        if (
            commodity.nama != nama_bersih
            or commodity.nama_normalized != normalized_bersih
        ):

            print(
                f"Perbaiki: "
                f"'{commodity.nama}' "
                f"-> '{nama_bersih}'"
            )

            commodity.nama = nama_bersih
            commodity.nama_normalized = normalized_bersih

            commodity.save()


print()
print("=" * 70)
print("PEMBERSIHAN SELESAI")
print("=" * 70)

print(
    f"Total Commodity: "
    f"{Commodity.objects.count()}"
)

for commodity in Commodity.objects.all().order_by("nama"):
    print(
        commodity.id,
        "|",
        commodity.nama,
        "|",
        commodity.nama_normalized
    )