using System.Collections.Generic;
using UnityEngine;

namespace FightingGame
{
    public enum FState { Idle, Walk, Jump, Block, Attack, Hit, KO, Win }

    public enum HitOutcome { Hit, Blocked, Parried, Armored, GuardBreak }

    /// <summary>
    /// One fighter: state machine, simple 2.5D physics (x along the stage, y up) and hit detection.
    /// Numbers come from the character's <see cref="CharacterData"/>; visuals from its <see cref="ModelView"/>.
    /// Ticked by <see cref="GameManager"/> so both fighters update in a fixed order.
    /// </summary>
    public class Fighter : MonoBehaviour
    {
        public const float StageHalfWidth = 8.5f;
        const float Gravity = 24f;

        // Blocking: a fresh block parries anything that lands in its first few frames. A held block weakens
        // exponentially (more chip damage, pushback and guard loss) and bleeds guard; empty guard = guard break.
        public const float ParryWindow = 0.15f;      // ~9 frames at 60 fps from the moment block is pressed
        const float ParryCooldown = 0.35f;           // re-pressing block sooner than this doesn't re-arm the parry
        public const float GuardMax = 100f;
        const float GuardDecayTau = 2.0f;            // seconds for a held block to lose ~63% of its effectiveness
        const float GuardRegen = 28f, GuardRegenDelay = 0.8f;

        [Header("Runtime state (read-only)")]
        public float X, Y, VX, VY;
        public int Facing = 1;
        public float HP, LagHP, Meter;
        public FState State;
        public float T, AirTime;
        public int Combo;
        public float ComboT;
        public float Guard = GuardMax;
        public bool GuardBroken;
        /// <summary>0 for a fresh block, approaching 1 the longer it's held.</summary>
        public float BlockWear => State == FState.Block ? 1f - Mathf.Exp(-T / GuardDecayTau) : 0f;
        public bool ParryReady => State == FState.Block && parryArmed && T <= ParryWindow;
        public float MeterFlash { get; private set; }

        public CharacterData Data { get; private set; }
        public CharacterDef Def { get; private set; }
        public ModelView View { get; private set; }
        public MoveData Move { get; private set; }
        public float Stun { get; private set; }
        public float Flash { get; private set; }
        public bool Grounded => Y <= 0.0001f;
        public string DisplayName => Data.DisplayName;
        public Color Accent => Def.accent;

        GameManager game;
        bool hitDone, fired, dived, airAttackUsed;
        bool parryArmed;
        float sinceBlock = 99f, guardDelay;

        static readonly List<Rect> scratch = new List<Rect>();
        float bodyHips, bodyTorso, bodyHead;

        public static Fighter Create(GameManager game, CharacterDef def, CharacterData data, Material trailTemplate, string label)
        {
            var go = new GameObject(label);
            var f = go.AddComponent<Fighter>();
            f.game = game; f.Def = def; f.Data = data;
            f.View = ModelView.Create(def, go.transform, trailTemplate);
            return f;
        }

        public void ResetFor(float x, int facing)
        {
            X = x; Y = 0; VX = VY = 0; Facing = facing;
            HP = LagHP = Data.Hp; Meter = 0;
            State = FState.Idle; T = 0; AirTime = 0; Move = null;
            hitDone = fired = dived = airAttackUsed = false; Stun = Flash = 0; Combo = 0; ComboT = 0;
            Guard = GuardMax; GuardBroken = false; parryArmed = false; sinceBlock = 99f; guardDelay = 0; MeterFlash = 0;
        }

        void AddMeter(float amount)
        {
            Meter = Mathf.Min(100, Meter + amount);
        }

        // ---------- Online (the host simulates; the guest only displays snapshots) ----------

        public FighterSnapshot CaptureNetwork() => new FighterSnapshot
        {
            x = X, y = Y, vx = VX, vy = VY, hp = HP, lag = LagHP, meter = Meter, guard = Guard, t = T, comboT = ComboT,
            flash = Flash, stun = Stun, meterFlash = MeterFlash, facing = Facing, state = (int)State, combo = Combo,
            move = Move != null ? Move.Id : "", guardBroken = GuardBroken,
        };

        public void ApplyNetwork(FighterSnapshot s)
        {
            X = s.x; Y = s.y; VX = s.vx; VY = s.vy; HP = s.hp; LagHP = s.lag; Meter = s.meter; Guard = s.guard; T = s.t;
            ComboT = s.comboT; Flash = s.flash; Stun = s.stun; MeterFlash = s.meterFlash; Facing = s.facing;
            State = (FState)s.state; Combo = s.combo; GuardBroken = s.guardBroken;
            Move = string.IsNullOrEmpty(s.move) ? null : Data.Move(s.move);
            if (State == FState.Attack && Move == null) State = FState.Idle;
        }

