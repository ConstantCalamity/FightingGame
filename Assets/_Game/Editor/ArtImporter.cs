using System;
using System.IO;
using UnityEditor;

namespace FightingGame.EditorTools
{
    /// <summary>
    /// Import settings for the Blender-generated art in Assets/_Game/Art: generic rigs with axis conversion baked,
    /// clips renamed from "Rig|Idle" to "Idle" with looping set, and normal/mask textures flagged correctly.
    /// </summary>
    public class ArtImporter : AssetPostprocessor
    {
        static readonly string[] LoopingClips = { "Idle", "WalkFwd", "WalkBack" };

        static bool IsCharacter(string p) => p.Replace('\\', '/').Contains("/_Game/Art/Characters/");
        static bool IsMap(string p) => p.Replace('\\', '/').Contains("/_Game/Art/Maps/");

        void OnPreprocessModel()
        {
            var mi = (ModelImporter)assetImporter;
            if (!IsCharacter(assetPath) && !IsMap(assetPath)) return;
            mi.bakeAxisConversion = true;
            mi.useFileScale = true;
            mi.globalScale = 1;
            mi.importCameras = false;
            mi.importLights = false;
            mi.importBlendShapes = false;
            mi.importNormals = ModelImporterNormals.Import;
            mi.importTangents = ModelImporterTangents.CalculateMikk;
            mi.materialImportMode = ModelImporterMaterialImportMode.ImportViaMaterialDescription;
            mi.materialLocation = ModelImporterMaterialLocation.InPrefab;

            bool animated = IsCharacter(assetPath) && !assetPath.EndsWith("_Knife.fbx", StringComparison.OrdinalIgnoreCase);
            if (animated)
            {
                mi.animationType = ModelImporterAnimationType.Generic;
                mi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                mi.optimizeGameObjects = false;
                mi.importAnimation = true;
                mi.resampleCurves = true;
                mi.animationCompression = ModelImporterAnimationCompression.KeyframeReduction;
            }
            else
            {
                mi.animationType = ModelImporterAnimationType.None;
                mi.importAnimation = false;
                mi.addCollider = false;
            }
        }

        void OnPreprocessAnimation()
        {
            if (!IsCharacter(assetPath)) return;
            var mi = (ModelImporter)assetImporter;
            var clips = mi.defaultClipAnimations;
            foreach (var c in clips)
            {
                string n = c.name;
                int bar = n.LastIndexOf('|');
                if (bar >= 0) n = n.Substring(bar + 1);
                c.name = n;
                c.loopTime = Array.IndexOf(LoopingClips, n) >= 0;
                c.lockRootRotation = false;
                c.lockRootHeightY = false;
                c.lockRootPositionXZ = false;
            }
            mi.clipAnimations = clips;
        }

        void OnPreprocessTexture()
        {
            if (!IsCharacter(assetPath) && !IsMap(assetPath)) return;
            var ti = (TextureImporter)assetImporter;
            ti.maxTextureSize = 4096;
            ti.mipmapEnabled = true;
            ti.anisoLevel = 4;
            ti.textureCompression = TextureImporterCompression.CompressedHQ;
            string f = Path.GetFileNameWithoutExtension(assetPath);
            if (f.EndsWith("_Normal", StringComparison.OrdinalIgnoreCase))
                ti.textureType = TextureImporterType.NormalMap;
            else if (f.EndsWith("_Mask", StringComparison.OrdinalIgnoreCase) || f.EndsWith("_AO", StringComparison.OrdinalIgnoreCase))
            {
                ti.textureType = TextureImporterType.Default;
                ti.sRGBTexture = false;
                ti.alphaSource = TextureImporterAlphaSource.FromInput;
            }
        }
    }
}
