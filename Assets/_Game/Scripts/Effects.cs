using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace FightingGame
{
    /// <summary>Short-lived hit sparks, impact rings and orb trails. Uses an additive unlit material.</summary>
    public class Effects
    {
        class Particle
        {
            public Transform T;
            public Renderer R;
            public Color Color;
            public Vector3 V;
            public float Life, Max, Grow;
            public Vector3 BaseScale;
            public bool Spark;
        }

        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");

        readonly List<Particle> live = new List<Particle>();
        readonly Material glow;
        readonly Transform cam;
        readonly MaterialPropertyBlock mpb = new MaterialPropertyBlock();

        public Effects(Material glowTemplate, Transform cam)
        {
            glow = glowTemplate;
            this.cam = cam;
        }

        public void Spark(Vector3 pos, Color c, int count, float power)
        {
            for (int i = 0; i < count; i++)
            {
                var v = new Vector3(Random.value - 0.5f, Random.value - 0.3f, Random.value - 0.5f).normalized
                        * ((3 + Random.value * 5) * power);
                var t = Mesh(PrimitiveType.Cube, pos, new Vector3(0.06f, 0.06f, 0.22f));
                t.rotation = Quaternion.LookRotation(v);
                Add(t, c, 0.35f, v, 0, spark: true);
            }

            var ring = new GameObject("ImpactRing").transform;
            ring.position = pos;
            ring.rotation = Quaternion.LookRotation(pos - cam.position);
            var lr = ring.gameObject.AddComponent<LineRenderer>();
            lr.useWorldSpace = false;
            lr.loop = true;
            lr.alignment = LineAlignment.TransformZ;
            lr.widthMultiplier = 0.08f;
            lr.shadowCastingMode = ShadowCastingMode.Off;
            lr.sharedMaterial = glow;
            const int n = 28;
            lr.positionCount = n;
            for (int i = 0; i < n; i++)
            {
                float a = i * Mathf.PI * 2 / n;
                lr.SetPosition(i, new Vector3(Mathf.Cos(a), Mathf.Sin(a), 0) * 0.22f);
            }
            Add(ring, Color.white * 0.8f, 0.22f, Vector3.zero, 2.5f * power, spark: false);
        }

        public void Trail(Vector3 pos, Color c)
        {
            var t = Mesh(PrimitiveType.Sphere, pos, Vector3.one * 0.4f);
            Add(t, c * 0.8f, 0.25f, Vector3.zero, -0.6f, spark: false);
        }

        Transform Mesh(PrimitiveType type, Vector3 pos, Vector3 scale)
        {
            var go = GameObject.CreatePrimitive(type);
            Object.Destroy(go.GetComponent<Collider>());
            var r = go.GetComponent<MeshRenderer>();
            r.sharedMaterial = glow;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            go.transform.position = pos;
            go.transform.localScale = scale;
            return go.transform;
        }

        void Add(Transform t, Color c, float life, Vector3 v, float grow, bool spark)
        {
            var p = new Particle
            {
                T = t, R = t.GetComponent<Renderer>(), Color = c, V = v, Life = life, Max = life,
                Grow = grow, BaseScale = t.localScale, Spark = spark,
            };
            SetColor(p, 1);
            live.Add(p);
        }

        void SetColor(Particle p, float k)
        {
            mpb.SetColor(BaseColorId, p.Color * k);
            p.R.SetPropertyBlock(mpb);
        }

        public void Tick(float dt)
        {
            for (int i = live.Count - 1; i >= 0; i--)
            {
                var p = live[i];
                p.Life -= dt;
                float k = Mathf.Max(p.Life / p.Max, 0);
                if (p.Spark)
                {
                    p.V.y -= 9 * dt;
                    p.T.position += p.V * dt;
                    var s = p.BaseScale; s.z *= 0.3f + k;
                    p.T.localScale = s;
                }
                else p.T.localScale = p.BaseScale * Mathf.Max(0.05f, 1 + (1 - k) * p.Grow);
                SetColor(p, k);

                if (p.Life <= 0)
                {
                    Object.Destroy(p.T.gameObject);
                    live.RemoveAt(i);
                }
            }
        }
    }
}
