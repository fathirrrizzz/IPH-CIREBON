from pathlib import Path
import re
import traceback
from datetime import datetime, date
from urllib.parse import urlencode

import pandas as pd
import requests

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.conf import settings
from django.db import transaction
from django.db.models import Q

from .models import (
    Region,
    ReportPeriod,
    ImportBatch,
    Commodity,
    WeeklyIPH,
    CommodityContribution,
    IPHSeries,
)

# get_latest_weekly_iph HARUS sudah ada di infografis.py
# (dipakai dashboard DAN infografis agar periodenya selalu sama)
from .infografis import generate_infografis, get_latest_weekly_iph


# ============================================================
# KONFIGURASI
# ============================================================

CIREBON_CODE = "3209"

MONTH_MAP = {
    "januari": 1,
    "februari": 2,
    "maret": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "agustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}

MONTH_NAMES = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}

# Alias bulan untuk header file Series (singkatan + nama lengkap)
MONTH_ALIAS = {
    "jan": 1, "januari": 1,
    "feb": 2, "februari": 2,
    "mar": 3, "maret": 3,
    "apr": 4, "april": 4,
    "mei": 5, "may": 5,
    "jun": 6, "juni": 6,
    "jul": 7, "juli": 7,
    "ags": 8, "agu": 8, "aug": 8, "agustus": 8,
    "sep": 9, "september": 9,
    "okt": 10, "oct": 10, "oktober": 10,
    "nov": 11, "november": 11,
    "des": 12, "dec": 12, "desember": 12,
}

ALLOWED_EXTENSIONS = [".xlsx", ".xls", ".csv"]


# ============================================================
# HELPER UMUM
# ============================================================

def normalize_column_name(value):

    if value is None:
        return ""

    value = str(value).strip().lower()
    value = value.replace("\n", " ").replace("\r", " ")

    return re.sub(r"[^a-z0-9]+", "", value)


def clean_code(value):

    if pd.isna(value):
        return ""

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return re.sub(r"\s+", "", text)


def clean_number(value):

    if pd.isna(value):
        return None

    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none", "-", "—"}:
        return None

    text = text.replace("%", "").strip()

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def find_column(df, *possible_names):

    normalized_columns = {
        normalize_column_name(column): column
        for column in df.columns
    }

    for name in possible_names:

        target = normalize_column_name(name)

        if target in normalized_columns:
            return normalized_columns[target]

    return None


def find_code_column(df):

    return find_column(
        df,
        "Kode Kabupaten/Kota",
        "Kode Kabupaten Kota",
        "Kode Kab/Kota",
        "Kode Kabkot",
        "Kode Kabkot/Kota",
        "Kode Kabupaten",
        "Kode kab",
        "kode_kab",
        "kode kabkota",
    )


def period_label(tahun, bulan, minggu):

    return (
        f"M{minggu} "
        f"{MONTH_NAMES.get(bulan, str(bulan))} "
        f"{tahun}"
    )


# ============================================================
# PARSER PERIODE
# ============================================================

def parse_period_from_text(value, default_year=None):
    """
    Membaca periode dari nama kolom.
    Mendukung: 'M1 Januari 2026', tanggal, datetime/date.
    """

    if value is None or pd.isna(value):
        return None

    if isinstance(value, (datetime, date, pd.Timestamp)):
        dt = pd.Timestamp(value)
        return dt.year, dt.month, int(dt.isocalendar().week)

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none"}:
        return None

    lower = text.lower()

    week_match = re.search(
        r"(?<![a-z0-9])m[\s_\-]*(\d{1,2})(?!\d)",
        lower,
        re.IGNORECASE,
    )

    year_match = re.search(r"\b(20\d{2})\b", lower)

    month_number = None

    for month_name, month_number_candidate in MONTH_MAP.items():
        if month_name in lower:
            month_number = month_number_candidate
            break

    if week_match and month_number:

        week = int(week_match.group(1))

        year = (
            int(year_match.group(1))
            if year_match
            else default_year
        )

        if year:
            return year, month_number, week

    # 2026 M1 tanpa bulan: jangan mengarang bulan
    if week_match and year_match:
        return None

    date_patterns = [
        r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b",
        r"\b(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\b",
    ]

    for pattern in date_patterns:

        match = re.search(pattern, text)

        if not match:
            continue

        groups = [int(x) for x in match.groups()]

        if groups[0] >= 2000:
            year, month, day = groups
        else:
            day, month, year = groups

        try:
            dt = date(year, month, day)
        except ValueError:
            continue

        return dt.year, dt.month, int(dt.isocalendar().week)

    if month_number and year_match:
        return int(year_match.group(1)), month_number, 1

    return None


