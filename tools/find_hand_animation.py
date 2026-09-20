"""Look for animation clips that drive the plush's Hand_L / Hand_R nodes.

The item prefab carries Animators, and an Animator overwrites transform values every
frame. If any clip animates Hand_L / Hand_R, then whatever the plugin writes to those
nodes is discarded at runtime and the game keeps using the vanilla values — which are
authored for the vanilla plush's shape and land near the head on a taller model.

This scans every AnimationClip in the game data and reports the ones whose curves touch
those node names, plus the value each curve drives.
"""
import glob
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def main():
    files = [os.path.join(GAME, "resources.assets")]
    files += sorted(glob.glob(os.path.join(GAME, "sharedassets*.assets")))
    files += sorted(glob.glob(os.path.join(GAME, "*.unity3d")))

    hits = 0
    for path in files:
        try:
            env = UnityPy.load(path)
        except Exception:
            continue
        for o in env.objects:
            if o.type.name not in ("AnimationClip", "AnimationClipOverrides"):
                continue
            try:
                clip = o.read()
            except Exception:
                continue
            name = getattr(clip, "m_Name", "?")
            curves = getattr(clip, "m_FloatCurves", None) or []
            pos_curves = getattr(clip, "m_PositionCurves", None) or []
            rot_curves = getattr(clip, "m_RotationCurves", None) or []

            paths = set()
            for c in list(curves) + list(pos_curves) + list(rot_curves):
                p = getattr(c, "path", "") or ""
                paths.add(p)

            target = [p for p in paths if "Hand" in p]
            if target:
                hits += 1
                print(f"=== {os.path.basename(path)} clip '{name}' "
                      f"(id {o.path_id}) ===")
                for p in sorted(target):
                    print(f"    path: {p}")
                # show the driven properties for those paths
                for c in curves:
                    if "Hand" in (getattr(c, "path", "") or ""):
                        attr = getattr(c, "attribute", "?")
                        keys = getattr(c, "m_Curve", None)
                        kc = len(getattr(keys, "m_Keyframes", []) or []) if keys else 0
                        print(f"      float {attr}  keys={kc}")
                for c in pos_curves:
                    if "Hand" in (getattr(c, "path", "") or ""):
                        curve = getattr(c, "curve", None)
                        print(f"      position curve keys="
                              f"{len(getattr(curve, 'm_Curve', []) or [])}")
                for c in rot_curves:
                    if "Hand" in (getattr(c, "path", "") or ""):
                        curve = getattr(c, "curve", None)
                        print(f"      rotation curve keys="
                              f"{len(getattr(curve, 'm_Curve', []) or [])}")

    if hits == 0:
        print("no clip references a Hand_* path")
    else:
        print(f"\n{hits} clips reference Hand_* paths")


if __name__ == "__main__":
    main()