        /// <summary>Guest side: carry the last snapshot forward so animation and movement stay smooth between updates.</summary>
        public void Extrapolate(float dt)
        {
            T += dt;
            X = Mathf.Clamp(X + VX * dt, -StageHalfWidth, StageHalfWidth);
            if (!Grounded) { VY -= Gravity * dt; Y = Mathf.Max(0, Y + VY * dt); }
            Flash = Mathf.Max(0, Flash - dt);
            MeterFlash = Mathf.Max(0, MeterFlash - dt);
        }

        void SetState(FState s) { State = s; T = 0; }

        bool StartMove(string id)
        {
            var m = Data.Move(id);
            if (m == null) return false;
            Move = m; hitDone = false; fired = false; dived = false;
            SetState(FState.Attack);
            if (Grounded) VX = 0;
            return true;
        }

        /// <summary>Debug/test hook: start a move immediately, ignoring input and meter.</summary>
        public bool ForceMove(string id) => State != FState.KO && StartMove(id);

        public void Celebrate()
        {
            if (State == FState.KO) return;
            Move = null;
            SetState(FState.Win);
        }

        public void Tick(float dt, IFighterInput inp, Fighter op)
        {
            bool wasBlocking = State == FState.Block;
            T += dt;
            if (!Grounded) AirTime += dt;
            switch (State)
            {
                case FState.KO:
                case FState.Win:
                    if (Grounded) VX *= Mathf.Pow(0.03f, dt);
                    break;
                case FState.Hit:
                    if (Grounded) VX *= Mathf.Pow(0.02f, dt);
                    if (T > Stun && Grounded)
                    {
                        SetState(FState.Idle);
                        if (GuardBroken) { GuardBroken = false; Guard = GuardMax * 0.4f; }
                    }
                    break;
                case FState.Attack:
                    TickAttack(dt, op);
                    break;
                default:
                    if (Grounded) Neutral(inp, op);
                    else if (!airAttackUsed && (inp.Pressed(FAction.Light) || inp.Pressed(FAction.Heavy)) && StartMove("Air"))
                        airAttackUsed = true;
                    break;
            }

            VY -= Gravity * dt;
            Y += VY * dt;
            if (Y <= 0)
            {
                Y = 0; VY = 0; AirTime = 0; airAttackUsed = false;
                if (State == FState.Jump) SetState(FState.Idle);
            }
            X = Mathf.Clamp(X + VX * dt, -StageHalfWidth, StageHalfWidth);

            if (wasBlocking && State != FState.Block) sinceBlock = 0;
            // guard: a held block bleeds guard faster the longer it's held; otherwise it regenerates after a delay
            if (State == FState.Block)
            {
                Guard -= dt * (3f + 10f * BlockWear);
                guardDelay = GuardRegenDelay;
                if (Guard <= 0) BreakGuard(-Facing, new Vector3(X, Y + 1.3f, 0));
            }
            else
            {
                sinceBlock += dt;
                if (guardDelay > 0) guardDelay -= dt;
                else if (!GuardBroken) Guard = Mathf.Min(GuardMax, Guard + GuardRegen * dt);
            }

            Flash = Mathf.Max(0, Flash - dt);
            MeterFlash = Mathf.Max(0, MeterFlash - dt);
            if (LagHP < HP) LagHP = HP;
            else if (State != FState.Hit) LagHP += (HP - LagHP) * (1 - Mathf.Pow(0.08f, dt));
            Meter = Mathf.Min(100, Meter + dt * 2);
            if (ComboT > 0) ComboT -= dt;
        }

        void TickAttack(float dt, Fighter op)
        {
            var m = Move;
            bool inActive = T >= m.Startup && T < m.Startup + m.Active;
            if (m.LungeSpeed > 0 && inActive) VX = Facing * m.LungeSpeed;
            else if (Grounded) VX *= Mathf.Pow(0.01f, dt);
            if (m.DiveSpeed > 0 && !dived && T >= m.Startup) { dived = true; VY = -m.DiveSpeed; VX *= 0.5f; }
            if (m.Projectile != null && !fired && T >= m.Startup) { fired = true; game.FireProjectile(this, m.Projectile); }
            // melee hits are resolved in ResolveHits, after the animation has been sampled for this frame

            bool landedFromAir = m.Id == "Air" && Grounded && T > m.Startup;
            if (T >= m.Total || landedFromAir)
            {
                Move = null;
                SetState(Grounded ? FState.Idle : FState.Jump);
            }
        }

