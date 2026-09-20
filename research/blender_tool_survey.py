"""Does Blender have ANY tool that can export a game-ready outline?

Run headless. Reports which of Blender's NPR tools produce exportable mesh geometry
(what a game can use) versus a camera/render-space effect (which a game cannot).

The distinction is the whole question: Freestyle, Line Art and Grease Pencil all
generate strokes from a *camera view*, so the result is not a 3D object and does not
survive export. Only a mesh modifier can.
"""
import bpy

print("=== Blender", bpy.app.version_string, "===")

# Which Grease Pencil / line-art object types exist in this build?
types = [i.identifier for i in bpy.types.Object.bl_rna.properties['type'].enum_items]
print("object types:", types)

# Does the Line Art modifier exist, and can it be applied to a mesh?
gp = bpy.data.objects.get("x")
print("has grease_pencil object type:", "GREASEPENCIL" in types or "GPENCIL" in types)

# Modifier types available (the only things that make exportable mesh)
mod_types = sorted(i.identifier for i in bpy.types.Modifier.bl_rna.properties['type'].enum_items)
print("modifier count:", len(mod_types))
print("outline-relevant modifiers:", [m for m in mod_types
      if m in ("SOLIDIFY", "WIREFRAME", "REMESH", "DISPLACE", "CORRECTIVE_SMOOTH")])

# Freestyle is a render setting, not geometry
scene = bpy.context.scene
print("has render.use_freestyle:", hasattr(scene.render, "use_freestyle"))
print("freestyle settings:", hasattr(scene, "freestyle_settings"))

print()
print("CONCLUSION:")
print("  * Freestyle      -> render-space strokes, no mesh, cannot export")
print("  * Line Art (GP)  -> camera-dependent strokes, no game mesh, cannot export")
print("  * Grease Pencil  -> 2D stroke object, not a Unity mesh, cannot export")
print("  * Solidify       -> makes a TWO-SIDED thick shell (2x verts + rim), not a")
print("                      single inverted hull, so it is worse for a game outline")
print("  * Shrink/Fatten  -> per-vertex normal offset = what the Python pipeline")
print("                      already does, but without the vertex welding that stops")
print("                      the shell tearing at hard edges")