def parse_period_from_filename(filename):
    """
    Membaca periode dari nama file, contoh:
    '9.1 Indikator Per Harga M1 Agustus 2026 Jabar.xlsx'
    -> (2026, 8, 1)

    Bulan & tahun diambil yang muncul SETELAH token minggu,
    sehingga tidak tertukar bila nama file memuat kata/angka lain.
    """

    lower = filename.lower()

    week_match = re.search(
        r"(?<![a-z0-9])m[\s_\-]*(\d{1,2})(?!\d)",
        lower,
    )

    if not week_match:
        return None

    week = int(week_match.group(1))

    month_pattern = (
        r"(?<![a-z])("
        + "|".join(MONTH_MAP.keys())
        + r")(?![a-z])"
    )

    months = [
        (m.start(), MONTH_MAP[m.group(1)])
        for m in re.finditer(month_pattern, lower)
    ]

    if not months:
        return None

    after_week = [x for x in months if x[0] >= week_match.end()]

    month = (after_week or months)[0][1]

    year_matches = list(
        re.finditer(r"(?<!\d)(20\d{2})(?!\d)", lower)
    )

    if not year_matches:
        return None

    after_year = [
        m for m in year_matches
        if m.start() >= week_match.end()
    ]

    year = int((after_year or year_matches)[0].group(1))

    return year, month, week


# ============================================================
# DETEKSI SHEET & TIPE FILE
# ============================================================

def _clean_sheet_name(name):

    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )


def detect_excel_sheet(excel, data_type):

    sheets = excel.sheet_names

    if not sheets:
        raise ValueError("File Excel tidak memiliki sheet.")

    if data_type == "weekly":

        # 1) 360 KabKot / 360 Kabkota
        for sheet in sheets:
            clean = _clean_sheet_name(sheet)

            if "360kabkot" in clean or "360kabkota" in clean:
                return sheet

        # 2) File indikator mingguan terbaru memakai sheet "Jabar"
        for sheet in sheets:
            if _clean_sheet_name(sheet) == "jabar":
                return sheet

        # 3) Sheet yang namanya memuat kabkot / kabupaten
        for sheet in sheets:
            clean = _clean_sheet_name(sheet)

            if (
                "kabkot" in clean
                or "kabkota" in clean
                or "kabupaten" in clean
            ):
                return sheet

    if data_type == "series":

        # Utamakan sheet historis (mis. "SERIES IPH")
        for sheet in sheets:
            if "series" in _clean_sheet_name(sheet):
                return sheet

    # Fallback: sheet pertama yang memuat header kode kabupaten/kota
    for sheet in sheets:

        raw = pd.read_excel(
            excel,
            sheet_name=sheet,
            header=None,
            nrows=30,
        )

        for _, row in raw.iterrows():

            values = [
                normalize_column_name(x)
                for x in row.tolist()
            ]

            if any(
                value in {
                    "kodekabupatenkota",
                    "kodekabkot",
                    "kodekab",
                }
                for value in values
            ):
                return sheet

    return sheets[0]


def detect_data_type(uploaded_file):
    """
    Dipakai bila form tidak mengirim data_type yang valid.
    Mengembalikan 'weekly' atau 'series'.
    """

    name = uploaded_file.name.lower()

    if "series" in name:
        return "series"

    if name.endswith((".xlsx", ".xls")):

        try:
            uploaded_file.seek(0)

            excel = pd.ExcelFile(uploaded_file)

            sheets = [
                str(x).strip().lower().replace(" ", "")
                for x in excel.sheet_names
            ]

        except Exception:
            uploaded_file.seek(0)
            return "weekly"

        uploaded_file.seek(0)

        if any(
            "360kabkot" in x
            or "360kabkota" in x
            or x == "jabar"
            for x in sheets
        ):
            return "weekly"

        if any("series" in x for x in sheets):
            return "series"

    return "weekly"


# ============================================================
# BACA FILE WEEKLY
# ============================================================

def read_weekly_excel(excel, selected_sheet):

    return pd.read_excel(
        excel,
        sheet_name=selected_sheet,
    )


# ============================================================
# BACA FILE SERIES
# ============================================================

