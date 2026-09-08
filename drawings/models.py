from django.db import models


class Drawing(models.Model):
    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("detecting_rooms", "Detecting rooms"),
        ("pending_review", "Pending review"),
        ("needs_manual_rooms", "Needs manual room boundaries"),
        ("calculating", "Calculating lighting"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    original_file = models.FileField(upload_to="uploads/")
    output_file = models.FileField(upload_to="outputs/", blank=True, null=True)
    preview_image = models.FileField(upload_to="previews/", blank=True, null=True)
    preview_extents = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="uploaded")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Drawing #{self.pk} ({self.status})"


class Room(models.Model):
    ROOM_TYPE_CHOICES = [
        ("office", "Office"),
        ("bedroom", "Bedroom"),
        ("living_room", "Living room"),
        ("kitchen", "Kitchen"),
        ("bathroom", "Bathroom"),
        ("corridor", "Corridor"),
        ("classroom", "Classroom"),
        ("storage", "Storage"),
        ("other", "Other"),
    ]

    drawing = models.ForeignKey(Drawing, related_name="rooms", on_delete=models.CASCADE)
    label = models.CharField(max_length=255, blank=True, default="")
    room_type = models.CharField(max_length=30, choices=ROOM_TYPE_CHOICES, default="other")
    polygon = models.JSONField(help_text="List of [x, y] vertex coordinates, in metres")
    area_sq_m = models.FloatField()
    required_lux = models.FloatField(blank=True, null=True)
    mounting_height_m = models.FloatField(default=2.7)
    confirmed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.label or 'Room'} ({self.room_type}) - {self.area_sq_m:.1f} m2"


class FixtureType(models.Model):
    name = models.CharField(max_length=255)
    luminous_flux_lm = models.FloatField(help_text="Lumen output per fixture")
    wattage_w = models.FloatField(default=120, help_text="Wattage per fixture")
    max_spacing_to_height_ratio = models.FloatField(default=1.2)

    def __str__(self):
        return self.name


class Fixture(models.Model):
    room = models.ForeignKey(Room, related_name="fixtures", on_delete=models.CASCADE)
    fixture_type = models.ForeignKey(FixtureType, on_delete=models.PROTECT)
    x = models.FloatField(help_text="Position in metres")
    y = models.FloatField(help_text="Position in metres")
    tag = models.CharField(max_length=30, blank=True, default="")

    def __str__(self):
        return f"Fixture {self.tag or ''} @ ({self.x:.2f}, {self.y:.2f})"


class Circuit(models.Model):
    CIRCUIT_TYPES = [
        ("lighting", "Lighting"),
        ("socket", "Socket"),
        ("socket_key", "Socket Key"),
    ]
    drawing = models.ForeignKey(Drawing, related_name="circuits", on_delete=models.CASCADE)
    cct_label = models.CharField(max_length=20)
    cct_type = models.CharField(max_length=20, choices=CIRCUIT_TYPES)
    phase = models.CharField(max_length=1)
    n_points = models.IntegerField()
    total_load_w = models.FloatField()
    cable_csa_mm2 = models.FloatField()
    mcb_rating_a = models.FloatField()
    voltage_drop_v = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.cct_label} ({self.cct_type})"


class SmallPowerPoint(models.Model):
    KIND_CHOICES = [("SP", "Socket Point"), ("SK", "Socket Key"), ("SW", "Switch")]
    drawing = models.ForeignKey(Drawing, related_name="small_power_points", on_delete=models.CASCADE)
    tag = models.CharField(max_length=30, blank=True, default="")
    kind = models.CharField(max_length=2, choices=KIND_CHOICES)
    x = models.FloatField()
    y = models.FloatField()
    circuit_no = models.IntegerField(default=0)
    phase = models.CharField(max_length=1, blank=True, default="")
    load_w = models.FloatField(default=150)

    def __str__(self):
        return f"{self.tag or self.kind} @ ({self.x:.2f}, {self.y:.2f})"


class DistributionBoard(models.Model):
    drawing = models.ForeignKey(Drawing, related_name="distribution_boards", on_delete=models.CASCADE)
    label = models.CharField(max_length=50, default="DB")
    x = models.FloatField()
    y = models.FloatField()
    incomer_mcb_a = models.IntegerField(default=30)
    incoming_cable_csa_mm2 = models.FloatField(default=4.0)
    schedule_data = models.JSONField(blank=True, null=True)
    sld_file = models.FileField(upload_to="outputs/sld/", blank=True, null=True)
    report_file = models.FileField(upload_to="outputs/reports/", blank=True, null=True)

    def __str__(self):
        return f"{self.label} @ ({self.x:.2f}, {self.y:.2f})"


class RoomOverride(models.Model):
    """User-requested design changes stored by ATLAS tool calls."""
    room            = models.OneToOneField(Room, related_name="override", on_delete=models.CASCADE)
    n_fixtures      = models.IntegerField(null=True, blank=True)
    required_lux    = models.FloatField(null=True, blank=True)
    fixture_type_id = models.IntegerField(null=True, blank=True)
    notes           = models.TextField(blank=True, default="")
    updated_at      = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Override for {self.room}"