        void Neutral(IFighterInput inp, Fighter op)
        {
            Facing = op.X > X ? 1 : -1;
            int dir = (inp.Held(FAction.Right) ? 1 : 0) - (inp.Held(FAction.Left) ? 1 : 0);
            var special = Data.Move("Special");

            if (inp.Pressed(FAction.Special) && special != null && Meter >= special.Cost)
            {
                Meter -= special.Cost;
                StartMove("Special");
            }
            else if (inp.Pressed(FAction.Light) && StartMove("Light")) { }
            else if (inp.Pressed(FAction.Heavy) && StartMove("Heavy")) { }
            else if (inp.Pressed(FAction.Jump))
            {
                VY = Data.JumpSpeed; VX = dir * (Data.WalkSpeed + 0.6f);
                SetState(FState.Jump);
            }
            else if (inp.Held(FAction.Block))
            {
                if (State != FState.Block)
                {
                    SetState(FState.Block);
                    parryArmed = sinceBlock >= ParryCooldown;   // mashing block doesn't keep the parry window open
                }
                VX = 0;
            }
            else
            {
                VX = dir * (dir != 0 && dir != Facing ? Data.BackSpeed : Data.WalkSpeed);
                var s = dir != 0 ? FState.Walk : FState.Idle;
                if (State != s) SetState(s);
            }
        }

        /// <summary>Knocked off balance (parried, or guard broken): stunned and open.</summary>
        void Stagger(float stun, int pushDir, float push)
        {
            Move = null;
            SetState(FState.Hit);
            Stun = stun;
            VX = pushDir * push;
            Flash = 0.12f;
        }

        void BreakGuard(int pushDir, Vector3 pos)
        {
            Guard = 0;
            GuardBroken = true;
            Stagger(1.0f, pushDir, 3.0f);
            game.OnGuardBreak(this, pos);
        }

        // ---------- Hitboxes / hurtboxes (2D, in the stage plane) ----------

        /// <summary>
        /// The current attack's hitbox: the actual blade (hilt to tip, from the animated weapon bones) as a capsule
        /// in the stage plane. Falls back to the authored capsule in Movesets.json if the model has no weapon bones.
        /// active is false during startup/recovery — timing still comes from the move data.
        /// </summary>
        public bool GetHitbox(out Vector2 a, out Vector2 b, out float radius, out bool active)
        {
            a = b = default; radius = 0; active = false;
            if (State != FState.Attack || Move == null || !Move.HasHitbox) return false;
            active = T >= Move.Startup && T < Move.Startup + Move.Active;
            if (View != null && View.GetFlailOrBlade(Def.dualFlails && Move.Id == "Heavy", out a, out b, out _))
            {
                radius = Def.bladeRadius;
                return true;
            }
            a = new Vector2(X + Facing * Move.HitP0.x, Y + Move.HitP0.y);
            b = new Vector2(X + Facing * Move.HitP1.x, Y + Move.HitP1.y);
            radius = Move.HitRadius;
            return true;
        }

        /// <summary>Test the blade (and the arc its tip swept since last frame) against the opponent.</summary>
        public void ResolveHits(Fighter op)
        {
            if (State == FState.Attack && Move != null && Move.HasHitbox && !hitDone &&
                GetHitbox(out var a, out var b, out var r, out var active) && active && op.State != FState.KO)
            {
                bool hit = op.Overlaps(a, b, r, out var contact);
                if (!hit && Def.dualFlails && Move.Id == "Special" && View.GetFlailOrBlade(true, out var la, out var lb, out _))
                    hit = op.Overlaps(la, lb, r, out contact);
                if (!hit && !Def.dualFlails && View != null && View.GetBlade(out _, out var tip, out var prevTip))
                    hit = op.Overlaps(prevTip, tip, r, out contact);   // fast swings: the tip's path between frames
                if (hit)
                {
                    hitDone = true;
                    op.TakeHit(this, Move, new Vector3(contact.x, contact.y, 0), Facing);
                }
            }
            View?.StoreBladeSample();
        }

        public void GetHurtboxes(List<Rect> list)
        {
            list.Clear();
            if (State == FState.KO) return;
            float dip = State == FState.Block ? 0.12f : 0;
            bool posed = View != null && View.GetBodyX(out bodyHips, out bodyTorso, out bodyHead);
            foreach (var (name, r) in Data.Hurtboxes)
            {
                float cx = X + Facing * r.center.x, cy = Y + r.center.y - dip;
                if (posed)
                {
                    // centre on the animated body part, but never let a wild pose drag the box far from the root
                    float bx = name == "head" ? bodyHead : name == "legs" ? bodyHips : bodyTorso;
                    cx = Mathf.Clamp(bx, X - 0.5f, X + 0.5f) + Facing * r.center.x;
                }
                float h = r.height;
                if (name == "legs" && !Grounded) { h *= 0.6f; cy = Y + r.yMax - h / 2 - 0.05f; }
                list.Add(new Rect(cx - r.width / 2, cy - h / 2, r.width, h));
            }
        }

