using System;
using System.Collections.Generic;
using UnityEngine;

namespace FightingGame
{
    /// <summary>Timing, damage and hitbox for one attack, loaded from Data/Movesets.json. Times are in seconds.</summary>
    public class MoveData
    {
        public string Id, Name;
        public float Startup, Active, Recovery;
        public float Damage, Hitstun, Push, MeterGain;
        public int Cost;
        public bool Armor;
        public float LungeSpeed, DiveSpeed;

        /// <summary>Capsule hitbox relative to the fighter's feet; x is multiplied by facing.</summary>
        public Vector2 HitP0, HitP1;
        public float HitRadius;

        public ProjectileSpec Projectile;

        public float Total => Startup + Active + Recovery;
        public bool HasHitbox => HitRadius > 0;
    }

    public class ProjectileSpec
    {
        public string Style;
        public float Speed, Height, Radius, SpawnX, Life;
        public MoveData Hit;     // damage profile applied on contact
    }

    /// <summary>Everything gameplay needs to know about one character.</summary>
    public class CharacterData
    {
        public string Id, DisplayName, Title;
        public float Hp, WalkSpeed, BackSpeed, JumpSpeed, PushboxWidth;
        public List<(string name, Rect box)> Hurtboxes = new List<(string, Rect)>();
        public Dictionary<string, MoveData> Moves = new Dictionary<string, MoveData>();

        public MoveData Move(string id) => Moves.TryGetValue(id, out var m) ? m : null;

        /// <summary>Longest forward reach of the grounded attacks, used by the CPU to judge distance.</summary>
        public float Reach
        {
            get
            {
                float r = 1f;
                foreach (var m in Moves.Values)
                    if (m.HasHitbox && m.Id != "Air") r = Mathf.Max(r, Mathf.Max(m.HitP0.x, m.HitP1.x) + m.HitRadius);
                return r;
            }
        }
    }

    /// <summary>Parses Movesets.json (shared with the Blender animation scripts).</summary>
    public static class MovesetLoader
    {
#pragma warning disable 0649
        [Serializable] class Root { public int fps; public Char[] characters; }
        [Serializable] class Char
        {
            public string id, displayName, title;
            public float hp, walkSpeed, backSpeed, jumpSpeed, pushboxWidth;
            public Box[] hurtboxes;
            public Move[] moves;
        }
        [Serializable] class Box { public string name; public float[] center, size; }
        [Serializable] class Move
        {
            public string id, name;
            public int startupF, activeF, recoveryF, cost;
            public float damage, hitstun, push, meterGain, lungeSpeed, diveSpeed;
            public bool armor;
            public Hitbox hitbox;
            public Proj projectile;
        }
        [Serializable] class Hitbox { public float[] p0, p1; public float radius; }
        [Serializable] class Proj
        {
            public string style;
            public float speed, height, radius, spawnX, damage, hitstun, push, life;
        }
#pragma warning restore 0649

        public static Dictionary<string, CharacterData> Load(string json)
        {
            var root = JsonUtility.FromJson<Root>(json);
            float fps = root.fps > 0 ? root.fps : 30f;
            var result = new Dictionary<string, CharacterData>();
            foreach (var c in root.characters)
            {
                var d = new CharacterData
                {
                    Id = c.id, DisplayName = c.displayName, Title = c.title, Hp = c.hp,
                    WalkSpeed = c.walkSpeed, BackSpeed = c.backSpeed, JumpSpeed = c.jumpSpeed,
                    PushboxWidth = c.pushboxWidth > 0 ? c.pushboxWidth : 0.75f,
                };
                foreach (var b in c.hurtboxes)
                    d.Hurtboxes.Add((b.name, new Rect(b.center[0] - b.size[0] / 2, b.center[1] - b.size[1] / 2, b.size[0], b.size[1])));
                foreach (var m in c.moves)
                {
                    var md = new MoveData
                    {
                        Id = m.id, Name = m.name,
                        Startup = m.startupF / fps, Active = m.activeF / fps, Recovery = m.recoveryF / fps,
                        Damage = m.damage, Hitstun = m.hitstun, Push = m.push, MeterGain = m.meterGain,
                        Cost = m.cost, Armor = m.armor, LungeSpeed = m.lungeSpeed, DiveSpeed = m.diveSpeed,
                    };
                    if (m.hitbox != null && m.hitbox.p0 != null && m.hitbox.p0.Length == 2)
                    {
                        md.HitP0 = new Vector2(m.hitbox.p0[0], m.hitbox.p0[1]);
                        md.HitP1 = new Vector2(m.hitbox.p1[0], m.hitbox.p1[1]);
                        md.HitRadius = m.hitbox.radius;
                    }
                    if (m.projectile != null && !string.IsNullOrEmpty(m.projectile.style))
                    {
                        var p = m.projectile;
                        md.Projectile = new ProjectileSpec
                        {
                            Style = p.style, Speed = p.speed, Height = p.height, Radius = p.radius, SpawnX = p.spawnX, Life = p.life,
                            Hit = new MoveData { Id = "Projectile", Name = m.name, Damage = p.damage, Hitstun = p.hitstun, Push = p.push },
                        };
                    }
                    d.Moves[m.id] = md;
                }
                result[d.Id] = d;
            }
            return result;
        }
    }
}
