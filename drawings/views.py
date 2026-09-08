import json

from django.conf import settings
from django.forms import modelformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from shapely.geometry import Polygon

from .forms import DrawingUploadForm, RoomReviewForm
from .models import Drawing, Room
from .services import dxf_preview, room_classifier, standards
from .tasks import calculate_and_place, parse_and_detect_rooms
import logging


def home(request):
    
    return render(request, "drawings/home.html")

def upload_view(request):
    if request.method == "POST":
        form = DrawingUploadForm(request.POST, request.FILES)
        if form.is_valid():
            drawing = Drawing.objects.create(original_file=form.cleaned_data["file"])
            parse_and_detect_rooms.delay(drawing.pk)
            return redirect("drawings:status", drawing_id=drawing.pk)
    else:
        form = DrawingUploadForm()

    return render(request, "drawings/upload.html", {"form": form})


def status_view(request, drawing_id):
    drawing = get_object_or_404(Drawing, pk=drawing_id)

    if drawing.status == "pending_review":
        return redirect("drawings:review_rooms", drawing_id=drawing.pk)
    if drawing.status == "needs_manual_rooms":
        return render(request, "drawings/needs_manual_rooms.html", {"drawing": drawing})
    if drawing.status == "done":
        return redirect("drawings:result", drawing_id=drawing.pk)

    # Still processing (or failed) -- the template below polls by simply
    # refreshing itself every few seconds and re-checking drawing.status.
    return render(request, "drawings/status.html", {"drawing": drawing})


def review_rooms_view(request, drawing_id):
    drawing = get_object_or_404(Drawing, pk=drawing_id)
    RoomFormSet = modelformset_factory(Room, form=RoomReviewForm, extra=0)

    if request.method == "POST":
        formset = RoomFormSet(request.POST, queryset=drawing.rooms.all())
        if formset.is_valid():
            formset.save()
            calculate_and_place.delay(drawing.pk)
            return redirect("drawings:status", drawing_id=drawing.pk)
    else:
        formset = RoomFormSet(queryset=drawing.rooms.all())

    return render(request, "drawings/review_rooms.html", {"drawing": drawing, "formset": formset})


def trace_rooms_view(request, drawing_id):
    drawing = get_object_or_404(Drawing, pk=drawing_id)

    if request.method == "POST":
        return _submit_traced_rooms(request, drawing)

    if not drawing.preview_image:
        # render_drawing_preview hasn't finished yet (or hasn't been
        # triggered) -- show a waiting page that polls, same pattern as
        # the general status page.
        return render(request, "drawings/trace_rooms_waiting.html", {"drawing": drawing})

    return render(request, "drawings/trace_rooms.html", {
        "drawing": drawing,
        "extents_json": json.dumps(drawing.preview_extents),
    })


def _submit_traced_rooms(request, drawing):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body."}, status=400)

    extents = drawing.preview_extents
    if not extents:
        return JsonResponse({"error": "No preview extents available for this drawing."}, status=400)

    scale = getattr(settings, "DRAWING_UNIT_SCALE", 1.0)
    created = 0
    skipped = []

    for index, room_data in enumerate(payload.get("rooms", []), start=1):
        points_px = room_data.get("points", [])
        label = (room_data.get("label") or "").strip()
        display_name = label or f"Room {index}"

        if len(points_px) < 3:
            skipped.append(f"{display_name}: fewer than 3 points")
            continue

        world_points = [dxf_preview.pixel_to_world(px, py, extents) for px, py in points_px]
        polygon_m = [(x * scale, y * scale) for x, y in world_points]

        shape = Polygon(polygon_m)
        if not shape.is_valid or shape.area <= 0:
            skipped.append(f"{display_name}: self-intersecting or zero-area boundary")
            continue

        room_type = room_classifier.classify_room_type(label)

        Room.objects.create(
            drawing=drawing,
            label=label,
            room_type=room_type,
            polygon=list(shape.exterior.coords),
            area_sq_m=shape.area,
            required_lux=standards.get_required_lux(room_type),
        )
        created += 1

    if created == 0:
        detail = "; ".join(skipped) if skipped else "each room needs at least 3 points."
        return JsonResponse({"error": f"No valid rooms were traced -- {detail}"}, status=400)

    drawing.status = "pending_review"
    drawing.save(update_fields=["status"])
    return JsonResponse({
        "redirect": reverse("drawings:review_rooms", args=[drawing.pk]),
        "warnings": skipped,
    })


