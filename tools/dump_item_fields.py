"""Dump the BingBong prefabs' Item component fields.

CharacterItems computes where the held item sits from `Item.defaultPos`:

    animationItemTransform.position = animationLookTransform.TransformPoint(defaultPos)

and CharacterAnimations' IK path then places the hands at

    animationItemTransform.TransformPoint(handAnchorLocal * item.lossyScale)

So `defaultPos` and the relationship between `animationItemTransform` and the item decide
where the hands land. This reads those exact values out of the prefab.
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
TARGETS = ("BingBong", "BingBong_Prop Variant")

INTERESTING = ("defaultPos", "defaultForward", "rightHandOnly", "gliderHold",
               "holdForce", "holdTorque", "offset", "scale")


def resolve_script(env, objects, mb):
    ref = getattr(mb, "m_Script", None)
    if ref is None:
        return "?"
    try:
        return ref.read().m_ClassName
    except Exception:
        return "?"


def main():
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in env.objects}

    for o in env.objects:
        if o.type.name != "GameObject":
            continue
        try:
            gd = o.read()
        except Exception:
            continue
        if gd.m_Name not in TARGETS:
            continue

        print(f"=== {gd.m_Name} (path_id={o.path_id}) ===")
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objects.get(comp.path_id)
            if cr is None or cr.type.name != "MonoBehaviour":
                continue
            try:
                mb = cr.read()
            except Exception as exc:
                print(f"  <unreadable: {exc}>")
                continue
            cls = resolve_script(env, objects, mb)
            fields = {}
            for name in dir(mb):
                if name.startswith("_"):
                    continue
                try:
                    val = getattr(mb, name)
                except Exception:
                    continue
                if name in INTERESTING:
                    if hasattr(val, "x") and hasattr(val, "y"):
                        fields[name] = f"({val.x:+.4f},{val.y:+.4f},{val.z:+.4f})"
                    else:
                        fields[name] = val
            if cls not in ("?", "BingBong", "BingBongsVisuals", "PhotonCleanupHelper") \
                    or fields:
                print(f"  [{cls}] {fields}")
        print()


if __name__ == "__main__":
    main()
