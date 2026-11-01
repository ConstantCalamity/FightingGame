using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace FightingGame
{
    /// <summary>
    /// Draws hurtboxes (green), pushboxes (blue), attack hitboxes (yellow in startup/recovery, red when active)
    /// and projectile hitboxes as line outlines in the stage plane, slightly in front of the fighters.
    /// </summary>
    public class HitboxDebug
    {
        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        static readonly Color Hurt = new Color(0.2f, 1f, 0.35f);
        static readonly Color Push = new Color(0.25f, 0.5f, 1f) * 0.7f;
        static readonly Color HitActive = new Color(1f, 0.15f, 0.15f) * 1.5f;
        static readonly Color HitInactive = new Color(1f, 0.8f, 0.2f) * 0.5f;
        const float Z = 0f;   // the fighters' plane; the overlay material draws on top so nothing hides it

        readonly Material mat;
        readonly Transform root;
        readonly List<LineRenderer> pool = new List<LineRenderer>();
        readonly List<Rect> rects = new List<Rect>();
        readonly MaterialPropertyBlock mpb = new MaterialPropertyBlock();
        int used;

        public HitboxDebug(Material overlay)
        {
            mat = overlay;
            root = new GameObject("HitboxDebug").transform;
        }

        public void Tick(bool visible, Fighter a, Fighter b, List<Projectile> projectiles)
        {
            used = 0;
            if (visible && a != null && b != null)
            {
                DrawFighter(a);
                DrawFighter(b);
                foreach (var p in projectiles) Capsule(p.Pos2D, p.Pos2D, p.Spec.Radius, HitActive);
            }
            for (int i = used; i < pool.Count; i++) pool[i].enabled = false;
        }

        void DrawFighter(Fighter f)
        {
            f.GetHurtboxes(rects);
            foreach (var r in rects) Rectangle(r, Hurt);
            if (f.State != FState.KO)
                Rectangle(new Rect(f.X - f.PushboxWidth / 2, f.Y, f.PushboxWidth, 0.25f), Push);
            if (f.GetHitbox(out var p0, out var p1, out var radius, out var active))
                Capsule(p0, p1, radius, active ? HitActive : HitInactive);
        }

        void Rectangle(Rect r, Color c)
        {
            var lr = Next(c, 4);
            lr.SetPosition(0, new Vector3(r.xMin, r.yMin, Z));
            lr.SetPosition(1, new Vector3(r.xMax, r.yMin, Z));
            lr.SetPosition(2, new Vector3(r.xMax, r.yMax, Z));
            lr.SetPosition(3, new Vector3(r.xMin, r.yMax, Z));
        }

        /// <summary>Outline of a 2D capsule: two half circles joined by straight sides.</summary>
        void Capsule(Vector2 a, Vector2 b, float radius, Color c)
        {
            const int half = 12;
            Vector2 axis = b - a;
            float ang = axis.sqrMagnitude > 1e-6f ? Mathf.Atan2(axis.y, axis.x) : 0f;
            var lr = Next(c, (half + 1) * 2);
            int k = 0;
            for (int i = 0; i <= half; i++)   // around b (front half)
            {
                float t = ang - Mathf.PI / 2 + Mathf.PI * i / half;
                lr.SetPosition(k++, new Vector3(b.x + Mathf.Cos(t) * radius, b.y + Mathf.Sin(t) * radius, Z));
            }
            for (int i = 0; i <= half; i++)   // around a (back half)
            {
                float t = ang + Mathf.PI / 2 + Mathf.PI * i / half;
                lr.SetPosition(k++, new Vector3(a.x + Mathf.Cos(t) * radius, a.y + Mathf.Sin(t) * radius, Z));
            }
        }

        LineRenderer Next(Color c, int points)
        {
            if (used == pool.Count)
            {
                var go = new GameObject("Box");
                go.transform.SetParent(root, false);
                var l = go.AddComponent<LineRenderer>();
                l.useWorldSpace = true;
                l.loop = true;
                l.widthMultiplier = 0.035f;
                l.sharedMaterial = mat;
                l.shadowCastingMode = ShadowCastingMode.Off;
                l.receiveShadows = false;
                pool.Add(l);
            }
            var lr = pool[used++];
            lr.enabled = true;
            lr.positionCount = points;
            mpb.SetColor(BaseColorId, c);
            lr.SetPropertyBlock(mpb);
            return lr;
        }
    }
}
