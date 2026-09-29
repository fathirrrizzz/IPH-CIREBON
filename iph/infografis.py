from pathlib import Path
import re

from django.conf import settings
from django.db.models import F

from PIL import Image, ImageDraw, ImageFont

from .models import (
    Region,
    IPHSeries,
    WeeklyIPH,
    CommodityContribution,
)


# ============================================================
# KONFIGURASI
# ============================================================

REGION_CODE = "3209"

# Template yang teks lama & isi kartunya sudah dibersihkan
TEMPLATE_FILENAME = "template_infografis_iph_bersih.png"

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


# ============================================================
# DATA WEEKLY TERBARU (dipakai dashboard DAN infografis)
# ============================================================

def get_latest_weekly_iph(region):
    """
    Weekly dari upload TERAKHIR, berdasarkan ID batch import
    (selalu naik pada setiap upload). Dashboard dan infografis
    memakai fungsi ini agar periodenya selalu sama.
    """

    return (
        WeeklyIPH.objects
        .select_related("period", "region", "import_batch")
        .filter(region=region)
        .order_by(
            F("import_batch_id").desc(nulls_last=True),
            "-id",
        )
        .first()
    )


# ============================================================
# FONT
# ============================================================

def get_font(size, bold=False):

    if bold:
        candidates = [
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/segoeuib.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf"),
        ]
    else:
        candidates = [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"),
        ]

    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)

    return ImageFont.load_default()


# ============================================================
# UTILITAS
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text).lower()
    text = re.sub(r"[^a-z0-9]+", "", text)

    return text


def format_decimal(value, decimals=2):

    if value is None:
        return "-"

    value = float(value)

    return f"{value:.{decimals}f}".replace(".", ",")


def format_signed(value, decimals=2):

    if value is None:
        return "-"

    value = float(value)

    return f"{value:+.{decimals}f}".replace(".", ",")


def month_name(month):

    return MONTH_NAMES.get(int(month), str(month))


def roman_week(week):

    romans = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}

    return romans.get(int(week), str(week))


def title_case_commodity(text):

    if not text:
        return "-"

    return str(text).strip().title()


def draw_justified_mixed(
    draw,
    segments,
    x,
    y,
    max_width,
    line_height=31,
    fill=(30, 30, 30, 255),
):

    words = []

    for text, font in segments:
        for word in str(text).split():
            words.append((word, font))

    if not words:
        return y

    lines = []
    current_line = []
    current_width = 0

    for word, font in words:

        bbox = draw.textbbox(
            (0, 0),
            word,
            font=font,
        )

        word_width = bbox[2] - bbox[0]

        if current_line:

            space_width = draw.textlength(
                " ",
                font=current_line[-1][1],
            )

            needed_width = (
                current_width
                + space_width
                + word_width
            )

        else:

            needed_width = word_width

        if (
            not current_line
            or needed_width <= max_width
        ):

            if current_line:

                current_width = needed_width

            else:

                current_width = word_width

            current_line.append(
                (word, font)
            )

        else:

            lines.append(current_line)

            current_line = [
                (word, font)
            ]

            current_width = word_width

    if current_line:
        lines.append(current_line)

    # ========================================================
    # GAMBAR BARIS
    # ========================================================

    for line_index, line in enumerate(lines):

        word_widths = []
        total_word_width = 0

        # Hitung lebar masing-masing kata
        for word, font in line:

            bbox = draw.textbbox(
                (0, 0),
                word,
                font=font,
            )

            word_width = (
                bbox[2] - bbox[0]
            )

            word_widths.append(
                word_width
            )

            total_word_width += word_width

        # Baris terakhir tidak dibuat justify
        is_last_line = (
            line_index == len(lines) - 1
        )

        # ====================================================
        # BARIS NORMAL / BARIS TERAKHIR
        # ====================================================

        if (
            is_last_line
            or len(line) == 1
        ):

            current_x = x

            for index, (word, font) in enumerate(line):

                draw.text(
                    (current_x, y),
                    word,
                    font=font,
                    fill=fill,
                )

                current_x += word_widths[index]

                if index < len(line) - 1:

                    current_x += draw.textlength(
                        " ",
                        font=font,
                    )

        # ====================================================
        # BARIS JUSTIFY
        # ====================================================

        else:

            gap_count = len(line) - 1

            extra_space = (
                max_width
                - total_word_width
            )

            justified_space = (
                extra_space / gap_count
            )

            current_x = x

            for index, (word, font) in enumerate(line):

                draw.text(
                    (current_x, y),
                    word,
                    font=font,
                    fill=fill,
                )

                current_x += word_widths[index]

                if index < gap_count:

                    current_x += justified_space

        y += line_height

    return y


