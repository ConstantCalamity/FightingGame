using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace FightingGame
{
    /// <summary>
    /// Impact effects: velocity-stretched spark streaks, a bright flash sprite, an expanding impact ring and
    /// short point-light flashes. Sparks and flashes are emitted into two shared particle systems.
    /// </summary>
    public class Effects
    {
        class RingFx
        {
            public Transform T;
            public LineRenderer L;
            public Color Color;
            public float Life, Max, Grow;
        }

        class LightFlash
        {
            public Light L;
            public float Life, Max, Peak;
        }

        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");

        readonly Material glow;
        readonly Transform cam;
        readonly ParticleSystem sparks, clash, flashes;
        readonly List<RingFx> rings = new List<RingFx>();
        readonly List<LightFlash> lights = new List<LightFlash>();
        readonly MaterialPropertyBlock mpb = new MaterialPropertyBlock();

        public Effects(Material glowTemplate, Material particle, Transform cam)
        {
            glow = glowTemplate;
            this.cam = cam;
            sparks = SparkSystem("ImpactSparks", particle, 0.035f, 1.4f, 2.5f, Color.white);
            // blade-clash sparks: longer streaks that cool from yellow-white to orange as they fly
            clash = SparkSystem("ClashSparks", particle, 0.065f, 1.1f, 1.4f, new Color(1f, 0.5f, 0.2f));

            flashes = MakeSystem("ImpactFlash", particle, ParticleSystemRenderMode.Billboard);
            var fs = flashes.sizeOverLifetime; fs.enabled = true;
            fs.size = new ParticleSystem.MinMaxCurve(1, AnimationCurve.EaseInOut(0, 0.4f, 1, 1.6f));
            var fc = flashes.colorOverLifetime; fc.enabled = true;
            var fg = new Gradient();
            fg.SetKeys(new[] { new GradientColorKey(Color.white, 0), new GradientColorKey(Color.white, 1) },
                       new[] { new GradientAlphaKey(1, 0), new GradientAlphaKey(0, 1) });
            fc.color = fg;
        }

        /// <summary>Velocity-stretched sparks that fall, slow down and fade; endTint multiplies the colour by end of life.</summary>
        static ParticleSystem SparkSystem(string name, Material mat, float velocityScale, float gravity, float drag, Color endTint)
        {
            var ps = MakeSystem(name, mat, ParticleSystemRenderMode.Stretch);
            var r = ps.GetComponent<ParticleSystemRenderer>();
            r.velocityScale = velocityScale;
            r.lengthScale = 1.5f;
            var main = ps.main;
            main.gravityModifier = gravity;
            var size = ps.sizeOverLifetime; size.enabled = true;
            size.size = new ParticleSystem.MinMaxCurve(1, AnimationCurve.EaseInOut(0, 1, 1, 0.2f));
            var col = ps.colorOverLifetime; col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0), new GradientColorKey(endTint, 1) },
                      new[] { new GradientAlphaKey(1, 0), new GradientAlphaKey(0.9f, 0.6f), new GradientAlphaKey(0, 1) });
            col.color = g;
            var lv = ps.limitVelocityOverLifetime; lv.enabled = true; lv.drag = drag; lv.multiplyDragByParticleSize = false;
            return ps;
        }

        static ParticleSystem MakeSystem(string name, Material mat, ParticleSystemRenderMode mode)
        {
            var go = new GameObject(name);
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var main = ps.main;
            main.loop = false;
            main.playOnAwake = false;
            main.maxParticles = 2000;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            var em = ps.emission; em.enabled = false;
            var shape = ps.shape; shape.enabled = false;
            var r = go.GetComponent<ParticleSystemRenderer>();
            r.sharedMaterial = mat;
            r.renderMode = mode;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            ps.Play();
            return ps;
        }

        /// <summary>Spray of stretched sparks plus a flash and a ring. bias tilts the spray (e.g. away from the hit).</summary>
        public void Spark(Vector3 pos, Color c, int count, float power, Vector3 bias = default, bool ring = true)
        {
            var ep = new ParticleSystem.EmitParams { applyShapeToPosition = false };
            for (int i = 0; i < count; i++)
            {
                Vector3 v = (Random.onUnitSphere + bias * 0.8f).normalized;
                v.z *= 0.5f;   // keep the spray mostly in the camera plane where it reads best
                ep.position = pos;
                ep.velocity = v * Random.Range(3f, 9f) * power;
                ep.startColor = Color.Lerp(c, Color.white, Random.value * 0.4f);
                ep.startSize = Random.Range(0.015f, 0.035f) * Mathf.Sqrt(power);
                ep.startLifetime = Random.Range(0.18f, 0.5f);
                sparks.Emit(ep, 1);
            }
            ep.velocity = Vector3.zero;
            ep.startColor = c;
            ep.startSize = 0.45f * power;
            ep.startLifetime = 0.09f;
            flashes.Emit(ep, 1);
            if (ring) Ring(pos, Color.white * 0.8f, 0.22f, 2.5f * power);
        }

        /// <summary>
        /// Blade-on-blade sparks and nothing else: a fast white-hot spray glancing up and back toward the attacker,
        /// arcing down under gravity and cooling to orange, plus a few slower, heavier sparks that linger and fall.
        /// </summary>
        public void ClashSparks(Vector3 pos, int towardX)
        {
            var ep = new ParticleSystem.EmitParams { applyShapeToPosition = false };
            var hot = new Color(4f, 2.9f, 1.4f);
            var orange = new Color(3.4f, 1.4f, 0.35f);
            for (int i = 0; i < 90; i++)
            {
                // a fan in the stage plane: mostly upward and toward the attacker, with some spray everywhere
                float ang = Random.value < 0.75f
                    ? Random.Range(15f, 80f) * Mathf.Deg2Rad
                    : Random.Range(-40f, 170f) * Mathf.Deg2Rad;
                var v = new Vector3(Mathf.Cos(ang) * towardX, Mathf.Sin(ang), Random.Range(-0.35f, 0.35f)).normalized;
                ep.position = pos + new Vector3(Random.Range(-0.04f, 0.04f), Random.Range(-0.04f, 0.04f), 0);
                ep.velocity = v * Random.Range(4f, 12f);
                ep.startColor = Color.Lerp(hot, orange, Random.value * Random.value);
                ep.startSize = Random.Range(0.014f, 0.026f);
                ep.startLifetime = Random.Range(0.3f, 0.8f);
                clash.Emit(ep, 1);
            }
            for (int i = 0; i < 14; i++)
            {
                // a few slower, heavier sparks that arc over and fall
                var v = new Vector3(Random.Range(-1f, 1f), Random.Range(0.3f, 1f), Random.Range(-0.3f, 0.3f)).normalized;
                ep.position = pos;
                ep.velocity = v * Random.Range(2f, 4.5f);
                ep.startColor = orange;
                ep.startSize = Random.Range(0.025f, 0.04f);
                ep.startLifetime = Random.Range(0.8f, 1.3f);
                clash.Emit(ep, 1);
            }
        }

        public void Ring(Vector3 pos, Color c, float life, float grow, float radius = 0.22f, float width = 0.08f)
        {
            var t = new GameObject("ImpactRing").transform;
            t.position = pos;
            t.rotation = Quaternion.LookRotation(pos - cam.position);
            var lr = t.gameObject.AddComponent<LineRenderer>();
            lr.useWorldSpace = false;
            lr.loop = true;
            lr.alignment = LineAlignment.TransformZ;
            lr.widthMultiplier = width;
            lr.shadowCastingMode = ShadowCastingMode.Off;
            lr.sharedMaterial = glow;
            const int n = 32;
            lr.positionCount = n;
            for (int i = 0; i < n; i++)
            {
                float a = i * Mathf.PI * 2 / n;
                lr.SetPosition(i, new Vector3(Mathf.Cos(a), Mathf.Sin(a), 0) * radius);
            }
            var r = new RingFx { T = t, L = lr, Color = c, Life = life, Max = life, Grow = grow };
            SetColor(r.L, c);
            rings.Add(r);
        }

        public void FlashLight(Vector3 pos, Color c, float intensity, float range, float duration)
        {
            var go = new GameObject("FlashLight");
            go.transform.position = pos;
            var l = go.AddComponent<Light>();
            l.type = LightType.Point;
            l.color = c;
            l.range = range;
            l.intensity = intensity;
            l.shadows = LightShadows.None;
            lights.Add(new LightFlash { L = l, Life = duration, Max = duration, Peak = intensity });
        }

        void SetColor(Renderer r, Color c)
        {
            mpb.SetColor(BaseColorId, c);
            r.SetPropertyBlock(mpb);
        }

        /// <summary>Rings and light flashes animate on real time so they still read during hitstop.</summary>
        public void Tick(float dt)
        {
            for (int i = rings.Count - 1; i >= 0; i--)
            {
                var r = rings[i];
                r.Life -= dt;
                float k = Mathf.Max(r.Life / r.Max, 0);
                r.T.localScale = Vector3.one * (1 + (1 - k) * r.Grow);
                SetColor(r.L, r.Color * k);
                if (r.Life <= 0)
                {
                    Object.Destroy(r.T.gameObject);
                    rings.RemoveAt(i);
                }
            }
            for (int i = lights.Count - 1; i >= 0; i--)
            {
                var f = lights[i];
                f.Life -= dt;
                f.L.intensity = f.Peak * Mathf.Max(0, f.Life / f.Max);
                if (f.Life <= 0)
                {
                    Object.Destroy(f.L.gameObject);
                    lights.RemoveAt(i);
                }
            }
        }

        /// <summary>Glowing streak for travelling projectiles (kept for the knife).</summary>
        public void Trail(Vector3 pos, Color c)
        {
            var ep = new ParticleSystem.EmitParams { position = pos, velocity = Vector3.zero, startColor = c, startSize = 0.25f, startLifetime = 0.15f };
            flashes.Emit(ep, 1);
        }
    }
}
