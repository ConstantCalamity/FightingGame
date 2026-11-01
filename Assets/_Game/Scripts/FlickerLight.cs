using UnityEngine;

namespace FightingGame
{
    /// <summary>Firelight flicker for torches and braziers.</summary>
    public class FlickerLight : MonoBehaviour
    {
        Light l;
        float baseIntensity, seed;

        void Start()
        {
            l = GetComponent<Light>();
            baseIntensity = l.intensity;
            seed = Random.value * 100;
        }

        void Update()
        {
            float n = Mathf.PerlinNoise(Time.time * 7f, seed);
            l.intensity = baseIntensity * (0.75f + 0.45f * n);
        }
    }
}