# ============================================================
# CARI GAMBAR KOMODITAS
# ============================================================

def find_commodity_image(commodity_name):

    image_dir = (
        Path(settings.BASE_DIR)
        / "iph"
        / "static"
        / "iph"
        / "images"
    )

    if not image_dir.exists():
        return None

    image_map = {
        "bawang merah": "bawang-merah.png",
        "bawang putih": "bawang-putih.png",
        "beras": "beras.png",
        "cabai merah": "cabai-merah.png",
        "cabai rawit": "cabai-rawit.png",
        "daging ayam ras": "daging-ayam-ras.png",
        "daging sapi": "daging-sapi.png",
        "gula pasir": "gula-pasir.png",
        "ikan kembung": "ikan-kembung.png",
        "jeruk": "jeruk.png",
        "mie instan": "mie-instan.png",
        "minyak goreng": "minyak-goreng.png",
        "pisang": "pisang.png",
        "susu bubuk balita": "susu-bubuk-balita.png",
        "susu bubuk": "susu-bubuk.png",
        "tahu mentah": "tahu-mentah.png",
        "telur ayam ras": "telur-ayam-ras.png",
        "tempe": "tempe.png",
        "tepung terigu": "tepung-terigu.png",
        "udang": "udang.png",
    }

    normalized_name = str(commodity_name or "").strip().lower()

    filename = image_map.get(normalized_name)

    if not filename:
        return None

    image_path = image_dir / filename

    if image_path.exists():
        return image_path

    return None


# ============================================================
# GAMBAR KOMODITAS
# ============================================================

def paste_commodity_image(canvas, commodity_name, x, y, size=58):

    image_path = find_commodity_image(commodity_name)

    if not image_path:
        return

    try:

        image = Image.open(image_path).convert("RGBA")

        image.thumbnail((size, size), Image.Resampling.LANCZOS)

        canvas.alpha_composite(image, (x, y))

    except Exception:
        pass


# ============================================================
# GRAFIK IPH
# ============================================================