def read_series_excel(uploaded_file, selected_sheet):
    """
    Membaca file Series Jabar.

    Mengembalikan:
        row            -> baris data Kabupaten Cirebon
        period_columns -> [(kolom, (tahun, bulan, minggu)), ...]
    """

    uploaded_file.seek(0)

    raw_df = pd.read_excel(
        uploaded_file,
        sheet_name=selected_sheet,
        header=None,
    )

    if raw_df.empty:
        raise ValueError("File Series kosong.")

    header_row = None

    for i in range(min(len(raw_df), 40)):

        row_values = (
            raw_df.iloc[i]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        normalized_text = normalize_column_name(
            " | ".join(row_values.tolist())
        )

        if (
            "kodekabupatenkota" in normalized_text
            or "kodekabkot" in normalized_text
            or "kodekabkota" in normalized_text
            or "kodekab" in normalized_text
        ):
            header_row = i
            break

    if header_row is None:
        # Tidak ada kolom kode: baca berbasis nama wilayah
        return read_series_excel_by_name(raw_df)

    headers = raw_df.iloc[header_row].tolist()

    df = raw_df.iloc[header_row + 1:].copy()
    df.columns = headers
    df = df.reset_index(drop=True)

    code_column = find_code_column(df)

    if code_column is None:
        raise ValueError(
            "Kolom kode pada file Series tidak ditemukan "
            f"setelah header terdeteksi pada baris {header_row + 1}."
        )

    period_columns = []

    for column in df.columns:

        if column == code_column:
            continue

        parsed = parse_period_from_text(column)

        if parsed:
            period_columns.append((column, parsed))

    if not period_columns:
        raise ValueError(
            "Kolom periode mingguan pada file Series "
            "tidak dapat dikenali. Header Series harus memuat "
            "periode seperti 'M1 Januari 2026' atau tanggal."
        )

    row = get_cirebon_row(df, code_column)

    return row, period_columns


def _find_cirebon_row_by_name(raw_df, max_scan_cols=6):
    """Cari baris Kabupaten Cirebon berdasarkan nama persis
    'CIREBON' (bukan 'KOTA CIREBON')."""

    for col in range(min(raw_df.shape[1], max_scan_cols)):

        col_values = (
            raw_df.iloc[:, col]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        matches = col_values[col_values == "CIREBON"]

        if not matches.empty:
            return matches.index[0], col

    return None, None


def _find_week_header_row(raw_df, before_row, max_scan=40):
    """Baris terdekat sebelum data yang berisi banyak M1/M2/M3."""

    start = max(0, before_row - max_scan)

    best_row = None

    for i in range(start, before_row):

        row = raw_df.iloc[i].astype(str).str.strip()

        matches = row.str.match(
            r"(?i)^m\s*\d{1,2}$",
            na=False,
        )

        if matches.sum() >= 2:
            best_row = i

    return best_row


def _find_month_header_row(raw_df, week_row):
    """Baris header bulan (nama lengkap atau singkatan)."""

    for i in range(max(0, week_row - 3), week_row):

        row = (
            raw_df.iloc[i]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        if row.isin(MONTH_ALIAS.keys()).sum() >= 1:
            return i

    return None


def _find_year_header_row(raw_df, month_row):
    """Baris header tahun dengan jumlah tahun (20xx) terbanyak."""

    best_row = None
    best_count = 0

    start = max(0, month_row - 4)

    for i in range(start, month_row + 1):

        row = raw_df.iloc[i].astype(str).str.strip()

        count = row.str.match(
            r"^20\d{2}(\.0)?$",
            na=False,
        ).sum()

        if count > best_count:
            best_count = count
            best_row = i

    return best_row


def read_series_excel_by_name(raw_df):
    """
    Membaca Series IPH berbentuk matriks:
    baris tahun, baris bulan, baris minggu (M1/M2/...),
    lalu baris data wilayah. Target: Kabupaten Cirebon.
    """

    cirebon_row_idx, name_col = _find_cirebon_row_by_name(raw_df)

    if cirebon_row_idx is None:
        raise ValueError(
            "Baris Kabupaten Cirebon tidak ditemukan "
            "pada file Series."
        )

    week_row_idx = _find_week_header_row(raw_df, cirebon_row_idx)

    if week_row_idx is None:
        raise ValueError(
            "Baris header minggu M1/M2/M3/... tidak ditemukan."
        )

    month_row_idx = _find_month_header_row(raw_df, week_row_idx)

    if month_row_idx is None:
        raise ValueError(
            "Baris header bulan pada file Series tidak ditemukan."
        )

    year_row_idx = _find_year_header_row(raw_df, month_row_idx)

    if year_row_idx is None:
        raise ValueError(
            "Baris header tahun pada file Series tidak ditemukan."
        )

    month_row = (
        raw_df.iloc[month_row_idx]
        .astype(str)
        .str.strip()
        .str.lower()
        .replace({"nan": None})
        .ffill()
    )

    week_row = raw_df.iloc[week_row_idx].astype(str).str.strip()

    year_row = (
        raw_df.iloc[year_row_idx]
        .astype(str)
        .str.strip()
        .replace({"nan": None})
        .ffill()
    )

    data_row = raw_df.iloc[cirebon_row_idx]

    period_columns = []

    for col in range(raw_df.shape[1]):

        if col == name_col:
            continue

        # Minggu
        week_match = re.match(
            r"(?i)^m\s*(\d{1,2})$",
            str(week_row.iloc[col]).strip(),
        )

        if not week_match:
            continue

        minggu = int(week_match.group(1))

        # Bulan
        month_text = month_row.iloc[col]

        if not month_text:
            continue

        month_text = str(month_text).strip().lower()

        if month_text not in MONTH_ALIAS:
            continue

        bulan = MONTH_ALIAS[month_text]

        # Tahun
        year_clean = re.sub(
            r"\.0$",
            "",
            str(year_row.iloc[col]).strip(),
        )

        if not re.match(r"^20\d{2}$", year_clean):
            continue

        tahun = int(year_clean)

        period_columns.append((col, (tahun, bulan, minggu)))

    if not period_columns:
        raise ValueError(
            "Tidak ada periode Series yang berhasil dikenali."
        )

    period_columns.sort(
        key=lambda item: (
            item[1][0],
            item[1][1],
            item[1][2],
        )
    )

    return data_row, period_columns


def get_cirebon_row(df, code_column):

    kode_data = df[code_column].apply(clean_code)

    result = df[kode_data == CIREBON_CODE].copy()

    if result.empty:
        raise ValueError(
            "Kode Kabupaten Cirebon (3209) "
            "tidak ditemukan dalam file."
        )

    return result.iloc[0]


def get_region_cirebon():

    return Region.objects.get(kode_kabkota=CIREBON_CODE)


# ============================================================
# SIMPAN DATA
# ============================================================

def save_series_observation(
    region,
    tahun,
    bulan,
    minggu,
    nilai_iph,
):

    if nilai_iph is None:
        return False

    IPHSeries.objects.update_or_create(
        region=region,
        tahun=tahun,
        bulan=bulan,
        minggu=minggu,
        defaults={"nilai_iph": nilai_iph},
    )

    ReportPeriod.objects.update_or_create(
        tahun=tahun,
        bulan=bulan,
        minggu=minggu,
        defaults={
            "label": period_label(tahun, bulan, minggu),
        },
    )

    return True


def process_weekly_file(uploaded_file, region):
    """
    File 1: Weekly update.

    Menyimpan WeeklyIPH + CommodityContribution, dan
    memperbarui observasi minggu tsb pada IPHSeries.

    Mengembalikan label periode yang terbaca (mis. 'M1 Agustus 2026')
    supaya bisa ditampilkan ke pengguna.
    """

    file_name = uploaded_file.name
    selected_sheet = ""

    print("\n==============================")
    print("FILE WEEKLY YANG DIPROSES:")
    print(file_name)
    print("==============================\n")

    # --------------------------------------------------------
    # Baca Excel/CSV
    # --------------------------------------------------------

    if file_name.lower().endswith((".xlsx", ".xls")):

        uploaded_file.seek(0)

        excel = pd.ExcelFile(uploaded_file)

        selected_sheet = detect_excel_sheet(excel, "weekly")

        df = read_weekly_excel(excel, selected_sheet)

    else:

        try:
            uploaded_file.seek(0)

            df = pd.read_csv(
                uploaded_file,
                sep=None,
                engine="python",
                encoding="utf-8-sig",
            )

        except UnicodeDecodeError:

            uploaded_file.seek(0)

            df = pd.read_csv(
                uploaded_file,
                sep=None,
                engine="python",
                encoding="latin-1",
            )

    # --------------------------------------------------------
    # Cari kolom
    # --------------------------------------------------------

    code_column = find_code_column(df)

    if code_column is None:
        raise ValueError(
            "Kolom kode tidak ditemukan pada file Weekly. "
            "Kolom yang terbaca: "
            + " | ".join(str(column) for column in df.columns)
        )

    row = get_cirebon_row(df, code_column)

    perubahan_column = find_column(
        df,
        "Perubahan IPH",
        "PerubahanIPH",
    )

    if perubahan_column is None:
        raise ValueError(
            "Kolom 'Perubahan IPH' tidak ditemukan pada file Weekly."
        )

    status_column = find_column(df, "status", "Status")

    fluktuasi_column = find_column(
        df,
        "Fluktuasi Harga Tertinggi Minggu Berjalan",
        "Fluktuasi Harga Tertinggi",
        "Fluktuasi Tertinggi",
    )

    cv_column = find_column(
        df,
        "Nilai CV (Nilai fluktuasi)",
        "Nilai CV",
        "CV",
    )

    disparitas_column = find_column(
        df,
        "Disparitas Harga antar Daerah",
        "Disparitas Harga Antar Daerah",
        "Disparitas Harga",
    )

    upaya_column = find_column(
        df,
        "Upaya Pemda (Monev APP)",
        "Upaya Pemda",
    )

    saran_column = find_column(
        df,
        "Saran Kepada Pemda",
        "Saran Pemda",
    )

    commodity_column = find_column(
        df,
        "Komoditas Andil Besar",
        "Komoditas Utama Penyumbang",
        "Komoditas Utama",
        "Komoditas Penyumbang",
    )

    perubahan = clean_number(row.get(perubahan_column))

    if perubahan is None:
        raise ValueError(
            "Nilai 'Perubahan IPH' tidak ditemukan pada file Weekly."
        )

    # --------------------------------------------------------
    # Periode dari nama file
    # --------------------------------------------------------

    parsed_period = parse_period_from_filename(file_name)

    if parsed_period is None:
        raise ValueError(
            "Periode Weekly tidak dapat dibaca dari nama file. "
            "Gunakan format seperti 'M4 April 2026'."
        )

    tahun, bulan, minggu = parsed_period

    label = period_label(tahun, bulan, minggu)

    print(
        f"PERIODE TERBACA: tahun={tahun}, bulan={bulan}, "
        f"minggu={minggu}, label={label}, file={file_name}"
    )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    status_raw = ""

    if status_column:

        value = row.get(status_column, "")

        if not pd.isna(value):
            status_raw = str(value).strip().lower()

    if "naik" in status_raw:
        status = "naik"
    elif "turun" in status_raw:
        status = "turun"
    elif "stabil" in status_raw:
        status = "stabil"
    elif perubahan > 0:
        status = "naik"
    elif perubahan < 0:
        status = "turun"
    else:
        status = "stabil"

    # --------------------------------------------------------
    # Data tambahan
    # --------------------------------------------------------

    def get_text(column):

        if not column:
            return ""

        value = row.get(column, "")

        if pd.isna(value):
            return ""

        return str(value).strip()

    fluktuasi = get_text(fluktuasi_column)
    upaya_pemda = get_text(upaya_column)
    saran_pemda = get_text(saran_column)

    nilai_cv = (
        clean_number(row.get(cv_column))
        if cv_column
        else None
    )

    disparitas = (
        clean_number(row.get(disparitas_column))
        if disparitas_column
        else None
    )

    # --------------------------------------------------------
    # Simpan
    # --------------------------------------------------------

    import_batch = ImportBatch.objects.create(
        nama_file=file_name,
        sheet_name=selected_sheet,
        jumlah_baris=len(df),
        status="proses",
    )

    try:

        with transaction.atomic():

            period, _ = ReportPeriod.objects.update_or_create(
                tahun=tahun,
                bulan=bulan,
                minggu=minggu,
                defaults={"label": label},
            )

            save_series_observation(
                region=region,
                tahun=tahun,
                bulan=bulan,
                minggu=minggu,
                nilai_iph=perubahan,
            )

            # import_batch ikut diperbarui saat re-upload periode
            # yang sama, sehingga upload terakhir selalu jadi
            # "data terbaru" di dashboard.
            weekly, _ = WeeklyIPH.objects.update_or_create(
                region=region,
                period=period,
                defaults={
                    "perubahan_iph": perubahan,
                    "fluktuasi_tertinggi": fluktuasi,
                    "nilai_cv": nilai_cv,
                    "disparitas_harga": disparitas,
                    "status": status,
                    "upaya_pemda": upaya_pemda,
                    "saran_pemda": saran_pemda,
                    "import_batch": import_batch,
                },
            )

            # Hapus kontribusi lama agar re-upload tidak menggandakan
            CommodityContribution.objects.filter(
                weekly_iph=weekly
            ).delete()

            # ------------------------------------------------
            # Komoditas andil besar
            # ------------------------------------------------

            if commodity_column:

                commodity_text = row.get(commodity_column, "")

                if (
                    not pd.isna(commodity_text)
                    and str(commodity_text).strip()
                ):

                    commodity_text = str(commodity_text).strip()

                    pattern = (
                        r"([^,(]+?)"
                        r"\s*\(\s*"
                        r"([-+]?\d+(?:[,.]\d+)?)"
                        r"\s*\)"
                    )

                    matches = re.findall(pattern, commodity_text)

                    for commodity_name, value in matches[:3]:

                        commodity_name = commodity_name.strip()

                        value = value.replace(",", ".")

                        try:
                            nilai_andil = float(value)
                        except ValueError:
                            continue

                        normalized = re.sub(
                            r"\s+",
                            " ",
                            commodity_name.strip().upper(),
                        )

                        commodity = (
                            Commodity.objects
                            .filter(nama_normalized=normalized)
                            .first()
                        )

                        if commodity is None:
                            commodity = (
                                Commodity.objects
                                .filter(nama__iexact=commodity_name)
                                .first()
                            )

                        if commodity is None:
                            commodity = Commodity.objects.create(
                                nama=commodity_name,
                                nama_normalized=normalized,
                            )

                        CommodityContribution.objects.update_or_create(
                            weekly_iph=weekly,
                            commodity=commodity,
                            defaults={"nilai_andil": nilai_andil},
                        )

            import_batch.status = "berhasil"
            import_batch.save(update_fields=["status"])

    except Exception as error:

        import_batch.status = "gagal"
        import_batch.pesan_error = str(error)
        import_batch.save(update_fields=["status", "pesan_error"])

        raise

    return label


def process_series_file(uploaded_file, region):
    """
    File 2: Series Jabar.

    Setiap kolom periode disimpan sebagai observasi IPHSeries
    Cirebon. Series TIDAK mengubah periode dashboard; hanya
    upload Weekly yang menentukan periode terbaru.
    """

    file_name = uploaded_file.name
    selected_sheet = ""

    if file_name.lower().endswith((".xlsx", ".xls")):

        uploaded_file.seek(0)

        excel = pd.ExcelFile(uploaded_file)

        selected_sheet = detect_excel_sheet(excel, "series")

        row, period_columns = read_series_excel(
            uploaded_file,
            selected_sheet,
        )

        row_count = len(period_columns)

    else:

        try:
            uploaded_file.seek(0)

            df = pd.read_csv(
                uploaded_file,
                sep=None,
                engine="python",
                encoding="utf-8-sig",
            )

        except UnicodeDecodeError:

            uploaded_file.seek(0)

            df = pd.read_csv(
                uploaded_file,
                sep=None,
                engine="python",
                encoding="latin-1",
            )

        code_column = find_code_column(df)

        if code_column is None:
            raise ValueError(
                "Kolom kode tidak ditemukan pada file Series."
            )

        period_columns = []

        for column in df.columns:

            if column == code_column:
                continue

            parsed = parse_period_from_text(column)

            if parsed:
                period_columns.append((column, parsed))

        row = get_cirebon_row(df, code_column)

        row_count = len(df)

    if not period_columns:
        raise ValueError(
            "Tidak ada kolom periode Series yang dapat dibaca."
        )

    import_batch = ImportBatch.objects.create(
        nama_file=file_name,
        sheet_name=selected_sheet,
        jumlah_baris=row_count,
        status="proses",
    )

    saved_count = 0

    try:

        with transaction.atomic():

            for period_column, parsed_period in period_columns:

                if parsed_period is None:
                    continue

                tahun, bulan, minggu = parsed_period

                nilai_iph = clean_number(row.get(period_column))

                if nilai_iph is None:
                    continue

                save_series_observation(
                    region=region,
                    tahun=tahun,
                    bulan=bulan,
                    minggu=minggu,
                    nilai_iph=nilai_iph,
                )

                saved_count += 1

            if saved_count == 0:
                raise ValueError(
                    "Tidak ada nilai IPH Cirebon yang berhasil "
                    "dibaca dari kolom periode Series."
                )

            import_batch.status = "berhasil"
            import_batch.save(update_fields=["status"])

    except Exception as error:

        import_batch.status = "gagal"
        import_batch.pesan_error = str(error)
        import_batch.save(update_fields=["status", "pesan_error"])

        raise

    print(
        f"SERIES TERBACA: {saved_count} observasi, file={file_name}"
    )


# ============================================================
# LOGIN
# ============================================================

def login_view(request):

    if request.user.is_authenticated:
        return redirect("home")

    error = None

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:

            login(request, user)

            return redirect("home")

        error = "Username atau password tidak sesuai."

    return render(
        request,
        "iph/login.html",
        {"error": error},
    )


# ============================================================
# GOOGLE LOGIN
# ============================================================

def google_login(request):

    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "").strip()
    redirect_uri = getattr(settings, "GOOGLE_REDIRECT_URI", "").strip()

    if not client_id or not redirect_uri:
        return render(
            request,
            "iph/login.html",
            {
                "error": (
                    "Konfigurasi Google Login belum lengkap. "
                    "Silakan hubungi administrator."
                )
            },
        )

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }

    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode(params)
    )

    return redirect(google_auth_url)


