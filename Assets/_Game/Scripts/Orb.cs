using UnityEngine;

namespace FightingGame
{
    /// <summary>Energy-orb projectile. Moved and collided by <see cref="GameManager"/>.</summary>
    public class Orb
    {
        public const float Speed = 9f;

        public GameObject Go;
        public Transform Halo;
        public Fighter Owner;
        public int Dir;
        public float Life = 2.5f, TrailTimer;

        public float X => Go.transform.position.x;
        public Vector2 Pos2D => Go.transform.position;
    }
}