def draw_iph_chart(canvas, series):

    draw = ImageDraw.Draw(canvas)

    left = 102
    right = 720
    top = 114
    bottom = 375

    width = right - left
    height = bottom - top

    if not series:
        return

    values = [float(item.nilai_iph) for item in series]

    labels = [
        f"M{item.minggu} {month_name(item.bulan)}"
        for item in series
    ]

    # ========================================================
    # SKALA
    # ========================================================

    raw_min = min(values)
    raw_max = max(values)

    if raw_max <= 0:

        max_value = 0.0

        min_value = min(
            -4.0,
            float(int(raw_min) - (1 if raw_min % 1 else 0)),
        )

    elif raw_min >= 0:

        min_value = 0.0

        max_value = max(
            4.0,
            float(int(raw_max) + (1 if raw_max % 1 else 0)),
        )

    else:

        min_value = float(int(raw_min) - (1 if raw_min % 1 else 0))
        max_value = float(int(raw_max) + (1 if raw_max % 1 else 0))

    if max_value == min_value:
        max_value += 1
        min_value -= 1

    def y_position(value):

        ratio = (max_value - value) / (max_value - min_value)

        return top + (ratio * height)

    # ========================================================
    # BERSIHKAN AREA GRAFIK
    # ========================================================

    white = (255, 255, 255, 255)

    draw.rectangle([left, top, right, bottom], fill=white)
    draw.rectangle([52, top - 4, left - 4, bottom + 2], fill=white)
    draw.rectangle([left, bottom + 2, right, 401], fill=white)

    # ========================================================
    # GRID
    # ========================================================

    grid_font = get_font(12)

    tick_count = 4

    for i in range(tick_count + 1):

        value = max_value - ((max_value - min_value) * i / tick_count)

        y = int(top + (height * i / tick_count))

        draw.line([left, y, right, y], fill=(205, 205, 205, 255), width=1)

        value_text = format_decimal(value, 2)

        bbox = draw.textbbox((0, 0), value_text, font=grid_font)
        text_width = bbox[2] - bbox[0]

        draw.text(
            (left - 12 - text_width, y - 8),
            value_text,
            font=grid_font,
            fill=(55, 55, 55, 255),
        )

    # ========================================================
    # AXIS
    # ========================================================

    axis_color = (55, 55, 55, 255)

    draw.line([left, top, left, bottom], fill=axis_color, width=1)
    draw.line([left, bottom, right, bottom], fill=axis_color, width=1)

    # ========================================================
    # GARIS NOL / SUMBU X
    # ========================================================

    zero_y = int(y_position(0))

    if min_value < 0 < max_value:
        draw.line(
            [left, zero_y, right, zero_y],
            fill=(55, 55, 55, 255),
            width=2,
        )

    # ========================================================
    # BATANG
    # ========================================================

    count = len(series)

    spacing = width / count

    bar_width = int(min(95, spacing * 0.62))

    value_font = get_font(14, bold=True)
    label_font = get_font(12, bold=False)

    zero_y = int(y_position(0))

    # jarak angka dari tepi atas bar (px), atur sesuai selera
    padding_atas = 8

    for index, item in enumerate(series):

        value = float(item.nilai_iph)

        center_x = int(left + spacing * (index + 0.5))

        bar_left = int(center_x - bar_width / 2)
        bar_right = int(center_x + bar_width / 2)

        value_y = int(y_position(value))
        value_y = max(top, min(bottom, value_y))

        # ---------------- WARNA BAR ----------------
        if value >= 0:
            bar_color = (34, 197, 94, 255)
        else:
            bar_color = (255, 153, 0, 255)

        # ---------------- GAMBAR BAR ----------------
        bar_top = min(zero_y, value_y)
        bar_bottom = max(zero_y, value_y)

        draw.rectangle(
            [bar_left, bar_top, bar_right, bar_bottom],
            fill=bar_color,
        )

        # ---------------- ERROR BAR ----------------
        errorbar_color = (190, 173, 143, 255)
        errorbar_length = 20
        errorbar_cap_width = 20

        if value >= 0:
            errorbar_far = max(top, value_y - errorbar_length)
        else:
            errorbar_far = min(bottom, value_y + errorbar_length)

        draw.line(
            [center_x, value_y, center_x, errorbar_far],
            fill=errorbar_color,
            width=2,
        )

        draw.line(
            [
                center_x - errorbar_cap_width / 2,
                errorbar_far,
                center_x + errorbar_cap_width / 2,
                errorbar_far,
            ],
            fill=errorbar_color,
            width=2,
        )

        # ---------------- ANGKA NILAI ----------------
        # Di DALAM bar, dekat tepi atas, warna hitam.
        # Kalau bar terlalu pendek, angka pindah ke luar bar.
        nilai_teks = format_decimal(value, 2)

        bbox_teks = draw.textbbox((0, 0), nilai_teks, font=value_font)

        lebar_teks = bbox_teks[2] - bbox_teks[0]
        tinggi_teks = bbox_teks[3] - bbox_teks[1]

        x_teks = center_x - lebar_teks / 2

        padding_dalam = 8

        if value >= 0:
            y_teks = bar_top + padding_dalam - bbox_teks[1]
        else:
            y_teks = (
                bar_bottom
                - padding_dalam
                - tinggi_teks
                - bbox_teks[1]
            )

        draw.text(
            (x_teks, y_teks),
            nilai_teks,
            font=value_font,
            fill=(30, 30, 30, 255),
        )

        # ---------------- LABEL X ----------------
        label_bbox = draw.textbbox((0, 0), labels[index], font=label_font)
        label_width = label_bbox[2] - label_bbox[0]

        draw.text(
            (center_x - label_width / 2, 381),
            labels[index],
            font=label_font,
            fill=(45, 45, 45, 255),
        )


# ============================================================
# GENERATOR UTAMA
# ============================================================

