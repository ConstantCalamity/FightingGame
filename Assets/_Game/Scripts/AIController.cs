using System.Collections.Generic;
using UnityEngine;

namespace FightingGame
{
    /// <summary>Simple CPU opponent: spaces to its own reach, mixes light/heavy/special, reacts to incoming attacks.</summary>
    public sealed class AIController : IFighterInput
    {
        enum Act { Idle, Approach, Retreat, Block, Parry, JumpIn, HeavyIn }

        public float ParryChance = 0.35f;

        readonly HashSet<FAction> held = new HashSet<FAction>();
        readonly HashSet<FAction> pressed = new HashSet<FAction>();
        Act act;
        float t, cooldown = 0.6f;
        bool judgedAttack, tryParry;
        Projectile judgedProjectile;

        public bool Held(FAction a) => held.Contains(a);
        public bool Pressed(FAction a) => pressed.Contains(a);

        /// <summary>Test hook: just hold block (used to exercise guard decay and guard breaks).</summary>
        public bool AlwaysBlock;

        public void Think(float dt, Fighter me, Fighter op, List<Projectile> projectiles)
        {
            pressed.Clear();
            held.Clear();
            if (AlwaysBlock) { held.Add(FAction.Block); return; }
            cooldown -= dt;
            t -= dt;

            float dx = op.X - me.X, dist = Mathf.Abs(dx);
            float reach = me.Data.Reach;
            var toward = dx > 0 ? FAction.Right : FAction.Left;
            var away = dx > 0 ? FAction.Left : FAction.Right;

            // Parry attempts: decided once per enemy swing; wait until just before it becomes active, then tap
            // block (a fresh block is what parries). Otherwise fall back to an ordinary, short block.
            if (op.State == FState.Attack && op.Move != null && op.Move.HasHitbox && dist < op.Data.Reach + 0.6f)
            {
                if (!judgedAttack) { judgedAttack = true; tryParry = Random.value < ParryChance; }
                float toActive = op.Move.Startup - op.T;
                if (tryParry && act != Act.Parry && toActive < 0.09f && toActive > -0.03f) Go(Act.Parry, 0.2f);
            }
            else judgedAttack = false;
            foreach (var p in projectiles)
            {
                if (p.Owner != op || (int)Mathf.Sign(me.X - p.X) != p.Dir) continue;
                if (judgedProjectile != p) { judgedProjectile = p; tryParry = Random.value < ParryChance * 0.8f; }
                if (tryParry && act != Act.Parry && Mathf.Abs(p.X - me.X) < 0.4f + p.Spec.Speed * 0.08f) Go(Act.Parry, 0.2f);
            }
            if (!tryParry && act != Act.Block && act != Act.Parry && act != Act.JumpIn &&
                IsThreatened(me, op, dist, projectiles) && Random.value < dt * 7)
            {
                if (Random.value < 0.75f) Go(Act.Block, 0.3f + Random.value * 0.2f);
                else { Go(Act.JumpIn, 0.6f); pressed.Add(FAction.Jump); }
            }

            if (t <= 0 && cooldown <= 0) Decide(me, dist, reach);

            if (t > 0)
            {
                switch (act)
                {
                    case Act.Approach: held.Add(toward); break;
                    case Act.Retreat: held.Add(away); break;
                    case Act.Block:
                    case Act.Parry: held.Add(FAction.Block); break;
                    case Act.JumpIn:
                        held.Add(toward);
                        if (me.State == FState.Jump && me.Y > 0.5f && me.VY < 1) pressed.Add(FAction.Light);
                        break;
                    case Act.HeavyIn:
                        held.Add(toward);
                        if (dist < reach * 0.9f) { pressed.Add(FAction.Heavy); act = Act.Idle; }
                        break;
                }
            }
            if (pressed.Contains(FAction.Jump)) held.Add(toward);
        }

        void Decide(Fighter me, float dist, float reach)
        {
            cooldown = 0.2f + Random.value * 0.4f;
            float r = Random.value;
            var special = me.Data.Move("Special");
            bool canSpecial = special != null && me.Meter >= special.Cost;

            if (dist > reach + 2.5f)
            {
                if (canSpecial && r < 0.35f) { pressed.Add(FAction.Special); Go(Act.Idle, 0.6f); }
                else if (r < 0.15f) { pressed.Add(FAction.Jump); Go(Act.JumpIn, 0.6f); }
                else Go(Act.Approach, 0.4f + Random.value * 0.5f);
            }
            else if (dist > reach * 0.85f)
            {
                if (r < 0.55f) Go(Act.Approach, 0.2f + Random.value * 0.3f);
                else if (r < 0.7f) Go(Act.HeavyIn, 0.4f);
                else if (r < 0.78f && canSpecial) { pressed.Add(FAction.Special); Go(Act.Idle, 0.6f); }
                else if (r < 0.88f) { pressed.Add(FAction.Jump); Go(Act.JumpIn, 0.6f); }
                else Go(Act.Idle, 0.3f);
            }
            else
            {
                if (r < 0.42f) { pressed.Add(FAction.Light); Go(Act.Idle, 0.25f); }
                else if (r < 0.62f) { pressed.Add(FAction.Heavy); Go(Act.Idle, 0.45f); }
                else if (r < 0.8f) Go(Act.Block, 0.4f);
                else Go(Act.Retreat, 0.35f);
            }
        }

        static bool IsThreatened(Fighter me, Fighter op, float dist, List<Projectile> projectiles)
        {
            if (op.State == FState.Attack && op.Move != null && op.Move.HasHitbox
                && dist < op.Data.Reach + 0.4f && op.T < op.Move.Startup + 0.02f) return true;
            foreach (var p in projectiles)
                if (p.Owner == op && Mathf.Abs(p.X - me.X) < 3.5f && (int)Mathf.Sign(me.X - p.X) == p.Dir) return true;
            return false;
        }

        void Go(Act a, float duration) { act = a; t = duration; }
    }
}