def google_callback(request):

    code = request.GET.get("code")
    error = request.GET.get("error")

    if error:
        return render(
            request,
            "iph/login.html",
            {"error": "Login dengan Google dibatalkan atau ditolak."},
        )

    if not code:
        return render(
            request,
            "iph/login.html",
            {"error": "Kode autentikasi Google tidak ditemukan."},
        )

    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "").strip()

    client_secret = getattr(
        settings,
        "GOOGLE_CLIENT_SECRET",
        "",
    ).strip()

    redirect_uri = getattr(
        settings,
        "GOOGLE_REDIRECT_URI",
        "",
    ).strip()

    if not client_id or not client_secret or not redirect_uri:
        return render(
            request,
            "iph/login.html",
            {
                "error": (
                    "Konfigurasi Google Login belum lengkap. "
                    "Silakan hubungi administrator."
                )
            },
        )

    # Tukar authorization code dengan access token
    try:
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
    except requests.RequestException:
        return render(
            request,
            "iph/login.html",
            {
                "error": (
                    "Tidak dapat terhubung ke layanan Google. "
                    "Silakan coba lagi."
                )
            },
        )

    if token_response.status_code != 200:
        return render(
            request,
            "iph/login.html",
            {"error": "Autentikasi Google gagal. Silakan coba lagi."},
        )

    try:
        token_data = token_response.json()
    except ValueError:
        return render(
            request,
            "iph/login.html",
            {"error": "Respons autentikasi Google tidak valid."},
        )

    access_token = token_data.get("access_token")

    if not access_token:
        return render(
            request,
            "iph/login.html",
            {"error": "Token autentikasi Google tidak ditemukan."},
        )

    # Ambil informasi akun Google
    try:
        userinfo_response = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except requests.RequestException:
        return render(
            request,
            "iph/login.html",
            {"error": "Informasi akun Google tidak dapat diambil."},
        )

    if userinfo_response.status_code != 200:
        return render(
            request,
            "iph/login.html",
            {"error": "Informasi akun Google tidak dapat diambil."},
        )

    try:
        google_data = userinfo_response.json()
    except ValueError:
        return render(
            request,
            "iph/login.html",
            {"error": "Data akun Google tidak valid."},
        )

    google_email = (
        google_data.get("email", "")
        .strip()
        .lower()
    )

    if not google_email:
        return render(
            request,
            "iph/login.html",
            {"error": "Email akun Google tidak ditemukan."},
        )

    # Hanya akun RIFORA yang sudah terdaftar yang boleh masuk
    user = User.objects.filter(email__iexact=google_email).first()

    if user is None:
        return redirect(f"/register/?google_email={google_email}")

    if not user.is_active:
        return render(
            request,
            "iph/login.html",
            {
                "error": (
                    "Akun RIFORA belum diaktifkan "
                    "oleh administrator."
                )
            },
        )

    login(
        request,
        user,
        backend="django.contrib.auth.backends.ModelBackend",
    )

    return redirect("home")


