using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace PlushieSwap
{
    /// <summary>
    /// Binary reader for the .psmesh format produced by tools/build_meshes.py.
    ///
    /// Layout (little endian):
    ///   char[8]  "PSMESH03"
    ///   int32    nameLength + utf8 bytes
    ///   int32    submeshCount
    ///   per submesh:
    ///     float32 x4 colour
    ///     int32      flags      (bit 0 = inverted-hull outline)
    ///     int32 vertexCount, int32 indexCount
    ///     positions float32 x3 * vertexCount
    ///     normals   float32 x3 * vertexCount
    ///     uvs       float32 x2 * vertexCount
    ///     colours   float32 x3 * vertexCount
    ///     indices   int32      * indexCount
    ///   float32 x3 boundsMin, float32 x3 boundsMax
    ///   int32 hasGrips,
    ///     [float32 x3 left, float32 x3 right,
    ///      float32 x4 leftRotation, float32 x4 rightRotation]   (rotations optional)
    ///   int32 wobbleCount, [uint8 * wobbleCount]                (legacy, always 0)
    ///   int32 outlineCount, [int32 * outlineCount], [uint8 * outlineCount]
    ///     source vertex of every outline vertex, and its ink width
    ///   float32 bakedOutlineThickness   (0 on older files)
    /// </summary>
    internal static class PsMeshReader
    {
        private static readonly byte[] Magic = { (byte)'P', (byte)'S', (byte)'M', (byte)'E', (byte)'S', (byte)'H', (byte)'0', (byte)'3' };

        /// <summary>Submesh flag: draw with front faces culled (the ink outline shell).</summary>
        internal const int FlagOutline = 1;

        internal sealed class SubMesh
        {
            /// <summary>
            /// The submesh's single flat colour, as stored in the file header.
            ///
            /// The format also carries a per-vertex colour block, but the build pipeline
            /// merges every submesh of one colour into one group, so that block is the
            /// same value repeated for every vertex and carries no information this field
            /// does not. It is still parsed (the reader must advance past it) and
            /// `PlushieModel.BuildMesh` still converts it into `mesh.colors`, which is
            /// what the shader samples; this header copy is retained for the same
            /// byte-layout reason as the grip rotations below.
            /// </summary>
            public Color Colour;
            public int Flags;
            public Vector3[] Positions;
            public Vector3[] Normals;
            public Vector2[] Uvs;
            public Color[] Colours;
            public int[] Indices;

            public bool IsOutline
            {
                get { return (Flags & FlagOutline) != 0; }
            }
        }

        internal sealed class Asset
        {
            public string Name;
            public SubMesh[] SubMeshes;
            public Bounds Bounds;

            /// <summary>True when the file carries hand hold points.</summary>
            public bool HasGrips;

            /// <summary>Item-local position of the player's left hand.</summary>
            public Vector3 GripLeft;

            /// <summary>Item-local position of the player's right hand.</summary>
            public Vector3 GripRight;

            /// <summary>
            /// Item-local rotation of the player's left hand, when the file carries it.
            ///
            /// Parsed for byte-layout symmetry but NOT read by anything: the mod derives
            /// the hold from the anchors' midpoint and never poses a hand. Both models in
            /// the repository also carry the identical value, i.e. it is a single
            /// constant rather than per-model data. Kept (and still consumed) because the
            /// format writes it and the reader must advance past those bytes; deleting the
            /// field would mean changing the byte layout, which older files depend on.
            /// </summary>
            public Quaternion GripLeftRotation = Quaternion.identity;

            /// <summary>Right-hand counterpart of <see cref="GripLeftRotation"/>; likewise unread.</summary>
            public Quaternion GripRightRotation = Quaternion.identity;

        /// <summary>
        /// Per-ink-shell-vertex width in [0, 1], or null when the file has none.
        ///
        /// The shell is baked as `surface + normal * thickness * width`, so the runtime
        /// can undo that exactly. Width 1 is a normal outward line; width 0 means "no ink
        /// here" (an eye, the mouth, a blush, a downward-facing surface) and the shell
        /// vertex sits on the body, where front-face culling and the body's own depth hide
        /// it. No geometry is cut for it, which is what keeps the silhouette line whole.
        /// </summary>
        public float[] OutlineWidths;

        /// <summary>
        /// How far the ink shell was pushed out along its normals when the file was
        /// built. The runtime subtracts exactly this to recover the surface, then
        /// extrudes again in screen space so the line has a constant pixel width
        /// instead of a constant world length. 0 when there is no outline.
        /// </summary>
        public float BakedOutlineThickness;
        }

        /// <summary>
        /// Parses a .psmesh held in memory.
        ///
        /// Only the in-memory entry point exists: the data always arrives through
        /// `AssetProvider`, which reads either a loose file or the embedded copy into a
        /// byte array, so a path-based overload would have no caller. Keeping one entry
        /// point also means the corrupt-file handling has exactly one shape to reason
        /// about.
        /// </summary>
        internal static Asset Read(byte[] bytes, string label)
        {
            using (MemoryStream stream = new MemoryStream(bytes, false))
            {
                return Read(stream, label);
            }
        }

        private static Asset Read(Stream stream, string label)
        {
            using (BinaryReader reader = new BinaryReader(stream))
            {
                byte[] magic = reader.ReadBytes(Magic.Length);
                if (magic.Length != Magic.Length)
                {
                    throw new InvalidDataException("truncated file: " + label);
                }
                for (int i = 0; i < Magic.Length; i++)
                {
                    if (magic[i] != Magic[i])
                    {
                        throw new InvalidDataException("not a .psmesh file: " + label);
                    }
                }

                // Every count in this file is read from the stream and then used to size an
                // allocation, so each one is validated against the bytes that actually
                // remain BEFORE allocating. `BinaryReader.ReadBytes(n)` allocates its
                // result buffer up front (measured: a 1.5e9 count allocates 1.5 GB even
                // when only 100 bytes are left), so an unvalidated count is an
                // out-of-memory vector on a corrupt or hostile file, not merely a parse
                // error. These guards turn a bad count into a clean InvalidDataException,
                // which the caller reports and answers with the embedded copy.
                const int MaxCount = 1 << 26; // 67 M: above any real model, below int.MaxValue.

                int nameLength = reader.ReadInt32();
                if (nameLength < 0 || nameLength > MaxCount || nameLength > Remaining(stream))
                {
                    throw new InvalidDataException(
                        "bad name length (" + nameLength + ") in " + label);
                }
                Asset asset = new Asset { Name = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(nameLength)) };

                int subMeshCount = reader.ReadInt32();
                if (subMeshCount < 0 || subMeshCount > MaxCount)
                {
                    throw new InvalidDataException(
                        "bad submesh count (" + subMeshCount + ") in " + label);
                }
                asset.SubMeshes = new SubMesh[subMeshCount];

                for (int s = 0; s < subMeshCount; s++)
                {
                    SubMesh sub = new SubMesh
                    {
                        Colour = new Color(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle()),
                        Flags = reader.ReadInt32()
                    };

                    int vertexCount = reader.ReadInt32();
                    int indexCount = reader.ReadInt32();
                    if (vertexCount < 0 || vertexCount > MaxCount
                        || indexCount < 0 || indexCount > MaxCount)
                    {
                        throw new InvalidDataException(
                            "bad vertex/index count (" + vertexCount + "/" + indexCount
                            + ") in " + label);
                    }

                    // positions + normals + uvs + colours = (3+3+2+3) floats per vertex,
                    // then 4 bytes per index.
                    long needed = (long)vertexCount * 44L + (long)indexCount * 4L;
                    if (needed > Remaining(stream))
                    {
                        throw new InvalidDataException(
                            "submesh " + s + " of " + label + " needs " + needed
                            + " bytes but only " + Remaining(stream) + " remain");
                    }

                    sub.Positions = ReadVector3Array(reader, vertexCount);
                    sub.Normals = ReadVector3Array(reader, vertexCount);
                    sub.Uvs = ReadVector2Array(reader, vertexCount);
                    sub.Colours = ReadColorArray(reader, vertexCount);
                    sub.Indices = ReadInt32Array(reader, indexCount);

                    asset.SubMeshes[s] = sub;
                }

                Vector3 min = ReadVector3(reader);
                Vector3 max = ReadVector3(reader);
                asset.Bounds = new Bounds((min + max) * 0.5f, max - min);

                if (stream.Position + 4 <= stream.Length)
                {
                    int hasGrips = reader.ReadInt32();
                    if (hasGrips != 0 && stream.Position + 24 <= stream.Length)
                    {
                        asset.GripLeft = ReadVector3(reader);
                        asset.GripRight = ReadVector3(reader);
                        asset.HasGrips = true;

                        // The rotations are newer than the positions; older files stop
                        // here and keep the identity default.
                        //
                        // The presence test is "are 32 bytes left", which is ambiguous in
                        // principle: a file with grip positions but no rotations followed
                        // by 32+ bytes of some other block would be misread, and the
                        // outline block that comes next is exactly that shape. Every file
                        // this project writes ends with the rotations, and nothing reads
                        // them anyway (see the GripLeftRotation field), so the ambiguity
                        // is latent rather than live — but it is why a future format
                        // revision should write an explicit flag instead of relying on
                        // the remaining length.
                        if (stream.Position + 32 <= stream.Length)
                        {
                            asset.GripLeftRotation = ReadQuaternion(reader);
                            asset.GripRightRotation = ReadQuaternion(reader);
                        }
                    }
                }

                // Two optional trailing blocks are still skipped rather than removed, so
                // the reader keeps working with files written before the soft-body
                // wobble was dropped. Nothing reads their contents any more.
                if (stream.Position + 4 <= stream.Length)
                {
                    int wobbleCount = reader.ReadInt32();
                    if (wobbleCount > 0)
                    {
                        if (wobbleCount > Remaining(stream))
                        {
                            // Truncated file. The old code skipped the block and then read
                            // whatever followed as the next field, which produced a
                            // plausible-looking garbage thickness and so defeated the
                            // "corrupt file -> fall back to the embedded copy" path.
                            throw new InvalidDataException(
                                "wobble block claims " + wobbleCount + " bytes but only "
                                + Remaining(stream) + " remain in " + label);
                        }
                        reader.ReadBytes(wobbleCount);
                    }
                }

                if (stream.Position + 4 <= stream.Length)
                {
                    int outlineCount = reader.ReadInt32();
                    if (outlineCount < 0)
                    {
                        throw new InvalidDataException(
                            "bad outline count (" + outlineCount + ") in " + label);
                    }
                    if (outlineCount > 0)
                    {
                        // int64 throughout, and the check runs before any allocation.
                        long needed = (long)outlineCount * 5L;
                        if (needed > Remaining(stream))
                        {
                            throw new InvalidDataException(
                                "outline block claims " + needed + " bytes but only "
                                + Remaining(stream) + " remain in " + label);
                        }
                        // source vertex of each ink-shell vertex (not needed at runtime)
                        reader.ReadBytes(outlineCount * 4);
                        byte[] widths = reader.ReadBytes(outlineCount);
                        asset.OutlineWidths = new float[outlineCount];
                        for (int i = 0; i < outlineCount; i++)
                        {
                            asset.OutlineWidths[i] = widths[i] / 255f;
                        }
                    }
                }

                // Written last, so older files simply run out of stream here.
                if (stream.Position + 4 <= stream.Length)
                {
                    asset.BakedOutlineThickness = reader.ReadSingle();
                }

                return asset;
            }
        }

        /// <summary>Bytes left in the stream, or 0 when it cannot be determined.</summary>
        private static long Remaining(Stream stream)
        {
            long remaining = stream.Length - stream.Position;
            return remaining > 0 ? remaining : 0;
        }

        private static Vector3 ReadVector3(BinaryReader reader)
        {
            return new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());
        }

        private static Quaternion ReadQuaternion(BinaryReader reader)
        {
            return new Quaternion(reader.ReadSingle(), reader.ReadSingle(),
                                  reader.ReadSingle(), reader.ReadSingle());
        }

        private static Vector3[] ReadVector3Array(BinaryReader reader, int count)
        {
            Vector3[] result = new Vector3[count];
            for (int i = 0; i < count; i++)
            {
                result[i] = ReadVector3(reader);
            }
            return result;
        }

        private static Vector2[] ReadVector2Array(BinaryReader reader, int count)
        {
            Vector2[] result = new Vector2[count];
            for (int i = 0; i < count; i++)
            {
                result[i] = new Vector2(reader.ReadSingle(), reader.ReadSingle());
            }
            return result;
        }

        private static Color[] ReadColorArray(BinaryReader reader, int count)
        {
            Color[] result = new Color[count];
            for (int i = 0; i < count; i++)
            {
                result[i] = new Color(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle(), 1f);
            }
            return result;
        }

        private static int[] ReadInt32Array(BinaryReader reader, int count)
        {
            int[] result = new int[count];
            for (int i = 0; i < count; i++)
            {
                result[i] = reader.ReadInt32();
            }
            return result;
        }
    }
}
