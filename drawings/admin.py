from django.contrib import admin

from .models import Circuit, DistributionBoard, Drawing, Fixture, FixtureType, Room, SmallPowerPoint


@admin.register(Drawing)
class DrawingAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_at", "updated_at")
    list_filter = ("status",)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("id", "drawing", "label", "room_type", "area_sq_m", "required_lux", "confirmed")
    list_filter = ("room_type", "confirmed")


@admin.register(FixtureType)
class FixtureTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "luminous_flux_lm", "max_spacing_to_height_ratio")


@admin.register(Fixture)
class FixtureAdmin(admin.ModelAdmin):
    list_display = ("id", "room", "fixture_type", "x", "y")


@admin.register(Circuit)
class CircuitAdmin(admin.ModelAdmin):
    list_display = ("id", "drawing", "cct_label", "cct_type", "phase", "n_points", "mcb_rating_a")


@admin.register(SmallPowerPoint)
class SmallPowerPointAdmin(admin.ModelAdmin):
    list_display = ("id", "drawing", "tag", "kind", "x", "y")


@admin.register(DistributionBoard)
class DistributionBoardAdmin(admin.ModelAdmin):
    list_display = ("id", "drawing", "label", "x", "y", "incomer_mcb_a")
