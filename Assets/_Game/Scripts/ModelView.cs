using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;
using UnityEngine.Rendering;

namespace FightingGame
{
    /// <summary>
    /// Drives an imported, animated character model from fighter state. Clips are sampled at times derived
    /// from gameplay (an attack clip is sampled at the move's elapsed time), so animation frames always line
    /// up with startup/active/recovery and hitstop freezes them exactly. A two-input mixer crossfades states.
    /// The left-facing fighter is mirrored rather than turned, so both always show their designed side.
    /// </summary>
    public class ModelView : MonoBehaviour
    {
        static readonly int EmissionId = Shader.PropertyToID("_EmissionColor");

        CharacterDef def;
        Transform model, mirror;
        PlayableGraph graph;
        AnimationMixerPlayable mixer;
        readonly Dictionary<string, AnimationClipPlayable> playables = new Dictionary<string, AnimationClipPlayable>();
        string current, previous;
        float fade = 1, fadeDuration = 0.1f, prevTime;
        float loopTime;
        int facing = 1;
        Renderer[] renderers;
        MaterialPropertyBlock mpb;
        bool flashing;
        TrailRenderer trail;
        SpringChain cape;

        public Transform WeaponTip { get; private set; }
        public Transform Weapon { get; private set; }

        Vector2 lastTip;
        bool hasLastTip;
        Transform hipsBone, chestBone, neckBone, headBone;

        /// <summary>
        /// Stage-plane X of the animated body (hips, torso, head), so hurtboxes follow lunges and leans instead of
        /// staying pinned to the fighter's root.
        /// </summary>
        public bool GetBodyX(out float hips, out float torso, out float head)
        {
            hips = torso = head = 0;
            if (hipsBone == null || chestBone == null || headBone == null) return false;
            hips = hipsBone.position.x;
            torso = neckBone != null ? (chestBone.position.x + neckBone.position.x) * 0.5f : chestBone.position.x;
            head = headBone.position.x;
            return true;
        }

        /// <summary>The blade as a 2D segment in the stage plane, sampled from the animated weapon bones.</summary>
        public bool GetBlade(out Vector2 baseP, out Vector2 tipP, out Vector2 prevTip)
        {
            baseP = tipP = prevTip = default;
            if (Weapon == null || WeaponTip == null) return false;
            Vector3 grip = Weapon.position, tip = WeaponTip.position;
            Vector3 b = grip + (tip - grip).normalized * def.bladeStart;
            baseP = b; tipP = tip;
            prevTip = hasLastTip ? lastTip : tipP;
            return true;
        }

        /// <summary>Remember where the tip was this frame, so the next frame can test the arc it swept.</summary>
        public void StoreBladeSample()
        {
            if (WeaponTip == null) return;
            lastTip = WeaponTip.position;
            hasLastTip = true;
        }

        public static ModelView Create(CharacterDef def, Transform parent, Material trailTemplate)
        {
            var root = new GameObject(def.id + "_View");
            root.transform.SetParent(parent, false);
            var v = root.AddComponent<ModelView>();
            v.Init(def, trailTemplate);
            return v;
        }

        void Init(CharacterDef d, Material trailTemplate)
        {
            def = d;
            // mirror pivot: turned to face +X; its local Z is flipped for the left-facing fighter
            mirror = new GameObject("Mirror").transform;
            mirror.SetParent(transform, false);
            mirror.localRotation = Quaternion.Euler(0, 90, 0);
            var go = Instantiate(def.prefab, mirror);
            go.name = def.id;
            model = go.transform;
            model.localPosition = Vector3.zero;
            // Blender's -Y forward arrives as Unity -Z after the FBX axis conversion: turn it to face the pivot's +Z
            model.localRotation = Quaternion.Euler(0, 180, 0);

            var animator = go.GetComponentInChildren<Animator>();
            if (animator == null) animator = go.AddComponent<Animator>();
            animator.applyRootMotion = false;
            animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            animator.runtimeAnimatorController = null;

            graph = PlayableGraph.Create(def.id + "_Anim");
            graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
            var output = AnimationPlayableOutput.Create(graph, "Animation", animator);
            mixer = AnimationMixerPlayable.Create(graph, 2);
            output.SetSourcePlayable(mixer);
            foreach (var clip in def.clips)
            {
                if (clip == null) continue;
                var p = AnimationClipPlayable.Create(graph, clip);
                p.SetApplyFootIK(false);
                p.SetApplyPlayableIK(false);
                playables[clip.name] = p;
            }

            renderers = go.GetComponentsInChildren<Renderer>();
            mpb = new MaterialPropertyBlock();
            foreach (var r in renderers)
            {
                r.shadowCastingMode = ShadowCastingMode.On;
                if (r is SkinnedMeshRenderer smr) smr.updateWhenOffscreen = true;
            }

            WeaponTip = FindDeep(model, def.weaponTipBone);
            Weapon = FindDeep(model, def.weaponBone);
            hipsBone = FindDeep(model, "hips");
            chestBone = FindDeep(model, "chest");
            neckBone = FindDeep(model, "neck");
            headBone = FindDeep(model, "head");
            if (WeaponTip != null && trailTemplate != null)
            {
                trail = WeaponTip.gameObject.AddComponent<TrailRenderer>();
                trail.time = 0.09f;
                trail.minVertexDistance = 0.02f;
                trail.widthMultiplier = 0.11f;
                trail.widthCurve = AnimationCurve.EaseInOut(0, 1, 1, 0);
                trail.shadowCastingMode = ShadowCastingMode.Off;
                trail.receiveShadows = false;
                trail.material = new Material(trailTemplate);
                trail.material.SetColor("_BaseColor", def.trailColor);
                trail.emitting = false;
            }

            if (def.capeBones != null && def.capeBones.Length > 0)
            {
                var bones = new List<Transform>();
                foreach (var b in def.capeBones)
                {
                    var t = FindDeep(model, b);
                    if (t != null) bones.Add(t);
                }
                if (bones.Count > 0)
                {
                    cape = gameObject.AddComponent<SpringChain>();
                    cape.Init(bones.ToArray());
                }
            }

            if (def.emberAura && StageFX.ParticleMaterial != null)
            {
                var chest = FindDeep(model, "chest");
                if (chest != null) StageFX.EmberAura(chest, StageFX.ParticleMaterial);
            }

            Play("Idle", 0, true, 0);
        }

