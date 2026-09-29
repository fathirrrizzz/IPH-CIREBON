from django.contrib import admin

from .models import (
    Region,
    ReportPeriod,
    ImportBatch,
    Commodity,
    WeeklyIPH,
    CommodityContribution,
)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = (
        "kode_kabkota",
        "nama",
        "provinsi",
        "pulau",
    )

    search_fields = (
        "kode_kabkota",
        "nama",
        "provinsi",
    )

    ordering = ("kode_kabkota",)


@admin.register(ReportPeriod)
class ReportPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "tahun",
        "minggu",
        "bulan",
        "tanggal_awal",
        "tanggal_akhir",
    )

    list_filter = (
        "tahun",
        "bulan",
    )

    ordering = (
        "-tahun",
        "-minggu",
    )


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "nama_file",
        "tanggal_import",
        "sheet_name",
        "jumlah_baris",
        "status",
    )

    list_filter = (
        "status",
    )

    search_fields = (
        "nama_file",
        "sheet_name",
    )


@admin.register(Commodity)
class CommodityAdmin(admin.ModelAdmin):
    list_display = (
        "nama",
        "nama_normalized",
    )

    search_fields = (
        "nama",
        "nama_normalized",
    )


@admin.register(WeeklyIPH)
class WeeklyIPHAdmin(admin.ModelAdmin):
    list_display = (
        "region",
        "period",
        "perubahan_iph",
        "fluktuasi_tertinggi",
        "nilai_cv",
        "disparitas_harga",
        "status",
    )

    list_filter = (
        "status",
        "period__tahun",
        "period__bulan",
    )

    search_fields = (
        "region__kode_kabkota",
        "region__nama",
        "fluktuasi_tertinggi",
    )


@admin.register(CommodityContribution)
class CommodityContributionAdmin(admin.ModelAdmin):
    list_display = (
        "weekly_iph",
        "commodity",
        "nilai_andil",
    )

    search_fields = (
        "commodity__nama",
        "weekly_iph__region__kode_kabkota",
    )
