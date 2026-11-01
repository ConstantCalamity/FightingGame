using UnityEngine;

namespace FightingGame
{
    /// <summary>A travelling attack (Corvin's ash wave, Isolde's throwing knife). Moved and collided by GameManager.</summary>
    public class Projectile
    {
        public GameObject Go;
        public Transform Spin;
        public Fighter Owner;
        public ProjectileSpec Spec;
        public int Dir;
        public float Life;
        public float TrailTimer;
        /// <summary>Host-assigned id so an online guest can match snapshots to the projectiles it already shows.</summary>
        public int NetId;

        public float X => Go.transform.position.x;
        public Vector2 Pos2D => Go.transform.position;
    }
}