        public float PushboxWidth => Data.PushboxWidth;

        /// <summary>Does a capsule (segment a-b with radius r) touch any hurtbox?</summary>
        public bool Overlaps(Vector2 a, Vector2 b, float r, out Vector2 contact)
        {
            GetHurtboxes(scratch);
            contact = default;
            float best = float.MaxValue;
            foreach (var box in scratch)
            {
                float d = SegmentRectDistance(a, b, box, out var c);
                if (d <= r && d < best) { best = d; contact = c; }
            }
            return best < float.MaxValue;
        }

        static float SegmentRectDistance(Vector2 a, Vector2 b, Rect r, out Vector2 contact)
        {
            // min over: segment endpoints to rect, rect corners to segment, and points of the segment inside the rect
            float best = float.MaxValue;
            Vector2 bestPoint = a;
            foreach (var p in new[] { a, b })
            {
                var q = new Vector2(Mathf.Clamp(p.x, r.xMin, r.xMax), Mathf.Clamp(p.y, r.yMin, r.yMax));
                float d = Vector2.Distance(p, q);
                if (d < best) { best = d; bestPoint = p; }
            }
            Vector2 ab = b - a;
            float len2 = Mathf.Max(ab.sqrMagnitude, 1e-8f);
            foreach (var corner in new[] { new Vector2(r.xMin, r.yMin), new Vector2(r.xMax, r.yMin), new Vector2(r.xMin, r.yMax), new Vector2(r.xMax, r.yMax) })
            {
                float t = Mathf.Clamp01(Vector2.Dot(corner - a, ab) / len2);
                Vector2 p = a + ab * t;
                float d = r.Contains(p) ? 0 : Vector2.Distance(p, corner);
                if (d < best) { best = d; bestPoint = p; }
            }
            for (int i = 0; i <= 8; i++)
            {
                Vector2 p = a + ab * (i / 8f);
                if (r.Contains(p)) { best = 0; bestPoint = p; break; }
            }
            contact = bestPoint;
            return best;
        }

        public HitOutcome TakeHit(Fighter att, MoveData m, Vector3 pos, int dir, bool projectile = false)
        {
            bool armored = State == FState.Attack && Move != null && Move.Armor && T < Move.Startup + Move.Active;
            var outcome = HitOutcome.Hit;
            if (State == FState.Block && Grounded && ParryReady)
            {
                // PARRY: no damage, big meter and guard refund; a nearby attacker is knocked off balance
                parryArmed = false;
                AddMeter(25);
                MeterFlash = 0.6f;
                Guard = Mathf.Min(GuardMax, Guard + 35);
                att.Combo = 0;
                if (!projectile || Mathf.Abs(att.X - X) < 2.6f)
                    att.Stagger(0.62f, Facing, 2.8f);
                game.OnParry(this, att, pos);
                return HitOutcome.Parried;
            }
            if (State == FState.Block && Grounded)
            {
                // a held block gets steadily worse: more chip, more pushback, more guard damage
                float wear = BlockWear;
                HP -= m.Damage * (0.08f + 0.42f * wear);
                VX = dir * m.Push * (0.6f + 0.7f * wear);
                Guard -= m.Damage * (2.2f + 3.8f * wear);
                guardDelay = GuardRegenDelay;
                AddMeter(4);
                att.AddMeter(3);
                att.Combo = 0;
                if (Guard <= 0)
                {
                    BreakGuard(dir, pos);
                    outcome = HitOutcome.GuardBreak;
                }
                else
                {
                    game.OnBlock(pos, wear);
                    outcome = HitOutcome.Blocked;
                }
            }
            else if (armored)
            {
                HP -= m.Damage * 0.8f;   // absorbs the hit without flinching
                Flash = 0.12f;
                att.Meter = Mathf.Min(100, att.Meter + m.MeterGain * 0.5f);
                game.OnArmor(this, pos);
                outcome = HitOutcome.Armored;
            }
            else
            {
                HP -= m.Damage;
                Move = null;
                SetState(FState.Hit);
                Stun = m.Hitstun;
                VX = dir * m.Push;
                if (!Grounded) VY = Mathf.Max(VY, 4);
                Flash = 0.1f;
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
            return outcome;
        }

        public void UpdateVisual(float dt, float realDt)
        {
            transform.position = new Vector3(X, Y, 0);
            View.Sync(this, dt, realDt);
        }
    }
}
