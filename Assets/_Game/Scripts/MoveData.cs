using UnityEngine;

namespace FightingGame
{
    /// <summary>Timing, damage and hitbox for one attack. Times are in seconds.</summary>
    public class MoveData
    {
        public string Name;
        public float Startup, Active, Recovery;
        public float Damage, Hitstun, Push, MeterGain;
        public int Cost;

        /// <summary>Hitbox centre relative to the fighter's feet; x is multiplied by facing.</summary>
        public Vector2 HitboxOffset;
        public float HitboxRadius;

        public float Total => Startup + Active + Recovery;

        public static readonly MoveData Punch = new MoveData
        {
            Name = "Punch", Startup = 0.07f, Active = 0.08f, Recovery = 0.16f,
            Damage = 5, Hitstun = 0.28f, Push = 2.6f, MeterGain = 7,
            HitboxOffset = new Vector2(0.85f, 1.6f), HitboxRadius = 0.25f,
        };

        public static readonly MoveData Kick = new MoveData
        {
            Name = "Kick", Startup = 0.16f, Active = 0.10f, Recovery = 0.28f,
            Damage = 9, Hitstun = 0.38f, Push = 5f, MeterGain = 10,
            HitboxOffset = new Vector2(1.15f, 1.1f), HitboxRadius = 0.3f,
        };

        public static readonly MoveData AirKick = new MoveData
        {
            Name = "Air Kick", Startup = 0.10f, Active = 0.14f, Recovery = 0.20f,
            Damage = 8, Hitstun = 0.35f, Push = 4f, MeterGain = 9,
            HitboxOffset = new Vector2(0.85f, 0.55f), HitboxRadius = 0.35f,
        };

        public static readonly MoveData Special = new MoveData
        {
            Name = "Energy Orb", Startup = 0.26f, Active = 0.05f, Recovery = 0.34f, Cost = 50,
        };

        /// <summary>Damage profile of the projectile fired by <see cref="Special"/>.</summary>
        public static readonly MoveData Orb = new MoveData
        {
            Name = "Orb", Damage = 12, Hitstun = 0.45f, Push = 4.5f, HitboxRadius = 0.3f,
        };
    }
}
