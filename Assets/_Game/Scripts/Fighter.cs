using System.Collections.Generic;
using UnityEngine;

namespace FightingGame
{
    public enum FState { Idle, Walk, Jump, Block, Attack, Hit, KO, Win }

    /// <summary>
    /// One fighter: state machine, simple 2.5D physics (x along the stage, y up) and hit detection.
    /// Ticked by <see cref="GameManager"/> so both fighters update in a fixed order.
    /// </summary>
    public class Fighter : MonoBehaviour
    {
        public const float StageHalfWidth = 8.5f;
        const float Gravity = 24f, JumpSpeed = 8.5f, WalkSpeed = 3.4f, BackSpeed = 2.4f;

        [Header("Runtime state (read-only)")]
        public string DisplayName;
        public Color Accent;
        public float X, Y, VX, VY;
        public int Facing = 1;
        public float HP = 100, LagHP = 100, Meter;
        public FState State;
        public float T;
        public int Combo;
        public float ComboT;

        public MoveData Move { get; private set; }
        public bool Grounded => Y <= 0.0001f;

        FighterRig rig;
        GameManager game;
        bool hitDone, fired;
        float stun, flash, idleSeed;

        static readonly List<Rect> scratch = new List<Rect>();

        public static Fighter Create(GameManager game, string name, Color color, Color accent, Material lit, float idleSeed)
        {
            var rig = FighterRig.Build(name, color, accent, lit);
            var f = rig.Root.gameObject.AddComponent<Fighter>();
            f.rig = rig; f.game = game; f.DisplayName = name; f.Accent = accent; f.idleSeed = idleSeed;
            return f;
        }

        public void ResetFor(float x, int facing)
        {
            X = x; Y = 0; VX = VY = 0; Facing = facing;
            HP = LagHP = 100; Meter = 0;
            State = FState.Idle; T = 0; Move = null;
            hitDone = fired = false; stun = flash = 0; Combo = 0; ComboT = 0;
            rig.ResetPose(facing);
        }

        void SetState(FState s) { State = s; T = 0; }

        void StartMove(MoveData m)
        {
            Move = m; hitDone = false; fired = false;
            SetState(FState.Attack);
            if (Grounded) VX = m == MoveData.Kick ? Facing * 1.8f : 0;
        }

        public void Celebrate()
        {
            if (State == FState.KO) return;
            Move = null;
            SetState(FState.Win);
        }

        public void Tick(float dt, IFighterInput inp, Fighter op)
        {
            T += dt;
            switch (State)
            {
                case FState.KO:
                case FState.Win:
                    if (Grounded) VX *= Mathf.Pow(0.03f, dt);
                    break;
                case FState.Hit:
                    if (Grounded) VX *= Mathf.Pow(0.02f, dt);
                    if (T > stun && Grounded) SetState(FState.Idle);
                    break;
                case FState.Attack:
                    if (Grounded) VX *= Mathf.Pow(0.01f, dt);
                    if (Move == MoveData.Special && !fired && T >= Move.Startup) { fired = true; game.FireOrb(this); }
                    if (!hitDone && T >= Move.Startup && T < Move.Startup + Move.Active) TryHit(op);
                    if (T >= Move.Total) { Move = null; SetState(Grounded ? FState.Idle : FState.Jump); }
                    break;
                default:
                    if (Grounded) Neutral(inp, op);
                    else if (inp.Pressed(FAction.Kick)) StartMove(MoveData.AirKick);
                    else if (inp.Pressed(FAction.Punch)) StartMove(MoveData.Punch);
                    break;
            }

            VY -= Gravity * dt;
            Y += VY * dt;
            if (Y <= 0)
            {
                Y = 0; VY = 0;
                if (State == FState.Jump) SetState(FState.Idle);
            }
            X = Mathf.Clamp(X + VX * dt, -StageHalfWidth, StageHalfWidth);

            flash = Mathf.Max(0, flash - dt);
            if (LagHP < HP) LagHP = HP;
            else if (State != FState.Hit) LagHP += (HP - LagHP) * (1 - Mathf.Pow(0.08f, dt));
            Meter = Mathf.Min(100, Meter + dt * 2);
            if (ComboT > 0) ComboT -= dt;
        }

