using System.Collections.Generic;
using UnityEngine;

namespace FightingGame
{
    /// <summary>Simple CPU opponent: approaches, mixes punches/kicks/orbs, and reacts to incoming attacks.</summary>
    public sealed class AIController : IFighterInput
    {
        enum Act { Idle, Approach, Retreat, Block, JumpIn, KickIn }

        readonly HashSet<FAction> held = new HashSet<FAction>();
        readonly HashSet<FAction> pressed = new HashSet<FAction>();
        Act act;
        float t, cooldown = 0.6f;

        public bool Held(FAction a) => held.Contains(a);
        public bool Pressed(FAction a) => pressed.Contains(a);

        public void Think(float dt, Fighter me, Fighter op, List<Orb> orbs)
        {
            pressed.Clear();
            held.Clear();
            cooldown -= dt;
            t -= dt;

            float dx = op.X - me.X, dist = Mathf.Abs(dx);
            var toward = dx > 0 ? FAction.Right : FAction.Left;
            var away = dx > 0 ? FAction.Left : FAction.Right;

            if (act != Act.Block && act != Act.JumpIn && IsThreatened(me, op, dist, orbs) && Random.value < dt * 7)
            {
                if (Random.value < 0.75f) Go(Act.Block, 0.35f);
                else { Go(Act.JumpIn, 0.6f); pressed.Add(FAction.Jump); }
            }

            if (t <= 0 && cooldown <= 0) Decide(me, dist);

            if (t > 0)
            {
                switch (act)
                {
                    case Act.Approach: held.Add(toward); break;
                    case Act.Retreat: held.Add(away); break;
                    case Act.Block: held.Add(FAction.Block); break;
                    case Act.JumpIn:
                        held.Add(toward);
                        if (me.State == FState.Jump && me.Y > 0.5f && me.VY < 1) pressed.Add(FAction.Kick);
                        break;
                    case Act.KickIn:
                        held.Add(toward);
                        if (dist < 1.5f) { pressed.Add(FAction.Kick); act = Act.Idle; }
                        break;
                }
            }
            if (pressed.Contains(FAction.Jump)) held.Add(toward);
        }

        void Decide(Fighter me, float dist)
        {
            cooldown = 0.2f + Random.value * 0.4f;
            float r = Random.value;
            bool canOrb = me.Meter >= MoveData.Special.Cost;

            if (dist > 4.5f)
            {
                if (canOrb && r < 0.35f) { pressed.Add(FAction.Special); Go(Act.Idle, 0.5f); }
                else if (r < 0.2f) { pressed.Add(FAction.Jump); Go(Act.JumpIn, 0.6f); }
                else Go(Act.Approach, 0.4f + Random.value * 0.5f);
            }
            else if (dist > 1.5f)
            {
                if (r < 0.55f) Go(Act.Approach, 0.25f + Random.value * 0.3f);
                else if (r < 0.72f) Go(Act.KickIn, 0.35f);
                else if (r < 0.8f && canOrb) { pressed.Add(FAction.Special); Go(Act.Idle, 0.5f); }
                else if (r < 0.9f) { pressed.Add(FAction.Jump); Go(Act.JumpIn, 0.6f); }
                else Go(Act.Idle, 0.3f);
            }
            else
            {
                if (r < 0.38f) { pressed.Add(FAction.Punch); Go(Act.Idle, 0.22f); }
                else if (r < 0.62f) { pressed.Add(FAction.Kick); Go(Act.Idle, 0.35f); }
                else if (r < 0.8f) Go(Act.Block, 0.4f);
                else Go(Act.Retreat, 0.35f);
            }
        }

        static bool IsThreatened(Fighter me, Fighter op, float dist, List<Orb> orbs)
        {
            if (op.State == FState.Attack && op.Move != null && op.Move != MoveData.Special
                && dist < 2.2f && op.T < op.Move.Startup + 0.02f) return true;
            foreach (var o in orbs)
                if (o.Owner == op && Mathf.Abs(o.X - me.X) < 3.5f && (int)Mathf.Sign(me.X - o.X) == o.Dir) return true;
            return false;
        }

        void Go(Act a, float duration) { act = a; t = duration; }
    }
}
