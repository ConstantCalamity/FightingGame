using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace FightingGame.EditorTools
{
    /// <summary>
    /// Turns the Blender exports in Assets/_Game/Art into game content: URP materials from the baked textures
    /// (remapped onto the FBX materials), CharacterDef/MapDef assets and the GameContent registry.
    /// Called by SceneBuilder.Build; safe to re-run after re-exporting art.
    /// </summary>
    public static class ContentBuilder
    {
        const string Art = "Assets/_Game/Art";
        const string ContentDir = "Assets/_Game/Content";
        const string MatDir = "Assets/_Game/Materials";

        struct CharStyle { public string id; public Color trail, accent; public float bladeStart, bladeRadius; }

        static readonly CharStyle[] Characters =
        {
            new CharStyle { id = "Corvin", trail = new Color(1.1f, 0.4f, 0.1f), accent = new Color(1f, 0.45f, 0.12f), bladeStart = 0.19f, bladeRadius = 0.09f },
            new CharStyle { id = "Mordran", trail = new Color(.8f,.25f,.08f), accent = new Color(.8f,.3f,.12f), bladeStart = 0f, bladeRadius = .20f },
            new CharStyle { id = "Isolde", trail = new Color(0.6f, 0.65f, 0.8f), accent = new Color(0.85f, 0.15f, 0.18f), bladeStart = 0.12f, bladeRadius = 0.07f },
        };

        [MenuItem("Fighting Game/Rebuild Content (characters + maps)")]
        public static GameContent Build()
        {
            Directory.CreateDirectory(ContentDir);
            Directory.CreateDirectory(MatDir);
            AssetDatabase.Refresh();

            var content = LoadOrCreate<GameContent>($"{ContentDir}/GameContent.asset");
            content.movesets = AssetDatabase.LoadAssetAtPath<TextAsset>("Assets/_Game/Data/Movesets.json");
            content.particleTemplate = ParticleMaterial();
            content.flameMaterial = FlameMaterial();
            content.smokeMaterial = SmokeMaterial();

            var chars = new List<CharacterDef>();
            foreach (var style in Characters)
            {
                var def = BuildCharacter(style);
                if (def != null) chars.Add(def);
            }
            content.characters = chars.ToArray();

            var maps = new List<MapDef>();
            if (Directory.Exists($"{Art}/Maps"))
                foreach (var dir in Directory.GetDirectories($"{Art}/Maps").OrderBy(d => d))
                {
                    var map = BuildMap(dir.Replace('\\', '/'));
                    if (map != null) maps.Add(map);
                }
            content.maps = maps.ToArray();

            EditorUtility.SetDirty(content);
            AssetDatabase.SaveAssets();
            Debug.Log($"[ContentBuilder] {chars.Count} characters ({string.Join(", ", chars.Select(c => c.id))}), " +
                      $"{maps.Count} maps ({string.Join(", ", maps.Select(m => m.displayName))})");
            return content;
        }

        // ---------- characters ----------

        static CharacterDef BuildCharacter(CharStyle style)
        {
            string id = style.id, dir = $"{Art}/Characters/{id}", fbx = $"{dir}/{id}.fbx";
            if (!File.Exists(fbx)) { Debug.LogWarning($"[ContentBuilder] missing {fbx}"); return null; }

            var remap = new Dictionary<string, Material>
            {
                [$"M_{id}_Body"] = CharacterMaterial(dir, id, "Body"),
                [$"M_{id}_Weapon"] = CharacterMaterial(dir, id, "Weapon"),
            };
            Remap(fbx, remap);

            var def = LoadOrCreate<CharacterDef>($"{ContentDir}/{id}.asset");
            def.id = id;
            def.dualFlails = id == "Mordran";
            def.prefab = AssetDatabase.LoadAssetAtPath<GameObject>(fbx);
            def.clips = AssetDatabase.LoadAllAssetsAtPath(fbx).OfType<AnimationClip>()
                .Where(c => !c.name.StartsWith("__preview__")).ToArray();
            def.trailColor = style.trail;
            def.accent = style.accent;
            def.emberAura = id == "Corvin";
            def.bladeStart = style.bladeStart;
            def.bladeRadius = style.bladeRadius;
            def.capeBones = def.prefab.GetComponentsInChildren<Transform>(true)
                .Where(t => t.name.StartsWith("cape.")).Select(t => t.name).OrderBy(n => n).ToArray();

            string knife = $"{dir}/{id}_Knife.fbx";
            if (File.Exists(knife))
            {
                Remap(knife, new Dictionary<string, Material> { [$"M_{id}_Knife"] = CharacterMaterial(dir, id, "Knife") });
                def.projectilePrefab = AssetDatabase.LoadAssetAtPath<GameObject>(knife);
            }
            EditorUtility.SetDirty(def);
            Debug.Log($"[ContentBuilder] {id}: {def.clips.Length} clips ({string.Join(",", def.clips.Select(c => c.name))}), cape bones {def.capeBones.Length}");
            return def;
        }

        static Material CharacterMaterial(string dir, string id, string part)
        {
            string p = $"{dir}/T_{id}_{part}";
            var emission = Tex($"{p}_Emission.png");
            var m = Lit(Tex($"{p}_Albedo.png"), Tex($"{p}_Normal.png"), Tex($"{p}_Mask.png"), Tex($"{p}_AO.png"),
                        Color.white, 1f, emission ? Color.white : (Color?)null, 2.6f);
            if (emission) m.SetTexture("_EmissionMap", emission);   // ember cracks: drives bloom
            return Save(m, $"{MatDir}/M_{id}_{part}.mat");
        }

        // ---------- maps ----------

#pragma warning disable 0649
        [Serializable] class MatList { public MatEntry[] items; }
        [Serializable] class MatEntry
        {
            public string material, albedo, normal, mask, emissionMap;
            public float tiling, emissionIntensity, smoothnessScale;
            public float[] tint, emission;
        }
        [Serializable] class Layout
        {
            public Sun sun; public Ambient ambient; public Fog fog; public float[] background;
            public PointL[] pointLights; public Fx[] fx;
        }
        [Serializable] class Sun { public float[] direction_deg, color; public float intensity; }
        [Serializable] class Ambient { public float[] sky, equator, ground; }
        [Serializable] class Fog { public float[] color; public float start, end; }
        [Serializable] class PointL { public float[] pos, color; public float intensity, range; }
        [Serializable] class Fx { public string type; public float[] pos; public float scale; }
#pragma warning restore 0649

        static MapDef BuildMap(string dir)
        {
            string name = Path.GetFileName(dir);
            string fbx = $"{dir}/{name}.fbx";
            if (!File.Exists(fbx) || !File.Exists($"{dir}/materials.json") || !File.Exists($"{dir}/layout.json"))
            {
                Debug.LogWarning($"[ContentBuilder] map {name} incomplete, skipped");
                return null;
            }
            var mats = JsonUtility.FromJson<MatList>("{\"items\":" + File.ReadAllText($"{dir}/materials.json") + "}");
            var remap = new Dictionary<string, Material>();
            foreach (var e in mats.items)
            {
                Color tint = C(e.tint, Color.white);
                Color? emission = e.emission != null && e.emission.Length >= 3 ? C(e.emission, Color.black) : (Color?)null;
                // the map mask packs AO in G, so it doubles as the occlusion map
                var mask = Tex($"{dir}/{e.mask}");
                var m = Lit(Tex($"{dir}/{e.albedo}"), Tex($"{dir}/{e.normal}"), mask, mask,
                            tint, e.smoothnessScale > 0 ? e.smoothnessScale : 1f, emission, e.emissionIntensity);
                if (emission.HasValue && !string.IsNullOrEmpty(e.emissionMap))
                    m.SetTexture("_EmissionMap", Tex($"{dir}/{e.emissionMap}"));
                remap[e.material] = Save(m, $"{MatDir}/{name}_{e.material}.mat");
            }
            Remap(fbx, remap);

            var lay = JsonUtility.FromJson<Layout>(File.ReadAllText($"{dir}/layout.json"));
            var def = LoadOrCreate<MapDef>($"{ContentDir}/Map_{name}.asset");
            def.displayName = name == "CinderCathedral" ? "Ashenfell" : Nice(name);
            def.prefab = AssetDatabase.LoadAssetAtPath<GameObject>(fbx);
            if (lay.sun != null)
            {
                var d = lay.sun.direction_deg;
                def.sunEuler = d != null && d.Length >= 2 ? new Vector3(d[0], d[1], 0) : new Vector3(50, -30, 0);
                def.sunColor = C(lay.sun.color, Color.white);
                def.sunIntensity = lay.sun.intensity;
            }
            if (lay.ambient != null)
            {
                def.ambientSky = C(lay.ambient.sky, Color.gray);
                def.ambientEquator = C(lay.ambient.equator, Color.gray);
                def.ambientGround = C(lay.ambient.ground, Color.black);
            }
            if (lay.fog != null)
            {
                def.fogColor = C(lay.fog.color, Color.gray);
                def.fogStart = lay.fog.start;
                def.fogEnd = lay.fog.end;
            }
            def.background = C(lay.background, def.fogColor);
            def.pointLights = (lay.pointLights ?? new PointL[0]).Select(p => new MapDef.PointLightDef
            {
                position = ToUnity(p.pos), color = C(p.color, Color.white), intensity = p.intensity, range = p.range,
            }).ToList();
            def.fx = (lay.fx ?? new Fx[0]).Select(f => new MapDef.FxDef { type = f.type, position = ToUnity(f.pos), scale = f.scale }).ToList();
            EditorUtility.SetDirty(def);
            Debug.Log($"[ContentBuilder] map {def.displayName}: {remap.Count} materials, {def.pointLights.Count} lights, {def.fx.Count} fx");
            return def;
        }

        static string Nice(string camel) =>
            System.Text.RegularExpressions.Regex.Replace(camel, "(?<=[a-z])([A-Z])", " $1");

        /// <summary>Blender (x, y, z) -> Unity (-x, z, -y), matching the FBX axis conversion.</summary>
        static Vector3 ToUnity(float[] p) => p == null || p.Length < 3 ? Vector3.zero : new Vector3(-p[0], p[2], -p[1]);

        static Color C(float[] c, Color fallback) =>
            c == null || c.Length < 3 ? fallback : new Color(c[0], c[1], c[2], c.Length > 3 ? c[3] : 1);

        // ---------- shared helpers ----------

        static Texture2D Tex(string path) => File.Exists(path) ? AssetDatabase.LoadAssetAtPath<Texture2D>(path) : null;

        static Material Lit(Texture2D albedo, Texture2D normal, Texture2D mask, Texture2D ao, Color tint, float smoothness,
                            Color? emission, float emissionIntensity)
        {
            var m = new Material(Shader.Find("Universal Render Pipeline/Lit"));
            m.SetTexture("_BaseMap", albedo);
            m.SetColor("_BaseColor", tint);
            if (normal)
            {
                m.SetTexture("_BumpMap", normal);
                m.SetFloat("_BumpScale", 1f);
                m.EnableKeyword("_NORMALMAP");
            }
            if (mask)
            {
                m.SetTexture("_MetallicGlossMap", mask);
                m.SetFloat("_SmoothnessTextureChannel", 0);
                m.SetFloat("_Smoothness", smoothness);
                m.EnableKeyword("_METALLICSPECGLOSSMAP");
            }
            else
            {
                m.SetFloat("_Smoothness", 0.3f * smoothness);
            }
            if (ao)
            {
                m.SetTexture("_OcclusionMap", ao);
                m.SetFloat("_OcclusionStrength", 0.6f);
                m.EnableKeyword("_OCCLUSIONMAP");
            }
            // emission is always enabled so characters can flash on hit via a property block
            m.EnableKeyword("_EMISSION");
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            m.SetColor("_EmissionColor", emission.HasValue ? emission.Value.linear * Mathf.Max(emissionIntensity, 0) : Color.black);
            return m;
        }

        static Material Save(Material m, string path)
        {
            var existing = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (existing != null)
            {
                existing.shader = m.shader;
                existing.CopyPropertiesFromMaterial(m);
                existing.shaderKeywords = m.shaderKeywords;
                existing.globalIlluminationFlags = m.globalIlluminationFlags;
                EditorUtility.SetDirty(existing);
                return existing;
            }
            AssetDatabase.CreateAsset(m, path);
            return m;
        }

        static void Remap(string modelPath, Dictionary<string, Material> materials)
        {
            var imp = (ModelImporter)AssetImporter.GetAtPath(modelPath);
            bool changed = false;
            var existing = imp.GetExternalObjectMap();
            foreach (var kv in materials)
            {
                if (kv.Value == null) continue;
                var id = new AssetImporter.SourceAssetIdentifier(typeof(Material), kv.Key);
                if (existing.TryGetValue(id, out var cur) && cur == kv.Value) continue;
                imp.AddRemap(id, kv.Value);
                changed = true;
            }
            if (changed) imp.SaveAndReimport();
        }

        static T LoadOrCreate<T>(string path) where T : ScriptableObject
        {
            var a = AssetDatabase.LoadAssetAtPath<T>(path);
            if (a != null) return a;
            a = ScriptableObject.CreateInstance<T>();
            AssetDatabase.CreateAsset(a, path);
            return a;
        }

        static float Fbm(float x, float y, int octaves = 4)
        {
            float sum = 0, amp = 0.5f, norm = 0, f = 1;
            for (int i = 0; i < octaves; i++)
            {
                sum += Mathf.PerlinNoise(x * f + 17.3f * i, y * f - 9.1f * i) * amp;
                norm += amp; amp *= 0.5f; f *= 2.03f;
            }
            return sum / norm;
        }

        static Texture2D SaveTexture(string path, int w, int h, Color32[] px, bool clamp = true)
        {
            var t = new Texture2D(w, h, TextureFormat.RGBA32, false);
            t.SetPixels32(px);
            File.WriteAllBytes(path, t.EncodeToPNG());
            UnityEngine.Object.DestroyImmediate(t);
            AssetDatabase.ImportAsset(path);
            var ti = (TextureImporter)AssetImporter.GetAtPath(path);
            ti.alphaIsTransparency = true;
            ti.wrapMode = clamp ? TextureWrapMode.Clamp : TextureWrapMode.Repeat;
            ti.mipmapEnabled = true;
            ti.SaveAndReimport();
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        }

        /// <summary>
        /// 4x4 flipbook of a licking flame (512x512). Noise is sampled around a circle in noise space so the
        /// 16 frames loop seamlessly; each frame is a tapered tongue with a hot core near the base.
        /// </summary>
        static Texture2D FlameSheet()
        {
            string path = $"{MatDir}/T_FlameSheet.png";
            if (File.Exists(path)) return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
            const int tile = 128, cols = 4, size = tile * cols;
            var px = new Color32[size * size];
            for (int f = 0; f < 16; f++)
            {
                int tx = f % cols, ty = cols - 1 - f / cols;      // frame 0 is the top-left tile
                float ph = f / 16f * Mathf.PI * 2;
                float ox = Mathf.Cos(ph) * 1.4f, oy = Mathf.Sin(ph) * 1.4f;
                for (int y = 0; y < tile; y++)
                    for (int x = 0; x < tile; x++)
                    {
                        float u = (x + 0.5f) / tile * 2f - 1f, v = (y + 0.5f) / tile;
                        // a broad teardrop body that licks sideways more the higher it goes
                        float distort = (Fbm(u * 1.4f + ox, v * 2.1f + oy) - 0.5f) * 0.9f * v * v;
                        float uu = u + distort;
                        float vv = v + (Fbm(u * 2f + ox + 5f, v * 3f + oy + 5f) - 0.5f) * 0.15f;
                        float width = 0.88f * Mathf.Pow(Mathf.Clamp01(1f - vv), 0.6f) * (0.62f + 0.38f * Mathf.Clamp01(vv * 5f));
                        float d = Mathf.Abs(uu) / Mathf.Max(0.001f, width);
                        float body = Mathf.Clamp01(1f - d);
                        body = body * body * (3f - 2f * body);
                        float bottom = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(v / 0.08f));
                        // noise eats into the upper half so the tips fork into separate tongues and break off
                        float n2 = Fbm(u * 3f + ox * 1.5f + 9f, v * 4f + oy * 1.5f + 9f);
                        float erode = Mathf.Clamp01((n2 - v * 0.8f + 0.38f) * 3.2f);
                        float detail = 0.7f + 0.3f * Fbm(u * 4f + ox * 2f, v * 6f + oy * 2f);
                        float a = body * bottom * erode * detail;
                        float core = Mathf.Clamp01(1f - d * 1.35f) * Mathf.Clamp01(1f - vv * 1.25f) * erode;
                        byte lum = (byte)(255 * Mathf.Clamp01(a * 0.7f + core * 0.75f));
                        px[(ty * tile + y) * size + tx * tile + x] = new Color32(lum, lum, lum, (byte)(255 * Mathf.Clamp01(a)));
                    }
            }
            return SaveTexture(path, size, size, px);
        }

        static Texture2D SmokePuff()
        {
            string path = $"{MatDir}/T_Smoke.png";
            if (File.Exists(path)) return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
            const int n = 128;
            var px = new Color32[n * n];
            for (int y = 0; y < n; y++)
                for (int x = 0; x < n; x++)
                {
                    float u = (x + 0.5f) / n * 2 - 1, v = (y + 0.5f) / n * 2 - 1;
                    float r = Mathf.Sqrt(u * u + v * v);
                    float fall = Mathf.Clamp01(1f - r);
                    fall = fall * fall * (3 - 2 * fall);
                    float billow = Fbm(u * 2.2f + 3f, v * 2.2f + 7f, 5);
                    float a = fall * Mathf.Clamp01(billow * 1.6f - 0.25f);
                    byte lum = (byte)(255 * (0.75f + 0.25f * billow));
                    px[y * n + x] = new Color32(lum, lum, lum, (byte)(255 * a));
                }
            return SaveTexture(path, n, n, px);
        }

        static Material ParticleShaderMaterial(Texture2D tex, bool additive)
        {
            var m = new Material(Shader.Find("Universal Render Pipeline/Particles/Unlit"));
            m.SetTexture("_BaseMap", tex);
            m.SetColor("_BaseColor", Color.white);
            m.SetFloat("_Surface", 1);
            m.SetFloat("_Blend", additive ? 2 : 0);
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)(additive ? BlendMode.One : BlendMode.OneMinusSrcAlpha));
            m.SetFloat("_ZWrite", 0);
            m.SetOverrideTag("RenderType", "Transparent");
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            return m;
        }

        static Material FlameMaterial() => Save(ParticleShaderMaterial(FlameSheet(), true), $"{MatDir}/FlameAdditive.mat");

        static Material SmokeMaterial() => Save(ParticleShaderMaterial(SmokePuff(), false), $"{MatDir}/SmokeAlpha.mat");

        /// <summary>Additive particle material with a soft round sprite (vertex colours drive tint and fade).</summary>
        static Material ParticleMaterial()
        {
            string texPath = $"{MatDir}/T_SoftDot.png";
            if (!File.Exists(texPath))
            {
                const int n = 64;
                var t = new Texture2D(n, n, TextureFormat.RGBA32, false);
                for (int y = 0; y < n; y++)
                    for (int x = 0; x < n; x++)
                    {
                        float d = Vector2.Distance(new Vector2(x + 0.5f, y + 0.5f), new Vector2(n / 2f, n / 2f)) / (n / 2f);
                        float a = Mathf.Clamp01(1 - d);
                        a = a * a * (3 - 2 * a);
                        t.SetPixel(x, y, new Color(1, 1, 1, a));
                    }
                File.WriteAllBytes(texPath, t.EncodeToPNG());
                UnityEngine.Object.DestroyImmediate(t);
                AssetDatabase.ImportAsset(texPath);
                var ti = (TextureImporter)AssetImporter.GetAtPath(texPath);
                ti.alphaIsTransparency = true;
                ti.wrapMode = TextureWrapMode.Clamp;
                ti.SaveAndReimport();
            }
            var m = new Material(Shader.Find("Universal Render Pipeline/Particles/Unlit"));
            m.SetTexture("_BaseMap", AssetDatabase.LoadAssetAtPath<Texture2D>(texPath));
            m.SetColor("_BaseColor", Color.white);
            m.SetFloat("_Surface", 1);
            m.SetFloat("_Blend", 2);
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)BlendMode.One);
            m.SetFloat("_ZWrite", 0);
            m.SetOverrideTag("RenderType", "Transparent");
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            return Save(m, $"{MatDir}/ParticleAdditive.mat");
        }
    }
}
