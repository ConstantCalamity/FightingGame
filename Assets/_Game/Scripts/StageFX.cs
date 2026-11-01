using UnityEngine;
using UnityEngine.Rendering;

namespace FightingGame
{
    /// <summary>
    /// Particle effects built in code. Fire is layered: soft heat glow, a hot core and outer tongues drawn from an
    /// animated flame flipbook, rising smoke (alpha-blended) and velocity-stretched sparks. Weather (embers, ash,
    /// snow), Corvin's ember aura and the ash-wave projectile reuse the same pieces.
    /// </summary>
    public static class StageFX
    {
        /// <summary>Soft additive dot (sparks, glows). Set by GameManager.</summary>
        public static Material ParticleMaterial;
        /// <summary>Additive 4x4 flame flipbook.</summary>
        public static Material FlameMaterial;
        /// <summary>Alpha-blended smoke puff.</summary>
        public static Material SmokeMaterial;

        static ParticleSystem New(string name, Transform parent, Vector3 pos, Material mat, int max,
                                  ParticleSystemRenderMode mode = ParticleSystemRenderMode.Billboard)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.transform.position = pos;
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var main = ps.main;
            main.loop = true;
            main.duration = 2f;
            main.maxParticles = max;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.playOnAwake = true;
            var r = go.GetComponent<ParticleSystemRenderer>();
            r.sharedMaterial = mat != null ? mat : ParticleMaterial;
            r.renderMode = mode;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            if (mode == ParticleSystemRenderMode.Stretch) { r.velocityScale = 0.06f; r.lengthScale = 1.2f; }
            return ps;
        }

