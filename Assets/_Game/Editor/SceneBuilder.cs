using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace FightingGame.EditorTools
{
    /// <summary>
    /// Generates the prototype arena scene and the shared material templates.
    /// Run from the menu (Fighting Game → Rebuild Fight Scene) or in batch mode with
    /// -executeMethod FightingGame.EditorTools.SceneBuilder.Build
    /// </summary>
    public static class SceneBuilder
    {
        const string Root = "Assets/_Game";
        const string MatDir = Root + "/Materials";
        public const string ScenePath = Root + "/Scenes/Fight.unity";

        static readonly Color Background = new Color(0.07f, 0.09f, 0.2f);
        static readonly Color Cyan = new Color(0.34f, 0.84f, 1f);
        static readonly Color Pink = new Color(1f, 0.35f, 0.48f);

        [MenuItem("Fighting Game/Open Fight Scene", priority = 0)]
        public static void Open()
        {
            if (!File.Exists(ScenePath)) Build();
            if (EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
                EditorSceneManager.OpenScene(ScenePath);
        }

        [MenuItem("Fighting Game/Rebuild Fight Scene", priority = 20)]
        public static void Build()
        {
            Directory.CreateDirectory(MatDir);
            Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));

            var lit = SaveMat(LitMaterial(Color.white, 0.5f, Color.black), "FighterLit");
            var glow = SaveMat(GlowMaterial(Color.white), "GlowAdditive");
            var stone = SaveMat(LitMaterial(new Color(0.17f, 0.18f, 0.27f), 0.15f, Color.black), "ArenaStone");
            var capCyan = SaveMat(LitMaterial(Cyan, 0.5f, Cyan * 2.5f), "PillarCapCyan");
            var capPink = SaveMat(LitMaterial(Pink, 0.5f, Pink * 2.5f), "PillarCapPink");
            var lineCyan = SaveMat(GlowMaterial(Cyan * 1.6f), "LineCyan");
            var lineCyanDim = SaveMat(GlowMaterial(Cyan * 0.3f), "LineCyanDim");
            var lineOrange = SaveMat(GlowMaterial(new Color(1f, 0.7f, 0.28f) * 0.45f), "LineOrange");
            var moonMat = SaveMat(GlowMaterial(new Color(1f, 0.9f, 0.77f)), "Moon");
            var starMat = SaveMat(GlowMaterial(Color.white * 0.9f), "Star");

            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            RenderSettings.skybox = null;
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.42f, 0.47f, 0.8f);
            RenderSettings.ambientEquatorColor = new Color(0.22f, 0.22f, 0.35f);
            RenderSettings.ambientGroundColor = new Color(0.15f, 0.08f, 0.04f);
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogColor = Background;
            RenderSettings.fogStartDistance = 25;
            RenderSettings.fogEndDistance = 120;

            // Camera (position is driven by GameManager at runtime)
            var camGo = new GameObject("Main Camera", typeof(Camera), typeof(AudioListener));
            camGo.tag = "MainCamera";
            var cam = camGo.GetComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = Background;
            cam.fieldOfView = 48;
            cam.nearClipPlane = 0.1f;
            cam.farClipPlane = 300;
            camGo.transform.position = new Vector3(0, 2.6f, -9);
            camGo.transform.LookAt(new Vector3(0, 1.2f, 0));
            var camData = camGo.AddComponent<UniversalAdditionalCameraData>();
            camData.renderPostProcessing = true;
            camData.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;

            // Lights
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = new Color(1f, 0.95f, 0.87f);
            sun.intensity = 1.6f;
            sun.shadows = LightShadows.Soft;
            sun.transform.rotation = Quaternion.Euler(50, -30, 0);
            PointLight("Rim Blue", new Vector3(-9, 4, 5), new Color(0.24f, 0.55f, 1f));
            PointLight("Rim Red", new Vector3(9, 4, 5), new Color(1f, 0.2f, 0.33f));

            // Post-processing (bloom/tonemapping from the template profile)
            var volume = new GameObject("Global Volume").AddComponent<Volume>();
            volume.isGlobal = true;
            volume.sharedProfile = AssetDatabase.LoadAssetAtPath<VolumeProfile>("Assets/Settings/SampleSceneProfile.asset");

            // Arena
            var arena = new GameObject("Arena").transform;
            var platform = Prim(PrimitiveType.Cylinder, arena, new Vector3(0, -0.5f, 0), new Vector3(20, 0.5f, 20), stone);
            platform.name = "Platform";
            platform.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            FlatLoop("Edge Ring", arena, 9.7f, 96, 0.12f, lineCyan, 0);
            FlatLoop("Inner Ring", arena, 3f, 72, 0.05f, lineCyanDim, 0);
            FlatLoop("Outer Ring", arena, 6.2f, 72, 0.05f, lineCyanDim, 0);
            FlatLoop("Sigil", arena, 0.9f, 6, 0.12f, lineOrange, 30);

            for (int i = 0; i < 10; i++)
            {
                float a = i / 10f * Mathf.PI * 2 + 0.3f;
                if (Mathf.Sin(a) < -0.55f) continue; // keep the camera side open
                float h = 5 + (i % 3) * 1.5f;
                var pos = new Vector3(Mathf.Cos(a) * 15, 0, Mathf.Sin(a) * 15);
                Prim(PrimitiveType.Cube, arena, pos + Vector3.up * (h / 2 - 1), new Vector3(1.1f, h, 1.1f), stone).name = "Pillar";
                Prim(PrimitiveType.Cube, arena, pos + Vector3.up * (h - 1 + 0.12f), new Vector3(1.3f, 0.25f, 1.3f), i % 2 == 1 ? capPink : capCyan).name = "Pillar Cap";
            }

            var sky = new GameObject("Sky").transform;
            var moon = Prim(PrimitiveType.Sphere, sky, new Vector3(-14, 22, 75), Vector3.one * 14, moonMat);
            moon.name = "Moon";
            moon.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            var rng = new System.Random(7);
            for (int i = 0; i < 160; i++)
            {
                float a = (float)rng.NextDouble() * Mathf.PI - 0.1f;
                float r = 80 + (float)rng.NextDouble() * 30;
                var star = Prim(PrimitiveType.Sphere, sky,
                    new Vector3(Mathf.Cos(a) * r, 8 + (float)rng.NextDouble() * 55, Mathf.Sin(a) * r + 10),
                    Vector3.one * (0.2f + (float)rng.NextDouble() * 0.25f), starMat);
                star.name = "Star";
                star.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
                Object.DestroyImmediate(star.GetComponent<Collider>());
            }

            // Game manager
            var game = new GameObject("Game").AddComponent<GameManager>();
            var so = new SerializedObject(game);
            so.FindProperty("litTemplate").objectReferenceValue = lit;
            so.FindProperty("glowTemplate").objectReferenceValue = glow;
            so.FindProperty("cam").objectReferenceValue = cam;
            so.ApplyModifiedPropertiesWithoutUndo();

            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            AssetDatabase.SaveAssets();
            Debug.Log($"[SceneBuilder] Built {ScenePath}");
        }

        static Material LitMaterial(Color c, float smoothness, Color emission)
        {
            var m = new Material(Shader.Find("Universal Render Pipeline/Lit"));
            m.SetColor("_BaseColor", c);
            m.SetFloat("_Smoothness", smoothness);
            m.EnableKeyword("_EMISSION");
            m.SetColor("_EmissionColor", emission);
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            return m;
        }

        /// <summary>Unlit, additive, no depth write: used for sparks, glows, lines and the hitbox overlay.</summary>
        static Material GlowMaterial(Color c)
        {
            var m = new Material(Shader.Find("Universal Render Pipeline/Unlit"));
            m.SetColor("_BaseColor", c);
            m.SetFloat("_Surface", 1);
            m.SetFloat("_Blend", 2); // additive
            m.SetFloat("_SrcBlend", (float)BlendMode.One);
            m.SetFloat("_DstBlend", (float)BlendMode.One);
            m.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            m.SetFloat("_DstBlendAlpha", (float)BlendMode.One);
            m.SetFloat("_ZWrite", 0);
            m.SetOverrideTag("RenderType", "Transparent");
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            return m;
        }

        static Material SaveMat(Material m, string name)
        {
            string path = $"{MatDir}/{name}.mat";
            var existing = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (existing != null)
            {
                existing.shader = m.shader;
                existing.CopyPropertiesFromMaterial(m);
                existing.shaderKeywords = m.shaderKeywords;
                existing.renderQueue = m.renderQueue;
                existing.SetOverrideTag("RenderType", m.GetTag("RenderType", false));
                EditorUtility.SetDirty(existing);
                return existing;
            }
            AssetDatabase.CreateAsset(m, path);
            return m;
        }

        static Transform Prim(PrimitiveType type, Transform parent, Vector3 pos, Vector3 scale, Material mat)
        {
            var go = GameObject.CreatePrimitive(type);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = pos;
            go.transform.localScale = scale;
            go.GetComponent<MeshRenderer>().sharedMaterial = mat;
            return go.transform;
        }

        static void PointLight(string name, Vector3 pos, Color c)
        {
            var l = new GameObject(name).AddComponent<Light>();
            l.type = LightType.Point;
            l.color = c;
            l.range = 30;
            l.intensity = 6;
            l.transform.position = pos;
        }

        /// <summary>A closed polyline lying flat on the arena floor.</summary>
        static void FlatLoop(string name, Transform parent, float radius, int points, float width, Material mat, float rotDeg)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = new Vector3(0, 0.015f, 0);
            go.transform.localRotation = Quaternion.Euler(90, rotDeg, 0);
            var lr = go.AddComponent<LineRenderer>();
            lr.useWorldSpace = false;
            lr.loop = true;
            lr.alignment = LineAlignment.TransformZ;
            lr.widthMultiplier = width;
            lr.shadowCastingMode = ShadowCastingMode.Off;
            lr.sharedMaterial = mat;
            lr.positionCount = points;
            for (int i = 0; i < points; i++)
            {
                float a = i * Mathf.PI * 2 / points;
                lr.SetPosition(i, new Vector3(Mathf.Cos(a), Mathf.Sin(a), 0) * radius);
            }
        }
    }
}