# ============================================================
# REGISTER
# ============================================================

def register_view(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    google_email = (
        request.GET.get("google_email", "")
        .strip()
        .lower()
    )

    error = None

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        password2 = request.POST.get("password2", "")

        if not username or not email or not password or not password2:
            error = "Semua kolom wajib diisi."

        elif password != password2:
            error = "Konfirmasi password tidak sesuai."

        elif User.objects.filter(username=username).exists():
            error = "Username sudah digunakan."

        elif User.objects.filter(email=email).exists():
            error = "Email sudah terdaftar."

        else:

            User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )

            return render(
                request,
                "iph/login.html",
                {
                    "success": (
                        "Registrasi berhasil. "
                        "Silakan masuk menggunakan akun yang "
                        "telah dibuat."
                    )
                },
            )

    return render(
        request,
        "iph/register.html",
        {
            "error": error,
            "google_email": google_email,
        },
    )


# ============================================================
# HOME / LOGOUT / HALAMAN SEDERHANA
# ============================================================

@login_required(login_url="login")
def home_view(request):

    return render(request, "iph/home.html")


def logout_view(request):

    logout(request)

    return redirect("login")


@login_required(login_url="login")
def generate(request):

    return render(request, "iph/generate.html")


# ============================================================
# DASHBOARD
# ============================================================