def chat_view(request, drawing_id=None):
    return render(request, "drawings/chat.html", {"drawing_id": drawing_id or ""})


def chat_api_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        payload    = json.loads(request.body)
        message    = payload.get("message", "").strip()
        history    = payload.get("history", [])
        drawing_id = payload.get("drawing_id")
    except Exception:
        return JsonResponse({"error": "Invalid request body"}, status=400)

    if not message:
        return JsonResponse({"error": "Empty message"}, status=400)

    # Build drawing context if a drawing_id was passed
    context_block = ""
    if drawing_id:
        try:
            drawing = Drawing.objects.get(pk=drawing_id)
            rooms   = drawing.rooms.filter(confirmed=True)
            db_obj  = drawing.distribution_boards.first()
            lines   = [f"Current project drawing #{drawing_id}:"]
            for r in rooms:
                lines.append(f"  - {r.label} ({r.room_type}): {r.area_sq_m:.1f} m², "
                             f"{r.required_lux} lux, {r.fixtures.count()} fixtures")
            if db_obj:
                sched = db_obj.schedule_data or {}
                lines.append(f"  DB: {db_obj.incomer_mcb_a}A incomer, "
                             f"total load {sched.get('total_w', '?')} W")
            context_block = "\n".join(lines)
        except Exception:
            pass

    system_prompt = """You are a senior professional electrical engineer with 25 years of experience in residential and commercial electrical design, specialising in:

- Lighting design — lumen method, point-by-point calculation, EN 12464-1 / CIBSE LG standards
- Small power design — socket layout, load estimation, BS 1363 / BS 546
- Distribution board design — load scheduling, phase balancing, protection coordination
- Cable sizing — current-carrying capacity, voltage drop (BS7671 Appendix 4), IEE guidance
- BS7671 (18th Edition IEE Wiring Regulations) compliance
- Nigerian Electricity Supply Regulations and local practice
- Single line diagrams, DB schedules, design reports

You give precise, professional answers. When doing calculations, show every step with units. When referencing standards, cite the specific regulation or table number. You are direct and technically rigorous — you don't hedge unnecessarily. You speak to the user as a fellow engineer.

If the user asks about their specific drawing project, use the context provided."""

    if context_block:
        system_prompt += f"\n\nPROJECT CONTEXT:\n{context_block}"

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_API_KEY)
        contents = _history_to_gemini_contents(history[-20:]) + [
            {"role": "user", "parts": [{"text": message}]}
        ]
        resp = client.models.generate_content(
            model=GOOGLE_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=1500,
            ),
        )
        reply = resp.text
    except Exception as exc:
        return JsonResponse({"error": f"AI service error: {exc}"}, status=500)

    return JsonResponse({"response": reply})


def result_view(request, drawing_id):
    drawing = get_object_or_404(Drawing, pk=drawing_id)
    db_obj  = drawing.distribution_boards.first()
    return render(request, "drawings/result.html", {
        "drawing": drawing,
        "db_obj":  db_obj,
    })


# ═══════════════════════════════════════════════════════════════
#  ATLAS — AI design modification with function-calling + live preview
# ═══════════════════════════════════════════════════════════════

import io
import logging

logger = logging.getLogger(__name__)

# ─── Google Gemini API key ──────────────────────────────────────────────
# Get a key from https://aistudio.google.com/app/apikey and paste it
# between the quotes below. This applies to both chat_api_view above and
# atlas_api_view below.
GOOGLE_API_KEY = "AQ.Ab8RN6Ie3zJUAT4prfba3W_uuOSrrc5v7rn9mzFwZVBnhJaRag"
GOOGLE_MODEL   = "gemini-2.5-flash"


def _history_to_gemini_contents(history):
    """Converts Anthropic-style history ({"role": "user"/"assistant", ...})
    into Gemini's contents format ({"role": "user"/"model", "parts": [...]})."""
    contents = []
    for turn in history:
        role = "model" if turn.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})
    return contents


