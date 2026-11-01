using UnityEngine;

namespace FightingGame
{
    /// <summary>Art and animation for one playable character. Gameplay numbers come from Movesets.json.</summary>
    [CreateAssetMenu(menuName = "Fighting Game/Character")]
    public class CharacterDef : ScriptableObject
    {
        public string id;
        public GameObject prefab;
        public AnimationClip[] clips;
        public string weaponBone = "weapon";
        public string weaponTipBone = "weapon_tip";
        [Tooltip("Where the blade starts, in metres from the grip toward the tip (the hilt doesn't hit).")]
        public float bladeStart = 0.15f;
        [Tooltip("Radius of the blade's hitbox capsule. A little wider than the steel so hits feel fair.")]
        public float bladeRadius = 0.08f;
        public string[] capeBones;
        [ColorUsage(false, true)] public Color trailColor = Color.white;
        [ColorUsage(false, true)] public Color accent = Color.white;
        public GameObject projectilePrefab;
        [Tooltip("Embers drifting off the armour (Corvin).")]
        public bool emberAura;

        public AnimationClip Clip(string clipName)
        {
            foreach (var c in clips)
                if (c != null && c.name == clipName) return c;
            return null;
        }
    }
}