@login_required(login_url="login")
def dashboard(request):

    # ========================================================
    # 1. WILAYAH
    # ========================================================

    region = get_object_or_404(
        Region,
        kode_kabkota=CIREBON_CODE,
    )

    # ========================================================
    # 2. WEEKLY DARI UPLOAD TERAKHIR
    #
    # Acuan dashboard adalah upload Weekly TERAKHIR (ID batch
    # import terbesar), bukan periode kalender terbesar.
    # Fungsi yang sama dipakai infografis.
    # ========================================================

    latest_data = get_latest_weekly_iph(region)

    # ========================================================
    # DEFAULT
    # ========================================================

    latest_series = []
    chart_labels = []
    chart_values = []

    latest_iph = None
    chart_year = None

    latest_value = None
    latest_period_label = "-"

    status = "-"
    perubahan = None
    fluktuasi_tertinggi = "-"

    commodity_insights = []

    arah = "-"
    kata_kerja = "-"

    # ========================================================
    # 3. DATA WEEKLY TERBARU
    # ========================================================

    if latest_data:

        anchor_year = latest_data.period.tahun
        anchor_month = latest_data.period.bulan
        anchor_week = latest_data.period.minggu

        # Nilai IPH HARUS dari WeeklyIPH
        latest_value = float(latest_data.perubahan_iph)
        perubahan = float(latest_data.perubahan_iph)

        latest_period_label = period_label(
            anchor_year,
            anchor_month,
            anchor_week,
        )

        status = latest_data.status or "-"

        fluktuasi_tertinggi = (
            latest_data.fluktuasi_tertinggi or "-"
        )

        # ====================================================
        # 4. IPHSERIES HANYA SAMPAI PERIODE WEEKLY TERAKHIR
        #
        # Periode setelah anchor TIDAK boleh masuk grafik.
        # ====================================================

        series_queryset = (
            IPHSeries.objects
            .filter(region=region)
            .filter(
                Q(tahun__lt=anchor_year)
                |
                Q(
                    tahun=anchor_year,
                    bulan__lt=anchor_month,
                )
                |
                Q(
                    tahun=anchor_year,
                    bulan=anchor_month,
                    minggu__lte=anchor_week,
                )
            )
        )

        latest_series = list(
            series_queryset
            .order_by("-tahun", "-bulan", "-minggu", "-id")[:4]
        )

        # Balik agar grafik: lama -> baru
        latest_series.reverse()

        # ====================================================
        # 5. DATA GRAFIK
        # ====================================================

        for item in latest_series:

            chart_labels.append(
                period_label(item.tahun, item.bulan, item.minggu)
            )

            chart_values.append(float(item.nilai_iph))

        if latest_series:
            latest_iph = latest_series[-1]
            chart_year = latest_iph.tahun
        else:
            chart_year = anchor_year

        # ====================================================
        # 6. KOMODITAS DARI WEEKLY YANG SAMA
        # ====================================================

        contributions = (
            CommodityContribution.objects
            .select_related("commodity", "weekly_iph")
            .filter(weekly_iph=latest_data)
            .order_by("-nilai_andil")
        )

        for item in contributions[:3]:

            commodity_insights.append(
                {
                    "nama": item.commodity.nama,
                    "nilai": float(item.nilai_andil),
                }
            )

        # ====================================================
        # 7. ARAH PERUBAHAN
        # ====================================================

        if perubahan > 0:
            arah = "kenaikan"
            kata_kerja = "mengalami kenaikan"

        elif perubahan < 0:
            arah = "penurunan"
            kata_kerja = "mengalami penurunan"

        else:
            arah = "kondisi stabil"
            kata_kerja = "berada dalam kondisi stabil"

    else:

        # ====================================================
        # TIDAK ADA DATA WEEKLY
        # ====================================================

        latest_series = list(
            IPHSeries.objects
            .filter(region=region)
            .order_by("-tahun", "-bulan", "-minggu", "-id")[:4]
        )

        latest_series.reverse()

        for item in latest_series:

            chart_labels.append(
                period_label(item.tahun, item.bulan, item.minggu)
            )

            chart_values.append(float(item.nilai_iph))

        if latest_series:
            latest_iph = latest_series[-1]
            chart_year = latest_iph.tahun

    # ========================================================
    # 8. CONTEXT
    # ========================================================

    context = {
        "region": region,

        # Grafik
        "latest_series": latest_series,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "latest_iph": latest_iph,
        "chart_year": chart_year,

        # Weekly terbaru
        "latest_data": latest_data,
        "latest_value": latest_value,
        "latest_period_label": latest_period_label,
        "status": status,
        "perubahan": perubahan,
        "fluktuasi_tertinggi": fluktuasi_tertinggi,

        # Insight
        "arah": arah,
        "kata_kerja": kata_kerja,

        # Komoditas
        "commodity_insights": commodity_insights,

        # Ringkasan
        "total_region": 1,
        "total_period": len(latest_series),
        "total_data": len(latest_series),
    }

    return render(request, "iph/dashboard.html", context)