# Same three tools, same names, same arguments -- just expressed as Gemini
# function declarations instead of Anthropic's input_schema. The parameter
# shape (type/properties/required) is the same JSON-schema style, so this
# is a near-literal translation.
ATLAS_TOOLS_GOOGLE = [
    {
        "name": "set_fixture_count",
        "description": ("Override the number of lighting fixtures in a specific room. "
                        "Use when the user wants more or fewer lights than auto-calculated."),
        "parameters": {
            "type": "object",
            "properties": {
                "room_id":    {"type": "integer", "description": "Room database ID"},
                "n_fixtures": {"type": "integer", "description": "Number of fixtures to place"},
                "reason":     {"type": "string"},
            },
            "required": ["room_id", "n_fixtures"],
        },
    },
    {
        "name": "set_room_illuminance",
        "description": "Change the target illuminance (lux) for a room.",
        "parameters": {
            "type": "object",
            "properties": {
                "room_id":      {"type": "integer"},
                "required_lux": {"type": "number", "description": "Target lux level"},
                "reason":       {"type": "string"},
            },
            "required": ["room_id", "required_lux"],
        },
    },
    {
        "name": "reset_room_to_auto",
        "description": "Remove any overrides for a room and restore auto-calculated values.",
        "parameters": {
            "type": "object",
            "properties": {"room_id": {"type": "integer"}},
            "required": ["room_id"],
        },
    },
    {
        "name": "get_design_summary",
        "description": "Get the current design state: all rooms, fixture counts, and circuit info.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]


def _run_atlas_tool(name, inp, drawing):
    from .models import Room, RoomOverride
    from .services.design_modifier import get_design_summary

    if name == "get_design_summary":
        return get_design_summary(drawing)

    if name == "set_fixture_count":
        try:
            room = Room.objects.get(pk=inp["room_id"], drawing=drawing)
        except Room.DoesNotExist:
            return {"error": f"Room {inp['room_id']} not found"}
        ov, _ = RoomOverride.objects.get_or_create(room=room)
        ov.n_fixtures = inp["n_fixtures"]
        ov.notes = inp.get("reason", "")
        ov.save()
        return {"success": True, "room": room.label,
                "message": f"Set {room.label} to {inp['n_fixtures']} fixture(s). Recalculating…"}

    if name == "set_room_illuminance":
        try:
            room = Room.objects.get(pk=inp["room_id"], drawing=drawing)
        except Room.DoesNotExist:
            return {"error": f"Room {inp['room_id']} not found"}
        ov, _ = RoomOverride.objects.get_or_create(room=room)
        ov.required_lux = inp["required_lux"]
        ov.notes = inp.get("reason", "")
        ov.save()
        return {"success": True, "room": room.label,
                "message": f"Set {room.label} illuminance to {inp['required_lux']} lux."}

    if name == "reset_room_to_auto":
        try:
            room = Room.objects.get(pk=inp["room_id"], drawing=drawing)
        except Room.DoesNotExist:
            return {"error": f"Room {inp['room_id']} not found"}
        from .models import RoomOverride
        RoomOverride.objects.filter(room=room).delete()
        return {"success": True, "room": room.label,
                "message": f"Override removed for {room.label}. Auto-calculation restored."}

    return {"error": f"Unknown tool: {name}"}


def atlas_view(request, drawing_id):
    drawing = get_object_or_404(Drawing, pk=drawing_id)
    return render(request, "drawings/atlas.html", {"drawing": drawing})


def atlas_api_view(request, drawing_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    drawing = get_object_or_404(Drawing, pk=drawing_id)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    message = payload.get("message", "").strip()
    history = payload.get("history", [])
    if not message:
        return JsonResponse({"error": "Empty message"}, status=400)

    # Everything below can throw for reasons unrelated to the AI call itself
    # (bad tool args, DB errors, non-serializable results) -- catch all of
    # it so the frontend always gets JSON back, never a raw 500 HTML page.
    try:
        from .services.design_modifier import get_design_summary
        summary = get_design_summary(drawing)

        rooms_ctx = "\n".join(
            f"  Room ID={r['id']}: {r['label']} ({r['room_type']}) | "
            f"{r['area_sq_m']}m² | {r['required_lux']} lux target | "
            f"{r['n_fixtures']} fixture(s) "
            f"{'[OVERRIDE: '+str(r['override_fixtures'])+']' if r['override_fixtures'] else '[auto]'} | "
            f"Tags: {', '.join(r['fixture_tags'])}"
            for r in summary["rooms"]
        )
        ft_ctx = "\n".join(
            f"  ID={ft['id']}: {ft['name']} — {ft['lumens']} lm, {ft['watts']}W"
            for ft in summary["fixture_types"]
        )

        system = f"""You are ATLAS, a professional electrical engineer AI embedded in a lighting design automation system. You have tool access to modify the design in real time.

CURRENT DESIGN — Drawing #{drawing_id}:
{rooms_ctx}

AVAILABLE FIXTURE TYPES:
{ft_ctx}

When the user requests a change (e.g. "use 3 bulbs in the bedroom"), call the appropriate tool immediately. After calling the tool, explain:
1. What you changed
2. What the new achieved lux level will be (calculate it: N × F × UF × MF / A)
3. Whether it meets the required illuminance standard (EN 12464-1)
4. Any professional recommendation if the change results in under-illumination

Use the lumen method: N = (E × A) / (F × UF × MF) where MF = 0.8.
Reference BS7671 and EN 12464-1 when relevant. Be precise and professional."""

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_API_KEY)
        contents = _history_to_gemini_contents(history[-16:]) + [
            {"role": "user", "parts": [{"text": message}]}
        ]
        resp = client.models.generate_content(
            model=GOOGLE_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=1500,
                tools=[types.Tool(function_declarations=ATLAS_TOOLS_GOOGLE)],
            ),
        )

        tool_results = []
        needs_regen  = False
        text_parts   = []

        candidate = resp.candidates[0] if resp.candidates else None
        parts = candidate.content.parts if candidate and candidate.content else []

        for part in parts:
            fc = getattr(part, "function_call", None)
            if fc is not None:
                tool_input = dict(fc.args) if fc.args else {}
                result = _run_atlas_tool(fc.name, tool_input, drawing)
                tool_results.append({"tool": fc.name, "input": tool_input, "result": result})
                if fc.name in ("set_fixture_count", "set_room_illuminance", "reset_room_to_auto"):
                    needs_regen = True
            elif getattr(part, "text", None):
                text_parts.append(part.text)

        task_id = None
        if needs_regen:
            from .tasks import atlas_regenerate
            task = atlas_regenerate.delay(drawing_id)
            task_id = getattr(task, "id", None)

        text = "\n\n".join(text_parts)

        # json.dumps(..., default=str) as a safety net -- if a tool result
        # ever contains something JsonResponse can't natively serialize
        # (Decimal, datetime, a model instance slipped in by mistake), this
        # coerces it to a string instead of throwing an unhandled 500.
        payload_out = {
            "response":     text or "(processing…)",
            "tool_results": tool_results,
            "task_id":      task_id,
            "needs_regen":  needs_regen,
        }
        safe_payload = json.loads(json.dumps(payload_out, default=str))
        return JsonResponse(safe_payload)

    except Exception as exc:
        logger.exception("ATLAS request failed for drawing %s", drawing_id)
        return JsonResponse({"error": f"ATLAS error: {exc}"}, status=500)


def atlas_task_status_view(request, task_id):
    try:
        from celery.result import AsyncResult
        r = AsyncResult(task_id)
        if r.ready():
            return JsonResponse({"status": "done" if r.successful() else "failed",
                                 "log": r.result.get("log", []) if r.successful() else [],
                                 "error": str(r.result) if not r.successful() else None})
        if r.state == "PROGRESS":
            return JsonResponse({"status": "progress",
                                 "message": r.info.get("status", "")})
        return JsonResponse({"status": "pending"})
    except Exception:
        return JsonResponse({"status": "done"})  # eager mode


def atlas_preview_view(request, drawing_id):
    drawing = get_object_or_404(Drawing, pk=drawing_id)
    if not drawing.output_file:
        return JsonResponse({"error": "No output yet"}, status=404)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import ezdxf
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        from django.http import HttpResponse

        doc = ezdxf.readfile(drawing.output_file.path)
        fig = plt.figure(figsize=(16, 12), facecolor="white")
        ax  = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor("white"); ax.axis("off")
        Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(
            doc.modelspace(), finalize=True)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return HttpResponse(buf.read(), content_type="image/png")
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)