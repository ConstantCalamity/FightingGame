using UnityEngine;

namespace FightingGame
{
    /// <summary>Registry of everything selectable, assigned to the GameManager by the scene builder.</summary>
    public class GameContent : ScriptableObject
    {
        public TextAsset movesets;
        public CharacterDef[] characters;
        public MapDef[] maps;
        public Material particleTemplate;
        public Material flameMaterial;
        public Material smokeMaterial;
    }
}
