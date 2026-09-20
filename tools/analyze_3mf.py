import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict

import numpy as np

MODELS = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models"
NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
NS_P = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"


def parse_model(path):
    """Return list of (object_id, verts Nx3, faces Mx3) for each object in each .model entry."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not (name.startswith("3D/") and name.endswith(".model")):
                continue
            root = ET.fromstring(z.read(name).decode("utf-8", "replace"))
            for obj in root.iter(f"{NS}object"):
                oid = obj.get("id")
                verts, faces = [], []
                for mesh in obj.iter(f"{NS}mesh"):
                    for v in mesh.iter(f"{NS}vertex"):
                        verts.append((float(v.get("x")), float(v.get("y")), float(v.get("z"))))
                    for t in mesh.iter(f"{NS}triangle"):
                        faces.append((int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))))
                comps = []
                for c in obj.iter(f"{NS}component"):
                    tr = c.get("transform", "")
                    vals = [float(x) for x in tr.split()] if tr else None
                    comps.append((c.get(f"{NS_P}path"), c.get("objectid"), vals))
                if verts or comps:
                    out[(name, oid)] = dict(verts=np.array(verts, dtype=np.float64) if verts else None,
                                            faces=np.array(faces, dtype=np.int64) if faces else None,
                                            comps=comps)
    return out


def dump(path, label):
    print("=" * 78)
    print("FILE:", label)
    print("=" * 78)
    objs = parse_model(path)
    for (entry, oid), d in objs.items():
        V, F = d["verts"], d["faces"]
        line = f"  {entry} obj={oid}"
        if V is not None:
            line += f"  verts={len(V)} tris={len(F)}"
            line += f"  bbox=({V.min(axis=0).round(2)} .. {V.max(axis=0).round(2)})"
        if d["comps"]:
            line += f"  components={len(d['comps'])}"
        print(line)
        if d["comps"]:
            for p, oid2, tr in d["comps"]:
                print(f"      -> {p} obj={oid2} T={[round(x,2) for x in tr] if tr else None}")

    # materials / filament colors
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.endswith("model_settings.config"):
                txt = z.read(n).decode("utf-8", "replace")
                for m in re.finditer(r'<part id="(\d+)"[^>]*>(.*?)</part>', txt, re.S):
                    pid, body = m.group(1), m.group(2)
                    nm = re.search(r'key="name" value="([^"]*)"', body)
                    ex = re.search(r'key="extruder" value="([^"]*)"', body)
                    fc = re.search(r'face_count="(\d+)"', body)
                    print(f"    part {pid}: name={nm.group(1) if nm else '?'} extruder={ex.group(1) if ex else '?'} faces={fc.group(1) if fc else '?'}")
            if n.endswith("project_settings.config"):
                txt = z.read(n).decode("utf-8", "replace")
                for key in ("filament_colour", "filament_type", "filament_settings_id", "filament_ids"):
                    for m in re.finditer(r'"' + key + r'"\s*:\s*\[([^\]]*)\]', txt):
                        print(f"    {key} = [{m.group(1)}]")


if __name__ == "__main__":
    dump(os.path.join(MODELS, "miffy.3mf"), "MIFFY")
    dump(os.path.join(MODELS, "zichaoxiong.3mf"), "ZICHAOXIONG")