        void Neutral(IFighterInput inp, Fighter op)
        {
            Facing = op.X > X ? 1 : -1;
            int dir = (inp.Held(FAction.Right) ? 1 : 0) - (inp.Held(FAction.Left) ? 1 : 0);

            if (inp.Pressed(FAction.Special) && Meter >= MoveData.Special.Cost)
            {
                Meter -= MoveData.Special.Cost;
                StartMove(MoveData.Special);
            }
            else if (inp.Pressed(FAction.Punch)) StartMove(MoveData.Punch);
            else if (inp.Pressed(FAction.Kick)) StartMove(MoveData.Kick);
            else if (inp.Pressed(FAction.Jump))
            {
                VY = JumpSpeed; VX = dir * 3.8f;
                SetState(FState.Jump);
            }
            else if (inp.Held(FAction.Block))
            {
                if (State != FState.Block) SetState(FState.Block);
                VX = 0;
            }
            else
            {
                VX = dir * (dir != 0 && dir != Facing ? BackSpeed : WalkSpeed);
                var s = dir != 0 ? FState.Walk : FState.Idle;
                if (State != s) SetState(s);
            }
        }

        // ---------- Hitboxes / hurtboxes (2D, in the stage plane) ----------

        /// <summary>The current attack's hitbox. <paramref name="active"/> is false during startup/recovery.</summary>
        public bool GetHitbox(out Vector2 centre, out float radius, out bool active)
        {
            centre = default; radius = 0; active = false;
            if (State != FState.Attack || Move == null || Move.HitboxRadius <= 0) return false;
            centre = new Vector2(X + Facing * Move.HitboxOffset.x, Y + Move.HitboxOffset.y);
            radius = Move.HitboxRadius;
            active = T >= Move.Startup && T < Move.Startup + Move.Active;
            return true;
        }

        public void GetHurtboxes(List<Rect> list)
        {
            list.Clear();
            if (State == FState.KO) return;
            float dip = State == FState.Block ? 0.15f : 0;
            list.Add(Box(X + Facing * 0.03f, Y + 2.05f - dip, 0.46f, 0.46f));   // head
            list.Add(Box(X, Y + 1.5f - dip, 0.66f, 0.72f));                   // torso
            if (Grounded) list.Add(Box(X, Y + 0.55f - dip / 2, 0.55f, 1.1f - dip)); // legs
            else list.Add(Box(X, Y + 0.8f, 0.6f, 0.6f));                      // tucked legs
        }

        /// <summary>Width of the body used to stop fighters walking through each other.</summary>
        public const float PushboxWidth = 0.75f;

        public bool Overlaps(Vector2 c, float r)
        {
            GetHurtboxes(scratch);
            foreach (var b in scratch)
            {
                var p = new Vector2(Mathf.Clamp(c.x, b.xMin, b.xMax), Mathf.Clamp(c.y, b.yMin, b.yMax));
                if ((p - c).sqrMagnitude <= r * r) return true;
            }
            return false;
        }

        static Rect Box(float cx, float cy, float w, float h) => new Rect(cx - w / 2, cy - h / 2, w, h);

        void TryHit(Fighter op)
        {
            if (!GetHitbox(out var c, out var r, out _)) return;
            if (op.State == FState.KO || !op.Overlaps(c, r)) return;
            hitDone = true;
            op.TakeHit(this, Move, new Vector3(c.x, c.y, 0), Facing);
        }

        public void TakeHit(Fighter att, MoveData m, Vector3 pos, int dir)
        {
            if (State == FState.Block && Grounded)
            {
                HP -= m.Damage * 0.12f;
                VX = dir * m.Push * 0.7f;
                Meter = Mathf.Min(100, Meter + 5);
                att.Meter = Mathf.Min(100, att.Meter + 3);
                att.Combo = 0;
                game.OnBlock(pos);
            }
            else
            {
                HP -= m.Damage;
                Move = null;
                SetState(FState.Hit);
                stun = m.Hitstun;
                VX = dir * m.Push;
                if (!Grounded) VY = Mathf.Max(VY, 4);
                flash = 0.1f;
                Meter = Mathf.Min(100, Meter + 4);
                att.Meter = Mathf.Min(100, att.Meter + m.MeterGain);
                att.Combo = (att.ComboT > 0 ? att.Combo : 0) + 1;
                att.ComboT = 0.9f;
                game.OnHit(this, att, m, pos);
            }

            if (HP <= 0)
            {
                HP = 0; Move = null;
                SetState(FState.KO);
                VX = dir * 6; VY = 6;
                game.OnKO(this);
            }
        }