        static Gradient Fade(Color a, Color b, Color c, float peak = 1f)
        {
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(a, 0), new GradientColorKey(b, 0.45f), new GradientColorKey(c, 1) },
                      new[] { new GradientAlphaKey(0, 0), new GradientAlphaKey(peak, 0.12f), new GradientAlphaKey(peak * 0.8f, 0.5f), new GradientAlphaKey(0, 1) });
            return g;
        }

        static void Flipbook(ParticleSystem ps)
        {
            if (FlameMaterial == null) return;
            var tsa = ps.textureSheetAnimation;
            tsa.enabled = true;
            tsa.numTilesX = 4; tsa.numTilesY = 4;
            tsa.animation = ParticleSystemAnimationType.WholeSheet;
            tsa.frameOverTime = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.Linear(0, 0, 1, 1));
            tsa.startFrame = new ParticleSystem.MinMaxCurve(0, 15);
            tsa.cycleCount = 1;
        }

        /// <summary>The flame layers on their own; used by fires, the ash wave and anything else that burns.</summary>
        static void Flames(Transform parent, Vector3 pos, float scale, float rate, Color hot, Color mid, Color cool, float speed,
                           Vector3 boxSize, string name = "Flames")
        {
            var ps = New(name, parent, pos, FlameMaterial, 600);
            ps.transform.rotation = Quaternion.identity;
            var main = ps.main;
            main.startLifetime = new ParticleSystem.MinMaxCurve(0.4f, 0.75f);
            main.startSpeed = 0;
            main.startSize3D = true;
            main.startSizeX = new ParticleSystem.MinMaxCurve(0.42f * scale, 0.62f * scale);
            main.startSizeY = new ParticleSystem.MinMaxCurve(0.5f * scale, 0.8f * scale);
            main.startSizeZ = new ParticleSystem.MinMaxCurve(1f, 1f);
            main.startRotation = new ParticleSystem.MinMaxCurve(-0.12f, 0.12f);
            var em = ps.emission; em.rateOverTime = rate;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box; sh.scale = boxSize * scale;
            var vel = ps.velocityOverLifetime; vel.enabled = true; vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(-0.04f, 0.04f); vel.y = new ParticleSystem.MinMaxCurve(speed * 0.35f * scale, speed * 0.6f * scale);
            vel.z = new ParticleSystem.MinMaxCurve(0f, 0f);
            var col = ps.colorOverLifetime; col.enabled = true; col.color = Fade(hot, mid, cool);
            // born full width at the base, then taper as they rise and cool
            var size = ps.sizeOverLifetime; size.enabled = true;
            size.size = new ParticleSystem.MinMaxCurve(1, new AnimationCurve(new Keyframe(0, 0.8f), new Keyframe(0.2f, 1f), new Keyframe(1, 0.3f)));
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.14f * scale; noise.frequency = 1.4f; noise.scrollSpeed = 1.0f;
            Flipbook(ps);
            ps.Play();
        }

        static void Smoke(Transform parent, Vector3 pos, float scale, float rate, float darkness, Vector3 boxSize)
        {
            if (SmokeMaterial == null) return;
            var ps = New("Smoke", parent, pos, SmokeMaterial, 300);
            var main = ps.main;
            main.startLifetime = new ParticleSystem.MinMaxCurve(2.2f, 3.6f);
            main.startSpeed = 0;
            main.startSize = new ParticleSystem.MinMaxCurve(0.35f * scale, 0.6f * scale);
            main.startRotation = new ParticleSystem.MinMaxCurve(0, Mathf.PI * 2);
            var em = ps.emission; em.rateOverTime = rate;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box; sh.scale = boxSize * scale;
            var vel = ps.velocityOverLifetime; vel.enabled = true; vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(-0.1f, 0.25f); vel.y = new ParticleSystem.MinMaxCurve(0.5f * scale, 0.9f * scale);
            vel.z = new ParticleSystem.MinMaxCurve(0f, 0.1f);
            var rot = ps.rotationOverLifetime; rot.enabled = true; rot.z = new ParticleSystem.MinMaxCurve(-0.4f, 0.4f);
            var col = ps.colorOverLifetime; col.enabled = true;
            var c = new Color(darkness, darkness * 0.95f, darkness * 0.9f);
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(c * 1.6f, 0), new GradientColorKey(c, 0.4f), new GradientColorKey(c, 1) },
                      new[] { new GradientAlphaKey(0, 0), new GradientAlphaKey(0.42f, 0.15f), new GradientAlphaKey(0.25f, 0.6f), new GradientAlphaKey(0, 1) });
            col.color = g;
            var size = ps.sizeOverLifetime; size.enabled = true;
            size.size = new ParticleSystem.MinMaxCurve(1, AnimationCurve.Linear(0, 0.6f, 1, 3.2f));
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.25f; noise.frequency = 0.4f;
            ps.Play();
        }

        static void Sparks(Transform parent, Vector3 pos, float scale, float rate, float spread)
        {
            var ps = New("Sparks", parent, pos, ParticleMaterial, 200, ParticleSystemRenderMode.Stretch);
            ps.transform.rotation = Quaternion.Euler(-90, 0, 0);
            var main = ps.main;
            main.startLifetime = new ParticleSystem.MinMaxCurve(0.8f, 2.0f);
            main.startSpeed = new ParticleSystem.MinMaxCurve(0.8f * scale, 2.6f * scale);
            main.startSize = new ParticleSystem.MinMaxCurve(0.012f, 0.03f);
            main.gravityModifier = -0.05f;
            var em = ps.emission; em.rateOverTime = rate;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Cone; sh.angle = spread; sh.radius = 0.12f * scale;
            var noise = ps.noise; noise.enabled = true; noise.strength = 1.0f; noise.frequency = 1.0f;
            var col = ps.colorOverLifetime; col.enabled = true;
            col.color = Fade(new Color(1f, 0.85f, 0.5f) * 2f, new Color(1f, 0.45f, 0.12f) * 1.5f, new Color(0.6f, 0.12f, 0.03f));
            var drag = ps.limitVelocityOverLifetime; drag.enabled = true; drag.drag = 0.8f;
            ps.Play();
        }

        static void Glow(Transform parent, Vector3 pos, float size, Color c)
        {
            var ps = New("HeatGlow", parent, pos, ParticleMaterial, 20);
            var main = ps.main;
            main.startLifetime = 0.8f;
            main.startSpeed = 0;
            main.startSize = size;
            main.startColor = c;
            var em = ps.emission; em.rateOverTime = 6;
            var sh = ps.shape; sh.enabled = false;
            var col = ps.colorOverLifetime; col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0), new GradientColorKey(Color.white, 1) },
                      new[] { new GradientAlphaKey(0, 0), new GradientAlphaKey(1, 0.3f), new GradientAlphaKey(1, 0.7f), new GradientAlphaKey(0, 1) });
            col.color = g;
            ps.Play();
        }

        /// <summary>A brazier / torch fire. scale ~1 is a brazier.</summary>
        public static void Fire(Transform parent, Vector3 pos, float scale, Material _ = null)
        {
            scale = Mathf.Max(0.35f, scale);
            Glow(parent, pos + Vector3.up * 0.25f * scale, 1.6f * scale, new Color(1f, 0.4f, 0.1f) * 0.35f);
            // outer tongues: big, orange-red, slower
            Flames(parent, pos, scale * 1.05f, 34 * scale, new Color(1f, 0.6f, 0.2f) * 1.3f, new Color(1f, 0.32f, 0.06f) * 1.1f,
                   new Color(0.35f, 0.05f, 0.01f), 1.1f, new Vector3(0.34f, 0.05f, 0.34f), "FlameOuter");
            // hot core: a dense near-white bed sitting low in the bowl
            Flames(parent, pos + Vector3.up * 0.02f, scale * 0.7f, 30 * scale, new Color(1f, 0.95f, 0.75f) * 2.0f, new Color(1f, 0.7f, 0.3f) * 1.7f,
                   new Color(1f, 0.3f, 0.05f), 0.9f, new Vector3(0.22f, 0.03f, 0.22f), "FlameCore");
            Smoke(parent, pos + Vector3.up * 0.7f * scale, scale, 7 * scale, 0.09f, new Vector3(0.25f, 0.1f, 0.25f));
            Sparks(parent, pos + Vector3.up * 0.2f * scale, scale, 9 * scale, 22);
        }

        /// <summary>Area effect around the stage: "embers" rise, "snow" and "ash" fall.</summary>
        public static void Weather(Transform parent, string type, Vector3 center, float scale, Material mat = null)
        {
            scale = Mathf.Max(0.5f, scale);
            var mode = type == "embers" ? ParticleSystemRenderMode.Stretch : ParticleSystemRenderMode.Billboard;
            var ps = New(type, parent, center, ParticleMaterial, 3000, mode);
            var main = ps.main;
            var em = ps.emission;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box;
            var noise = ps.noise; noise.enabled = true;
            var col = ps.colorOverLifetime; col.enabled = true;
            switch (type)
            {
                case "snow":
                    sh.scale = new Vector3(40, 1, 22) * scale;
                    ps.transform.position = center + Vector3.up * 12;
                    main.startLifetime = 9; main.startSpeed = new ParticleSystem.MinMaxCurve(0.6f, 1.4f);
                    main.startSize = new ParticleSystem.MinMaxCurve(0.03f, 0.08f);
                    main.gravityModifier = 0.05f;
                    ps.transform.rotation = Quaternion.Euler(90, 0, 0);
                    em.rateOverTime = 260 * scale;
                    noise.strength = 0.6f; noise.frequency = 0.3f;
                    col.color = Fade(new Color(0.9f, 0.93f, 1f), new Color(0.85f, 0.9f, 1f), new Color(0.8f, 0.85f, 0.95f));
                    break;
                case "ash":
                    sh.scale = new Vector3(40, 1, 22) * scale;
                    ps.transform.position = center + Vector3.up * 10;
                    main.startLifetime = 10; main.startSpeed = new ParticleSystem.MinMaxCurve(0.2f, 0.6f);
                    main.startSize = new ParticleSystem.MinMaxCurve(0.025f, 0.06f);
                    ps.transform.rotation = Quaternion.Euler(90, 0, 0);
                    em.rateOverTime = 120 * scale;
                    noise.strength = 0.9f; noise.frequency = 0.25f;
                    col.color = Fade(new Color(0.45f, 0.42f, 0.4f), new Color(0.35f, 0.33f, 0.3f), new Color(0.2f, 0.2f, 0.2f));
                    break;
                default: // embers: drifting, flickering streaks
                    sh.scale = new Vector3(30, 4, 16) * scale;
                    main.startLifetime = new ParticleSystem.MinMaxCurve(4, 8);
                    main.startSpeed = new ParticleSystem.MinMaxCurve(0.1f, 0.4f);
                    main.startSize = new ParticleSystem.MinMaxCurve(0.015f, 0.04f);
                    main.gravityModifier = -0.02f;
                    em.rateOverTime = 45 * scale;
                    noise.strength = 0.7f; noise.frequency = 0.4f;
                    col.color = Fade(new Color(1f, 0.7f, 0.3f) * 1.6f, new Color(1f, 0.4f, 0.1f) * 1.3f, new Color(0.6f, 0.1f, 0.02f));
                    break;
            }
            ps.Simulate(8f, true, true);
            ps.Play();
        }

        /// <summary>Embers, small flames and soot drifting off a character's armour.</summary>
        public static void EmberAura(Transform bone, Material mat = null)
        {
            var ps = New("EmberAura", bone, bone.position, ParticleMaterial, 300, ParticleSystemRenderMode.Stretch);
            ps.transform.localPosition = Vector3.zero;
            var main = ps.main;
            main.startLifetime = new ParticleSystem.MinMaxCurve(0.8f, 1.8f);
            main.startSpeed = new ParticleSystem.MinMaxCurve(0.1f, 0.5f);
            main.startSize = new ParticleSystem.MinMaxCurve(0.012f, 0.03f);
            main.gravityModifier = -0.12f;
            var em = ps.emission; em.rateOverTime = 34;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box; sh.scale = new Vector3(0.5f, 0.9f, 0.35f);
            sh.position = new Vector3(0, -0.2f, 0);
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.6f; noise.frequency = 0.9f;
            var col = ps.colorOverLifetime; col.enabled = true;
            col.color = Fade(new Color(1f, 0.75f, 0.35f) * 2f, new Color(1f, 0.38f, 0.08f) * 1.4f, new Color(0.4f, 0.08f, 0.02f));
            ps.Play();
            if (FlameMaterial != null)
            {
                // occasional wisps of flame licking up from the cracks in the armour
                var wisps = New("EmberWisps", bone, bone.position, FlameMaterial, 60);
                wisps.transform.localPosition = new Vector3(0, -0.1f, 0);
                var wm = wisps.main;
                wm.startLifetime = new ParticleSystem.MinMaxCurve(0.25f, 0.45f);
                wm.startSpeed = 0;
                wm.startSize = new ParticleSystem.MinMaxCurve(0.07f, 0.14f);
                var we = wisps.emission; we.rateOverTime = 9;
                var ws = wisps.shape; ws.shapeType = ParticleSystemShapeType.Box; ws.scale = new Vector3(0.45f, 0.8f, 0.3f);
                var wv = wisps.velocityOverLifetime; wv.enabled = true; wv.space = ParticleSystemSimulationSpace.World;
                wv.x = new ParticleSystem.MinMaxCurve(0f, 0f); wv.y = new ParticleSystem.MinMaxCurve(0.4f, 0.8f); wv.z = new ParticleSystem.MinMaxCurve(0f, 0f);
                var wc = wisps.colorOverLifetime; wc.enabled = true;
                wc.color = Fade(new Color(1f, 0.8f, 0.4f) * 1.8f, new Color(1f, 0.35f, 0.06f) * 1.4f, new Color(0.3f, 0.05f, 0.01f), 0.8f);
                Flipbook(wisps);
                wisps.Play();
            }
        }

        /// <summary>The ash-wave projectile: a rolling wall of fire with a hot core, smoke and a spray of sparks.</summary>
        public static void AshWave(Transform parent, Material particleMat, Material glowMat, int dir)
        {
            Glow(parent, parent.position + Vector3.up * 0.2f, 1.4f, new Color(1f, 0.45f, 0.12f) * 0.5f);
            Flames(parent, parent.position, 1.5f, 160, new Color(1f, 0.62f, 0.28f) * 1.7f, new Color(1f, 0.32f, 0.05f) * 1.4f,
                   new Color(0.25f, 0.04f, 0.01f), 2.4f, new Vector3(0.4f, 0.1f, 0.25f), "WaveFlames");
            Flames(parent, parent.position, 0.8f, 120, new Color(1f, 0.85f, 0.55f) * 1.9f, new Color(1f, 0.55f, 0.18f) * 1.6f,
                   new Color(1f, 0.3f, 0.05f), 2.8f, new Vector3(0.25f, 0.05f, 0.15f), "WaveCore");
            Smoke(parent, parent.position + Vector3.up * 0.6f, 1.2f, 18, 0.06f, new Vector3(0.4f, 0.2f, 0.3f));
            Sparks(parent, parent.position + Vector3.up * 0.1f, 1.4f, 50, 35);

            var light = parent.gameObject.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = new Color(1f, 0.45f, 0.15f);
            light.range = 7;
            light.intensity = 8;
            parent.gameObject.AddComponent<FlickerLight>();
        }

        public static Light PointLight(Transform parent, Vector3 pos, Color color, float intensity, float range, bool flicker)
        {
            var go = new GameObject("MapLight");
            go.transform.SetParent(parent, false);
            go.transform.position = pos;
            var l = go.AddComponent<Light>();
            l.type = LightType.Point;
            l.color = color;
            l.intensity = intensity;
            l.range = range;
            l.shadows = LightShadows.None;
            if (flicker) go.AddComponent<FlickerLight>();
            return l;
        }
    }
}