def generate_infografis():

    # ========================================================
    # 1. TEMPLATE
    # ========================================================

    template_path = (
        Path(settings.BASE_DIR)
        / "iph"
        / "static"
        / "iph"
        / "images"
        / TEMPLATE_FILENAME
    )

    if not template_path.exists():

        raise FileNotFoundError(
            "Template infografis tidak ditemukan: "
            f"{template_path}"
        )

    canvas = Image.open(template_path).convert("RGBA")

    # ========================================================
    # 2. REGION
    # ========================================================

    region = Region.objects.get(kode_kabkota=REGION_CODE)

    # ========================================================
    # 3. PERIODE DARI UPLOAD TERBARU
    #
    # Jangan gunakan IPHSeries untuk menentukan periode terbaru.
    # WeeklyIPH berasal dari upload, jadi batch upload terbaru
    # menjadi penentu periode aktif.
    # ========================================================

    latest_data = get_latest_weekly_iph(region)

    if not latest_data:

        raise ValueError(
            "Belum terdapat data IPH. "
            "Silakan upload data terlebih dahulu."
        )

    # ========================================================
    # 4. PERIODE AKTIF
    # ========================================================

    active_period = latest_data.period

    active_year = int(active_period.tahun)
    active_month = int(active_period.bulan)
    active_week = int(active_period.minggu)

    # ========================================================
    # 5. SERIES SAMPAI PERIODE AKTIF SAJA (maks. 4)
    # ========================================================

    latest_series = list(
        IPHSeries.objects
        .filter(
            region=region,
            tahun=active_year,
            bulan=active_month,
            minggu__lte=active_week,
        )
        .order_by("-tahun", "-bulan", "-minggu")[:4]
    )

    # ========================================================
    # 6. FALLBACK LINTAS BULAN
    # ========================================================

    if len(latest_series) < 4:

        existing_ids = {item.id for item in latest_series}

        previous_series = list(
            IPHSeries.objects
            .filter(region=region)
            .filter(tahun__lt=active_year)
            |
            IPHSeries.objects
            .filter(
                region=region,
                tahun=active_year,
                bulan__lt=active_month,
            )
        )

        previous_series = [
            item
            for item in previous_series
            if item.id not in existing_ids
        ]

        previous_series.sort(
            key=lambda item: (
                int(item.tahun),
                int(item.bulan),
                int(item.minggu),
            ),
            reverse=True,
        )

        needed = 4 - len(latest_series)

        latest_series.extend(previous_series[:needed])

    # ========================================================
    # 7. URUTKAN KRONOLOGIS
    # ========================================================

    latest_series.sort(
        key=lambda item: (
            int(item.tahun),
            int(item.bulan),
            int(item.minggu),
        )
    )

    # ========================================================
    # 8. VALIDASI SERIES TERAKHIR
    # ========================================================

    latest_iph = None

    for item in latest_series:

        if (
            int(item.tahun) == active_year
            and int(item.bulan) == active_month
            and int(item.minggu) == active_week
        ):
            latest_iph = item
            break

    if latest_iph is None:

        raise ValueError(
            "Data IPHSeries untuk periode upload terbaru "
            f"M{active_week} "
            f"{month_name(active_month)} "
            f"{active_year} "
            "tidak ditemukan."
        )

    # ========================================================
    # 9. SAMAKAN PERIODE
    # ========================================================

    active_year = int(latest_iph.tahun)
    active_month = int(latest_iph.bulan)
    active_week = int(latest_iph.minggu)

    # ========================================================
    # 10. VALIDASI WEEKLY DATA
    # ========================================================

    if (
        int(latest_data.period.tahun) != active_year
        or int(latest_data.period.bulan) != active_month
        or int(latest_data.period.minggu) != active_week
    ):

        latest_data = (
            WeeklyIPH.objects
            .select_related("period", "region")
            .filter(
                region=region,
                period__tahun=active_year,
                period__bulan=active_month,
                period__minggu=active_week,
            )
            .order_by(F("import_batch_id").desc(nulls_last=True), "-id")
            .first()
        )

    if not latest_data:

        raise ValueError(
            "Data Weekly IPH untuk "
            f"M{active_week} "
            f"{month_name(active_month)} "
            f"{active_year} "
            "tidak ditemukan."
        )

    # ========================================================
    # 11. DATA KOMODITAS
    # ========================================================

    contributions = list(
        CommodityContribution.objects
        .select_related("commodity")
        .filter(weekly_iph=latest_data)
        .order_by("-nilai_andil")[:3]
    )

    # ========================================================
    # 12. PERIODE
    # ========================================================

    period_month = month_name(active_month)
    period_week = roman_week(active_week)
    period_year = active_year

    period_short = f"M{active_week} {period_month} {period_year}"
    period_full = f"Minggu {period_week} {period_month} {period_year}"

    # ========================================================
    # 13. NILAI IPH
    # ========================================================

    latest_value = float(latest_iph.nilai_iph)

    # ========================================================
    # 14. STATUS
    # ========================================================

    status_map = {
        "naik": "Naik",
        "turun": "Turun",
        "stabil": "Stabil",
    }

    status_raw = str(latest_data.status or "").strip().lower()

    status = status_map.get(status_raw, latest_data.status or "-")

    # ========================================================
    # 15. TEKS PERUBAHAN
    # ========================================================

    change_text_map = {
        "naik": "kenaikan",
        "turun": "penurunan",
        "stabil": "kestabilan",
    }

    change_text = change_text_map.get(status_raw, "perubahan")

    # ========================================================
    # 16. DRAW
    # ========================================================

    draw = ImageDraw.Draw(canvas)

    # ========================================================
    # JUDUL
    # ========================================================

    draw.rectangle([48, 18, 980, 62], fill=(255, 255, 255, 255))

    title_font = get_font(25, bold=True)

    title = (
        "PERKEMBANGAN IPH "
        "KABUPATEN CIREBON "
        f"MINGGU {period_week} "
        f"{period_month.upper()} "
        f"{period_year}"
    )

    draw.text(
        (54, 25),
        title,
        font=title_font,
        fill=(218, 123, 47, 255),
    )

    # ========================================================
    # HEADER GRAFIK
    # ========================================================

    draw.rounded_rectangle(
        [210, 63, 640, 107],
        radius=24,
        fill=(40, 160, 82, 255),
    )

    pill_font = get_font(18, bold=True)

    pill_text = "Perkembangan IPH Kabupaten Cirebon"

    bbox = draw.textbbox((0, 0), pill_text, font=pill_font)
    pill_width = bbox[2] - bbox[0]

    draw.text(
        (425 - pill_width / 2, 72),
        pill_text,
        font=pill_font,
        fill=(255, 255, 255, 255),
    )

    # ========================================================
    # GRAFIK
    # ========================================================

    draw_iph_chart(canvas, latest_series)

    # ========================================================
    # 17. HEADER KOMODITAS
    # ========================================================

    draw.rounded_rectangle(
        [810, 104, 1245, 208],
        radius=20,
        fill=(40, 160, 82, 255),
    )

    header_font = get_font(20, bold=True)

    header_line_1_left = "Komoditas dengan "
    header_line_1_highlight = "andil tertinggi"

    bbox_left = draw.textbbox((0, 0), header_line_1_left, font=header_font)
    bbox_highlight = draw.textbbox(
        (0, 0),
        header_line_1_highlight,
        font=header_font,
    )

    total_width = (
        (bbox_left[2] - bbox_left[0])
        + (bbox_highlight[2] - bbox_highlight[0])
    )

    x = 1027 - total_width / 2

    draw.text(
        (x, 116),
        header_line_1_left,
        font=header_font,
        fill=(255, 255, 255, 255),
    )

    x += bbox_left[2] - bbox_left[0]

    draw.text(
        (x, 116),
        header_line_1_highlight,
        font=header_font,
        fill=(255, 235, 0, 255),
    )

    header_line_2 = f"terhadap {change_text} harga pada"

    bbox = draw.textbbox((0, 0), header_line_2, font=header_font)

    draw.text(
        (1027 - (bbox[2] - bbox[0]) / 2, 140),
        header_line_2,
        font=header_font,
        fill=(255, 255, 255, 255),
    )

    bbox = draw.textbbox((0, 0), period_full, font=header_font)

    draw.text(
        (1027 - (bbox[2] - bbox[0]) / 2, 164),
        period_full,
        font=header_font,
        fill=(255, 235, 0, 255),
    )

    # ========================================================
    # 18. KARTU KOMODITAS
    #
    # Kartu (warna + transparansi) sudah ada di template bersih,
    # jadi di sini hanya menulis ikon, nama, dan nilai.
    # ========================================================

    commodity_font = get_font(25, bold=False)
    commodity_value_font = get_font(38, bold=True)

    card_tops = [220, 355, 470]


    for index in range(3):

        if index < len(contributions):

            item = contributions[index]

            commodity_name = item.commodity.nama
            commodity_value = float(item.nilai_andil)

        else:

            commodity_name = "-"
            commodity_value = None

        card_top = card_tops[index]

        # ---------------- ICON ----------------
        paste_commodity_image(
            canvas,
            commodity_name,
            836,
            card_top + 17,
            size=55,
        )

        # ---------------- NILAI ANDIL ----------------
        if commodity_value is not None:
            value_text = format_decimal(commodity_value, 2) + "%"
        else:
            value_text = "-"

        value_bbox = draw.textbbox(
            (0, 0),
            value_text,
            font=commodity_value_font,
        )

        value_width = value_bbox[2] - value_bbox[0]

        # ---------------- NAMA KOMODITAS ----------------
        name_display = title_case_commodity(commodity_name)

        name_x = 910

        name_max_width = 1215 - value_width - 24 - name_x

        name_font = commodity_font

        for shrink_size in [23, 21, 19, 17, 15]:

            candidate_font = get_font(shrink_size, bold=False)

            bbox = draw.textbbox((0, 0), name_display, font=candidate_font)

            name_font = candidate_font

            if (bbox[2] - bbox[0]) <= name_max_width:
                break

        draw.text(
            (name_x, card_top + 33),
            name_display,
            font=name_font,
            fill=(35, 35, 35, 255),
        )

        # ---------------- NILAI ----------------
        draw.text(
            (1215 - value_width, card_top + 26),
            value_text,
            font=commodity_value_font,
            fill=(20, 145, 72, 255),
        )

    # ========================================================
    # 19. INSIGHT TEKS
    #
    # Tidak perlu kotak putih lagi: teks lama sudah dihapus
    # dari template bersih, dan 3 titik warna sudah ada di sana.
    # ========================================================

    body_font = get_font(22, bold=False)
    bold_font = get_font(22, bold=True)

    # ---------------- INSIGHT 1 ----------------
    if status_raw == "naik":
        direction = "kenaikan"
    elif status_raw == "turun":
        direction = "penurunan"
    elif status_raw == "stabil":
        direction = "kondisi stabil"
    else:
        direction = "perubahan"

    latest_value_text = format_decimal(latest_value, 2)

    insight_1_segments = [
        (
            f"IPH {period_full} "
            f"di Kabupaten Cirebon "
            f"mengalami {direction} "
            f"sebesar",
            body_font,
        ),
        (latest_value_text, bold_font),
        (
            "persen dibanding dengan "
            "rata-rata bulan sebelumnya.",
            body_font,
        ),
    ]

    # ---------------- INSIGHT 2 ----------------
    commodity_names = [
        title_case_commodity(item.commodity.nama)
        for item in contributions
    ]

    if commodity_names:

        if len(commodity_names) == 1:

            commodity_text = commodity_names[0]

        elif len(commodity_names) == 2:

            commodity_text = (
                f"{commodity_names[0]} "
                f"dan {commodity_names[1]}"
            )

        else:

            commodity_text = (
                f"{commodity_names[0]}, "
                f"{commodity_names[1]} dan "
                f"{commodity_names[2]}"
            )

        insight_2_segments = [
            (
                f"{change_text.capitalize()} "
                f"IPH {period_full} "
                f"dipicu oleh {change_text} "
                f"harga",
                body_font,
            ),
            (f"{commodity_text}.", bold_font),
        ]

    else:

        insight_2_segments = [
            (
                "Belum terdapat data kontribusi "
                "komoditas pada periode tersebut.",
                body_font,
            ),
        ]

    # ---------------- INSIGHT 3 ----------------
    fluctuation = title_case_commodity(latest_data.fluktuasi_tertinggi)

    insight_3_segments = [
        (
            f"Fluktuasi harga tertinggi "
            f"di Minggu ke-{period_week} "
            f"{period_month} "
            f"{period_year} "
            f"pada komoditas",
            body_font,
        ),
        (f"{fluctuation}.", bold_font),
    ]

    # ========================================================
    # 20. GAMBAR TEKS
    # ========================================================

    current_y = 424

    current_y = draw_justified_mixed(
        draw,
        insight_1_segments,
        96,
        current_y,
        675,
        line_height=31,
    )

    current_y += 8

    current_y = draw_justified_mixed(
        draw,
        insight_2_segments,
        96,
        current_y,
        675,
        line_height=31,
    )

    # ruang untuk 3 titik warna (sudah ada di template)
    current_y += 20

    draw_justified_mixed(
        draw,
        insight_3_segments,
        96,
        current_y,
        675,
        line_height=31,
    )

    # ========================================================
    # 21. SIMPAN HASIL
    # ========================================================

    output_dir = Path(settings.MEDIA_ROOT) / "generated"

    output_dir.mkdir(parents=True, exist_ok=True)

    filename = (
        f"rifora_"
        f"{region.kode_kabkota}_"
        f"{latest_iph.tahun}_"
        f"{latest_iph.bulan}_"
        f"{latest_iph.minggu}.png"
    )

    output_path = output_dir / filename

    canvas.convert("RGB").save(
        output_path,
        "PNG",
        optimize=True,
    )

    return output_path