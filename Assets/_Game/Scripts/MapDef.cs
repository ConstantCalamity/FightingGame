using System;
using System.Collections.Generic;
using UnityEngine;

namespace FightingGame
{
    /// <summary>One arena: the environment prefab plus its lighting, fog and ambient effects.</summary>
    [CreateAssetMenu(menuName = "Fighting Game/Map")]
    public class MapDef : ScriptableObject
    {
        [Serializable]
        public struct PointLightDef
        {
            public Vector3 position;
            public Color color;
            public float intensity, range;
        }

        [Serializable]
        public struct FxDef
        {
            public string type;
            public Vector3 position;
            public float scale;
        }

        public string displayName;
        public GameObject prefab;
        public Vector3 sunEuler = new Vector3(50, -30, 0);
        public Color sunColor = Color.white;
        public float sunIntensity = 1.5f;
        public Color ambientSky = Color.gray, ambientEquator = Color.gray, ambientGround = Color.black;
        public Color fogColor = Color.gray;
        public float fogStart = 25, fogEnd = 120;
        public Color background = Color.black;
        public List<PointLightDef> pointLights = new List<PointLightDef>();
        public List<FxDef> fx = new List<FxDef>();
    }
}
