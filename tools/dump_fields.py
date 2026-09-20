"""Dump MonoBehaviour fields (with script names) and mesh bounds for the BingBong prefab."""
import os
import sys

import numpy as np
import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def read_mesh_bounds(env, name):
    for o in env.objects:
        if o.type.name != "Mesh":
            continue
        try:
            d = o.read()
        except Exception:
            continue
        if d.m_Name != name:
            continue
        aabb = d.m_LocalAABB
        if hasattr(aabb, "m_Center"):
            c, e = aabb.m_Center, aabb.m_Extent
        else:
            c, e = aabb.center, aabb.extent
        print(f"  Mesh '{name}': centre=({c.x:.4f},{c.y:.4f},{c.z:.4f})"
              f" size=({e.x*2:.4f},{e.y*2:.4f},{e.z*2:.4f})")


def dump_behaviour_fields(env, root_go_id, max_depth=8):
    objs = {o.path_id: o for o in env.objects}
    seen = set()

    def walk(go_reader, depth):
        if depth > max_depth or go_reader.path_id in seen:
            return
        seen.add(go_reader.path_id)
        gd = go_reader.read()
        pad = "  " * depth
        tr = None
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objs.get(comp.path_id)
            if cr is None:
                continue
            typ = cr.type.name
            try:
                cd = cr.read()
            except Exception:
                continue
            if typ == "MonoBehaviour":
                sc = cd.m_Script
                sn = sc.read().m_ClassName if sc else "?"
                fields = []
                for attr in dir(cd):
                    if attr.startswith("m_") or attr.startswith("_"):
                        continue
                    if attr in ("serializedTypeNames",):
                        continue
                    try:
                        v = getattr(cd, attr)
                    except Exception:
                        continue
                    if isinstance(v, (int, float, str, bool)):
                        fields.append(f"{attr}={v!r}")
                    elif hasattr(v, "path_id"):
                        try:
                            target = v.read()
                            tn = getattr(target, "m_Name", None) or getattr(target, "name", "?")
                        except Exception:
                            tn = "?"
                        fields.append(f"{attr}->{tn}")
                    elif isinstance(v, (list, tuple)) and v and all(hasattr(x, 'path_id') for x in v):
                        names = []
                        for x in v[:8]:
                            try:
                                names.append(x.read().m_Name)
                            except Exception:
                                names.append("?")
                        fields.append(f"{attr}[{len(v)}]={names}")
                print(f"{pad}<MonoBehaviour:{sn}>")
                for f in fields:
                    print(f"{pad}    {f}")
            elif typ == "AudioSource":
                ac = getattr(cd, "m_audioClip", None)
                try:
                    cn = ac.read().m_Name if ac else None
                except Exception:
                    cn = "?"
                vol = getattr(cd, "m_Volume", getattr(cd, "Volume", "?"))
                loop = getattr(cd, "m_Loop", getattr(cd, "Loop", "?"))
                awake = getattr(cd, "m_PlayOnAwake", getattr(cd, "PlayOnAwake", "?"))
                spatial = getattr(cd, "m_SpatialBlend", getattr(cd, "SpatialBlend", "?"))
                print(f"{pad}<AudioSource> clip={cn} vol={vol} loop={loop}"
                      f" awake={awake} spatial={spatial}")
            elif typ == "Transform":
                tr = cd
                print(f"{pad}<Transform> {gd.m_Name} pos={cd.m_LocalPosition} scale={cd.m_LocalScale}")
            elif typ in ("MeshFilter", "MeshRenderer", "SkinnedMeshRenderer", "Animator", "PhotonView"):
                print(f"{pad}<{typ}>")
        if tr is None:
            return
        for ch in tr.m_Children:
            if ch is None:
                continue
            try:
                cgo = ch.read()
            except Exception:
                continue
            ref = getattr(cgo, "m_GameObject", None)
            if ref:
                walk(objs[ref.path_id], depth + 1)

    walk(objs[root_go_id], 0)


def main():
    env = UnityPy.load(os.path.join(GAME_DATA, "resources.assets"))
    print("=== mesh bounds ===")
    for n in ("BingBong", "Lip Top", "Lip Bottom"):
        read_mesh_bounds(env, n)

    print()
    print("=== prefab behaviour fields (BingBong_Prop Variant) ===")
    for o in env.objects:
        if o.type.name != "GameObject":
            continue
        try:
            d = o.read()
        except Exception:
            continue
        if d.m_Name == "BingBong_Prop Variant":
            dump_behaviour_fields(env, o.path_id)
            break


if __name__ == "__main__":
    main()
