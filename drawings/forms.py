from django import forms

from .models import Room


class DrawingUploadForm(forms.Form):
    file = forms.FileField(help_text="DXF file containing the architectural drawing")


class RoomReviewForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["label", "room_type", "required_lux", "mounting_height_m", "confirmed"]