        // ---------- Procedural animation ----------

        public void UpdateVisual(float dt, float clock)
        {
            bool snappy = State == FState.Attack || State == FState.Hit;
            float k = 1 - Mathf.Pow(snappy ? 1e-14f : 1e-5f, dt);
            rig.Apply(TargetPose(clock), k, dt, X, Y, Facing, State == FState.KO, flash > 0);
        }

        Pose TargetPose(float clock)
        {
            var p = Pose.Base;
            p.Dip += Mathf.Sin(clock * 4 + idleSeed) * 0.025f;
            switch (State)
            {
                case FState.Walk:
                {
                    float s = Mathf.Sin(clock * 11);
                    p.HpA += s * 0.55f; p.HpB -= s * 0.55f;
                    p.KnA += Mathf.Max(0, -s) * 0.7f; p.KnB += Mathf.Max(0, s) * 0.7f;
                    break;
                }
                case FState.Block:
                    p.ShA = p.ShB = -1.35f; p.ElA = p.ElB = -2.3f;
                    p.Dip = -0.2f; p.KnA = p.KnB = 0.75f; p.HpA = -0.1f; p.HpB = -0.5f; p.Lean = 0.2f; p.Twist = 0;
                    break;
                case FState.Jump:
                    p.HpA = -1.1f; p.KnA = 1.7f; p.HpB = -0.5f; p.KnB = 1.2f;
                    break;
                case FState.Hit:
                    p.Lean = -0.5f; p.ShA = -0.3f; p.ElA = -0.6f; p.ShB = -0.2f; p.ElB = -0.5f; p.Twist = -0.2f; p.Dip = -0.12f;
                    break;
                case FState.KO:
                    p.ShA = -2.6f; p.ElA = -0.2f; p.ShB = -2.4f; p.ElB = -0.4f;
                    p.HpA = -0.2f; p.KnA = 0.3f; p.HpB = 0.1f; p.KnB = 0.2f; p.Lean = 0; p.Twist = 0; p.Dip = 0;
                    break;
                case FState.Win:
                    p.ShA = -3.0f; p.ElA = -0.4f; p.ShB = -0.9f; p.ElB = -1.7f; p.Twist = 0; p.Lean = -0.1f;
                    break;
                case FState.Attack:
                    AttackPose(ref p);
                    break;
            }
            return p;
        }

        void AttackPose(ref Pose p)
        {
            var m = Move;
            bool ext = T >= m.Startup && T < m.Startup + m.Active + m.Recovery * 0.5f;
            if (m == MoveData.Punch)
            {
                if (ext) { p.ShA = -1.6f; p.ElA = -0.05f; p.Twist = 0.8f; p.Lean = 0.15f; }
                else { p.ShA = -0.7f; p.ElA = -2.1f; p.Twist = 0.05f; }
            }
            else if (m == MoveData.Kick)
            {
                if (ext) { p.HpA = -1.65f; p.KnA = 0.05f; p.Lean = -0.35f; p.Twist = -0.3f; p.HpB = 0.15f; p.KnB = 0.25f; }
                else { p.HpA = -0.9f; p.KnA = 1.7f; p.Lean = -0.1f; }
            }
            else if (m == MoveData.AirKick)
            {
                if (ext) { p.HpA = -1.2f; p.KnA = 0; p.HpB = -0.9f; p.KnB = 1.6f; p.Lean = -0.3f; }
                else { p.HpA = -1.1f; p.KnA = 1.7f; p.HpB = -0.5f; p.KnB = 1.2f; }
            }
            else if (m == MoveData.Special)
            {
                if (ext) { p.ShA = p.ShB = -1.55f; p.ElA = p.ElB = 0; p.Twist = 0; p.Lean = 0.2f; p.Dip = -0.12f; }
                else { p.ShA = p.ShB = 0.5f; p.ElA = p.ElB = -1.4f; p.Twist = -0.7f; p.Dip = -0.15f; p.Lean = -0.1f; }
            }
        }
    }
}
