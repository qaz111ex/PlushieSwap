// Plushie Swap - screen-space constant-width cartoon outline (URP 17 / Unity 6000.3).
//
// ============================================================================
// STATUS: RESEARCH ARTEFACT — NOT COMPILED, NOT SHIPPED.
//
// Nothing references this file: it is not under src/, and PlushieSwap.csproj sets
// EnableDefaultCompileItems=false and compiles only src/**/*.cs. Building it needs
// the Unity editor to compile the shader into a bundle, and no editor is installed
// here, so the shipping mod does the identical arithmetic on the CPU instead — see
// src/PlushieOutline.cs and research/OUTLINE_DESIGN.md. Kept because the maths and
// the measurements below document WHY the shipped code extrudes the way it does.
// ============================================================================
//
// Why this exists
// ---------------
// The .psmesh carries an inverted-hull ink shell whose vertices were pushed out
// along the welded normals by a FIXED OBJECT-SPACE distance in the offline
// pipeline (tools/build_meshes.py: outline_thickness * target_height).
//
//   shell_vertex = surface_vertex + smooth_normal * OUTLINE_THICKNESS
//
// A fixed object-space offset is not a fixed number of screen pixels, so the
// drawn line grows as the plush comes near and thins out as it goes away, and it
// foreshortens at grazing angles. Measured on the shipped assets (research/
// outline_width_metrics.txt), the same shell projects to about 0.8 px at 8 m and
// 37 px at 0.35 m on a 1080p camera: a 48x spread. That is the "coarse and
// broken" look.
//
// This shader keeps those exact shell vertices, undoes the baked extrusion, and
// re-applies an offset whose size is constant in pixels:
//
//   surfaceOS = positionOS - normalOS * _OutlineBakedThickness
//   clip      = TransformObjectToHClip(surfaceOS)
//   dir       = normalize(TransformWorldToHClipDir(normalWS).xy)
//   clip.xy  += dir / _ScreenParams.xy * _OutlineWidth * clip.w * 2
//
// The clip.w factor cancels the perspective divide, and the /screen * 2 term
// converts pixels into NDC, so _OutlineWidth really is the line width in
// displayed pixels at every distance and every FOV. Undoing the extrusion in
// object space also makes the runtime object scale cancel out, so the backpack's
// built-in 0.5x shrink no longer halves the line.
//
// The mesh split is unchanged (body mesh + ink shell mesh, one material each),
// so the existing face/decal mask and welded outline normals keep working.
//
// Usage
// -----
//   * Shader name: "PlushieSwap/Outline"
//   * _OutlineBakedThickness = outline_thickness * target_height from
//     tools/build_meshes.py  (0.0075 * 0.9635 = 0.00722625).
//   * _Cull must stay 1 (Front): this is an inverted hull, the back faces are
//     the ones that draw the line.
//   * Build into an AssetBundle and load it from the plugin; see
//     research/PlushieShaderLoader.sample.cs. If the bundle is missing the
//     plugin keeps its current Universal Render Pipeline/Lit fallback.
//
// The ink colour is flat; it is deliberately NOT sampled from the palette
// texture. The body material keeps _BaseMap -> *_shading.png untouched.