# ============================================================
# UPLOAD DATA
# ============================================================

@login_required(login_url="login")
def upload_data(request):
    """
    Upload satu file sesuai form upload.html.

    Form memakai:
        name="data_type"  -> weekly / series (opsional)
        name="file"       -> file yang dipilih

    Weekly : menyimpan WeeklyIPH + kontribusi komoditas dan
             menentukan periode dashboard.
    Series : memperbarui riwayat IPHSeries saja.
    """

    if request.method != "POST":
        return render(request, "iph/upload.html")

    data_type = (
        request.POST.get("data_type", "")
        .strip()
        .lower()
    )

    uploaded_file = (
        request.FILES.get("file")
        or request.FILES.get("weekly_file")
        or request.FILES.get("series_file")
    )

    if uploaded_file is None:
        return render(
            request,
            "iph/upload.html",
            {"error": "Silakan unggah file terlebih dahulu."},
        )

    file_name = uploaded_file.name.lower()

    if not any(
        file_name.endswith(extension)
        for extension in ALLOWED_EXTENSIONS
    ):
        return render(
            request,
            "iph/upload.html",
            {
                "error": (
                    "Format file tidak didukung. "
                    "Gunakan .xlsx, .xls, atau .csv."
                ),
            },
        )

    # Jika form tidak mengirim data_type yang valid -> deteksi otomatis
    if data_type not in {"weekly", "series"}:
        data_type = detect_data_type(uploaded_file)

    try:

        region = get_region_cirebon()

        # ----------------------------------------------------
        # FILE 1 - WEEKLY INDICATOR
        # ----------------------------------------------------

        if data_type == "weekly":

            period_text = process_weekly_file(
                uploaded_file,
                region,
            )

            return render(
                request,
                "iph/upload.html",
                {
                    "success": (
                        f"File Weekly berhasil diimport: "
                        f"{uploaded_file.name}. "
                        f"Periode terbaca: {period_text}. "
                        "Dashboard sekarang mengikuti periode ini."
                    ),
                },
            )

        # ----------------------------------------------------
        # FILE 2 - SERIES IPH
        # ----------------------------------------------------

        process_series_file(
            uploaded_file,
            region,
        )

        return render(
            request,
            "iph/upload.html",
            {
                "success": (
                    f"File Series berhasil diimport: "
                    f"{uploaded_file.name}. "
                    "Riwayat IPH diperbarui, tetapi periode dashboard "
                    "hanya berubah oleh upload data Weekly."
                ),
            },
        )

    except Exception as error:

        traceback.print_exc()

        return render(
            request,
            "iph/upload.html",
            {
                "error": f"Gagal mengimport data: {error}",
            },
        )


# ============================================================
# ANALISIS
# ============================================================

@login_required(login_url="login")
def analisis(request):

    region = get_object_or_404(
        Region,
        kode_kabkota=CIREBON_CODE,
    )

    return render(
        request,
        "iph/analisis.html",
        {"region": region},
    )


# ============================================================
# GENERATE INFOGRAFIS
# ============================================================

@login_required(login_url="login")
def generate_view(request):

    if request.method == "POST":

        try:

            output_path = generate_infografis()

            output_url = (
                settings.MEDIA_URL
                + "generated/"
                + output_path.name
            )

            return render(
                request,
                "iph/generate.html",
                {"output_url": output_url},
            )

        except Exception as error:

            traceback.print_exc()

            return render(
                request,
                "iph/generate.html",
                {
                    "error": (
                        "Gagal membuat infografis: "
                        f"{error}"
                    ),
                },
            )

    return render(request, "iph/generate.html")