        void OnDestroy()
        {
            if (graph.IsValid()) graph.Destroy();
        }

        static Transform FindDeep(Transform t, string name)
        {
            if (t.name == name) return t;
            foreach (Transform c in t)
            {
                var r = FindDeep(c, name);
                if (r != null) return r;
            }
            return null;
        }

        float Length(string clip) => playables.TryGetValue(clip, out var p) ? p.GetAnimationClip().length : 0f;

        /// <summary>Sample a clip at an explicit time, crossfading from whatever played before.</summary>
        public void Play(string clip, float time, bool loop, float crossfade)
        {
            if (!playables.ContainsKey(clip)) clip = "Idle";
            if (!playables.ContainsKey(clip)) return;
            if (clip != current)
            {
                if (current != null) prevTime = (float)playables[current].GetTime();
                previous = current;
                current = clip;
                fade = crossfade <= 0 ? 1 : 0;
                fadeDuration = Mathf.Max(0.0001f, crossfade);
                graph.Disconnect(mixer, 0);
                graph.Disconnect(mixer, 1);
                graph.Connect(playables[current], 0, mixer, 0);
                if (previous != null && previous != current) graph.Connect(playables[previous], 0, mixer, 1);
            }
            float len = Length(clip);
            float t = loop ? Mathf.Repeat(time, Mathf.Max(0.0001f, len)) : Mathf.Clamp(time, 0, Mathf.Max(0, len - 0.0001f));
            playables[current].SetTime(t);
            if (previous != null && previous != current) playables[previous].SetTime(prevTime);
        }

        /// <summary>Choose and sample the clip for this frame. dt is gameplay time (0 during hitstop).</summary>
        public void Sync(Fighter f, float dt, float realDt)
        {
            loopTime += dt;
            switch (f.State)
            {
                case FState.Idle:
                    Play("Idle", loopTime, true, 0.12f);
                    break;
                case FState.Walk:
                    bool forward = f.VX * f.Facing > 0;
                    float speed = forward ? f.Data.WalkSpeed : f.Data.BackSpeed;
                    Play(forward ? "WalkFwd" : "WalkBack", loopTime * Mathf.Abs(f.VX) / Mathf.Max(0.1f, speed), true, 0.1f);
                    break;
                case FState.Jump:
                    Play("Jump", f.AirTime, false, 0.06f);
                    break;
                case FState.Block:
                    Play("Block", f.T, false, 0.05f);
                    break;
                case FState.Hit:
                    Play("Hit", f.T / Mathf.Max(0.15f, f.Stun) * Length("Hit") * 0.85f, false, 0.03f);
                    break;
                case FState.KO:
                    Play("KO", f.T, false, 0.05f);
                    break;
                case FState.Win:
                {
                    float len = Length("Win"), intro = 0.4f;
                    float t = f.T < len ? f.T : intro + Mathf.Repeat(f.T - intro, Mathf.Max(0.1f, len - intro));
                    Play("Win", t, false, 0.15f);
                    break;
                }
                case FState.Attack:
                    Play(f.Move.Id, f.T, false, 0.04f);
                    break;
            }

            fade = Mathf.Min(1, fade + realDt / fadeDuration * (dt > 0 ? 1 : 0.25f));
            bool blending = previous != null && previous != current && fade < 1;
            mixer.SetInputWeight(0, blending ? fade : 1);
            mixer.SetInputWeight(1, blending ? 1 - fade : 0);

            if (f.Facing != facing)
            {
                facing = f.Facing;
                if (cape != null) cape.ResetSim();
            }
            mirror.localScale = new Vector3(1, 1, facing);
            graph.Evaluate(0);

            if (trail != null)
            {
                bool swing = f.State == FState.Attack && f.Move.HasHitbox &&
                             f.T > f.Move.Startup - 0.05f && f.T < f.Move.Startup + f.Move.Active + 0.06f;
                trail.emitting = swing;
            }

            bool flash = f.Flash > 0;
            if (flash != flashing)
            {
                flashing = flash;
                mpb.SetColor(EmissionId, flash ? new Color(0.22f, 0.19f, 0.16f) : Color.black);
                foreach (var r in renderers)
                    if (!(r is TrailRenderer)) r.SetPropertyBlock(mpb);
            }
        }

        void LateUpdate()
        {
            if (cape != null) cape.Step(Time.deltaTime);
        }
    }
}