Shader "PlushieSwap/Outline"
{
    Properties
    {
        [Header(Ink)]
        _OutlineColor ("Outline Color", Color) = (0.085, 0.085, 0.105, 1)

        [Header(Width)]
        // Width in displayed pixels. _ScreenParams (not _ScaledScreenParams) is
        // used, so lowering URP's renderScale keeps the on-screen width the same.
        // 2 - 3 px reads as a clean pen line on the plush.
        _OutlineWidth ("Width (pixels)", Range(0.0, 12.0)) = 2.5
        _OutlineWidthScale ("Width Scale", Range(0.0, 4.0)) = 1.0

        [Header(Baked mesh)]
        // outline_thickness * target_height, from tools/build_meshes.py.
        _OutlineBakedThickness ("Baked Object Thickness", Float) = 0.00722625

        [Header(Depth)]
        // Pushes the ink a hair deeper so it never z-fights the body it hugs.
        _OutlineZOffset ("Z Offset (clip units)", Range(0.0, 0.02)) = 0.0005

        [Header(Distance fade)]
        // Defaults are a no-op; lower End to fade the ink out far away.
        _OutlineFadeStart ("Fade Start Distance", Float) = 1000.0
        _OutlineFadeEnd ("Fade End Distance", Float) = 1200.0

        [Header(Render state)]
        [Enum(UnityEngine.Rendering.CullMode)] _Cull ("Cull", Float) = 1
    }

    SubShader
    {
        // Restrict the shader to URP, and keep it in the opaque queue next to the
        // body so the two draw back to back.
        Tags
        {
            "RenderPipeline" = "UniversalPipeline"
            "RenderType" = "Opaque"
            "Queue" = "Geometry"
        }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        CBUFFER_START(UnityPerMaterial)
            float4 _OutlineColor;
            float  _OutlineWidth;
            float  _OutlineWidthScale;
            float  _OutlineBakedThickness;
            float  _OutlineZOffset;
            float  _OutlineFadeStart;
            float  _OutlineFadeEnd;
            float  _Cull;
        CBUFFER_END

        struct OutlineAttributes
        {
            float4 positionOS : POSITION;
            float3 normalOS   : NORMAL;
            UNITY_VERTEX_INPUT_INSTANCE_ID
        };

        struct OutlineVaryings
        {
            float4 positionCS : SV_POSITION;
            UNITY_VERTEX_OUTPUT_STEREO
        };

        // One shared function so the colour and depth passes agree to the pixel.
        float4 OutlinePositionCS(float3 positionOS, float3 normalOS)
        {
            // Recover the real surface by undoing the baked extrusion. Both the
            // shell position and its stored normal are object space, so this is
            // exact and the object's localScale cancels out.
            float3 surfaceOS = positionOS - normalOS * _OutlineBakedThickness;

            float4 positionCS = TransformObjectToHClip(surfaceOS);

            // The shading normal in clip space: its xy is the on-screen direction
            // to push the silhouette outwards.
            float3 normalWS = TransformObjectToWorldNormal(normalOS);
            float3 normalCS = TransformWorldToHClipDir(normalWS);

            float2 dir = normalCS.xy;
            float  len2 = dot(dir, dir);
            // A normal aimed straight at the camera has no silhouette direction;
            // leaving it alone avoids NaNs at the front and back poles.
            dir = (len2 > 1e-10) ? dir * rsqrt(len2) : float2(0.0, 0.0);

            // Optional distance fade; with the defaults `fade` is 1 everywhere.
            float3 positionWS = TransformObjectToWorld(surfaceOS);
            float  dist = distance(positionWS, GetCameraPositionWS());
            float  fade = saturate((_OutlineFadeEnd - dist)
                                   / max(1e-4, _OutlineFadeEnd - _OutlineFadeStart));

            // The pixel-constant step:
            //   clip.w        cancels the perspective divide
            //   / screen * 2  turns a pixel count into NDC
            //
            // _ScreenParams is the CAMERA (display) resolution, so _OutlineWidth
            // is the line width in final displayed pixels regardless of URP's
            // renderScale. Using _ScaledScreenParams instead would make the line
            // grow on screen as the render scale is lowered, because the game
            // allows renderScale 0.2 - 1.0 (RenderScaleSetting.cs).
            float  widthPx = _OutlineWidth * _OutlineWidthScale * fade;
            float2 offset = dir / _ScreenParams.xy
                            * (widthPx * 2.0) * positionCS.w;
            positionCS.xy += offset;

            // Nudge the ink slightly away from the camera so it never z-fights
            // the body it hugs. Reversed Z (D3D) uses larger z = nearer.
            #if UNITY_REVERSED_Z
                positionCS.z -= _OutlineZOffset * positionCS.w;
            #else
                positionCS.z += _OutlineZOffset * positionCS.w;
            #endif

            return positionCS;
        }
        ENDHLSL

        // ------------------------------------------------------------------
        // Pass 1: the ink itself. Front faces culled, so only the shell that
        // pokes past the silhouette is visible.
        // ------------------------------------------------------------------
        Pass
        {
            Name "PlushieOutline"
            // UniversalForwardOnly, not UniversalForward: this pass is then drawn
            // in the forward path AND in the deferred path's forward-only step,
            // so the outline survives either renderer mode.
            Tags { "LightMode" = "UniversalForwardOnly" }

            Cull [_Cull]
            ZWrite On
            ZTest LEqual
            Blend One Zero

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex OutlineVertex
            #pragma fragment OutlineFragment
            #pragma multi_compile_instancing

            OutlineVaryings OutlineVertex(OutlineAttributes input)
            {
                OutlineVaryings output = (OutlineVaryings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.positionCS = OutlinePositionCS(input.positionOS.xyz, input.normalOS);
                return output;
            }

            half4 OutlineFragment(OutlineVaryings input) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);
                return half4(_OutlineColor.rgb, 1.0);
            }
            ENDHLSL
        }

        // ------------------------------------------------------------------
        // Pass 2: depth only, so depth priming and the depth texture see the ink
        // in exactly the same place the colour pass draws it.
        // ------------------------------------------------------------------
        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }

            Cull [_Cull]
            ZWrite On
            ZTest LEqual
            ColorMask R

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex DepthVertex
            #pragma fragment DepthFragment
            #pragma multi_compile_instancing

            OutlineVaryings DepthVertex(OutlineAttributes input)
            {
                OutlineVaryings output = (OutlineVaryings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.positionCS = OutlinePositionCS(input.positionOS.xyz, input.normalOS);
                return output;
            }

            half4 DepthFragment(OutlineVaryings input) : SV_Target
            {
                return 0;
            }
            ENDHLSL
        }
    }

    // The plugin treats a missing/uncompilable shader as a hard failure and
    // falls back to URP/Lit with front-face culling (object-space width).
    FallBack "Universal Render Pipeline/Unlit"
}
