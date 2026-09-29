from django.db import models


class Region(models.Model):
    kode_kabkota = models.CharField(
        max_length=10,
        unique=True,
    )

    nama = models.CharField(
        max_length=150,
    )

    provinsi = models.CharField(
        max_length=100,
        blank=True,
    )

    pulau = models.CharField(
        max_length=50,
        blank=True,
    )

    class Meta:
        db_table = "region"
        ordering = ["kode_kabkota"]

    def __str__(self):
        return f"{self.kode_kabkota} - {self.nama}"


class ReportPeriod(models.Model):
    tahun = models.PositiveIntegerField()

    minggu = models.PositiveIntegerField()

    bulan = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    tanggal_awal = models.DateField(
        blank=True,
        null=True,
    )

    tanggal_akhir = models.DateField(
        blank=True,
        null=True,
    )

    label = models.CharField(
        max_length=100,
    )

    class Meta:
        db_table = "report_period"
        ordering = ["-tahun", "-minggu"]

        constraints = [
            models.UniqueConstraint(
                fields=("tahun", "bulan", "minggu"),
                name="unique_report_period",
            ),
        ]

    def __str__(self):
        return self.label


class ImportBatch(models.Model):
    nama_file = models.CharField(
        max_length=255,
    )

    tanggal_import = models.DateTimeField(
        auto_now_add=True,
    )

    sheet_name = models.CharField(
        max_length=100,
        blank=True,
    )

    jumlah_baris = models.PositiveIntegerField(
        default=0,
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("proses", "Proses"),
            ("berhasil", "Berhasil"),
            ("gagal", "Gagal"),
        ],
        default="proses",
    )

    pesan_error = models.TextField(
        blank=True,
    )

    class Meta:
        db_table = "import_batch"
        ordering = ["-tanggal_import"]

    def __str__(self):
        return self.nama_file


class Commodity(models.Model):
    nama = models.CharField(
        max_length=150,
        unique=True,
    )

    nama_normalized = models.CharField(
        max_length=150,
        unique=True,
    )

    class Meta:
        db_table = "commodity"
        ordering = ["nama"]

    def __str__(self):
        return self.nama


class WeeklyIPH(models.Model):
    perubahan_iph = models.DecimalField(
        max_digits=10,
        decimal_places=4,
    )

    fluktuasi_tertinggi = models.CharField(
        max_length=150,
        blank=True,
    )

    nilai_cv = models.DecimalField(
        max_digits=15,
        decimal_places=9,
        blank=True,
        null=True,
    )

    disparitas_harga = models.DecimalField(
        max_digits=15,
        decimal_places=9,
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("naik", "Naik"),
            ("turun", "Turun"),
            ("stabil", "Stabil"),
        ],
    )

    upaya_pemda = models.TextField(
        blank=True,
    )

    saran_pemda = models.TextField(
        blank=True,
    )

    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.PROTECT,
        related_name="weekly_iph",
    )

    period = models.ForeignKey(
        ReportPeriod,
        on_delete=models.PROTECT,
        related_name="weekly_iph",
    )

    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name="weekly_iph",
    )

    class Meta:
        db_table = "weekly_iph"
        ordering = ["-period", "region"]

        constraints = [
            models.UniqueConstraint(
                fields=("region", "period"),
                name="unique_region_period",
            ),
        ]

    def __str__(self):
        return f"{self.region.nama} - {self.period.label}"


class CommodityContribution(models.Model):
    nilai_andil = models.DecimalField(
        max_digits=15,
        decimal_places=9,
    )

    commodity = models.ForeignKey(
        Commodity,
        on_delete=models.PROTECT,
        related_name="contributions",
    )

    weekly_iph = models.ForeignKey(
        WeeklyIPH,
        on_delete=models.CASCADE,
        related_name="commodity_contributions",
    )

    class Meta:
        db_table = "commodity_contribution"
        ordering = ["id"]

        constraints = [
            models.UniqueConstraint(
                fields=("weekly_iph", "commodity"),
                name="unique_weekly_commodity",
            ),
        ]

    def __str__(self):
        return f"{self.commodity.nama} - {self.weekly_iph}"


class IPHSeries(models.Model):
    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name="series_iph",
    )

    tahun = models.PositiveIntegerField()
    bulan = models.PositiveIntegerField()
    minggu = models.PositiveIntegerField()

    nilai_iph = models.DecimalField(
        max_digits=10,
        decimal_places=4,
    )

    class Meta:
        db_table = "iph_series"
        ordering = ["tahun", "bulan", "minggu"]

        constraints = [
            models.UniqueConstraint(
                fields=["region", "tahun", "bulan", "minggu"],
                name="unique_series_region_period",
            )
        ]

    def __str__(self):
        return (
            f"{self.region.nama} - "
            f"{self.tahun} M{self.minggu}/{self.bulan}"
        )


class UserProfile(models.Model):
    STATUS_CHOICES = [
        ("menunggu", "Menunggu Validasi"),
        ("disetujui", "Disetujui"),
        ("ditolak", "Ditolak"),
    ]

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="profile",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="menunggu",
    )

    tanggal_validasi = models.DateTimeField(
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "user_profile"

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.get_status_display()}"
        )