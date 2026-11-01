using System.Collections.Generic;
using UnityEngine;

namespace FightingGame
{
    /// <summary>Placeholder impact sounds synthesised at startup (filtered noise + a pitch sweep).</summary>
    public class Sfx
    {
        public enum Kind { Hit, Heavy, Block, Orb, KO }

        readonly AudioSource source;
        readonly Dictionary<Kind, AudioClip> clips = new Dictionary<Kind, AudioClip>();

        public Sfx(GameObject host)
        {
            source = host.AddComponent<AudioSource>();
            source.playOnAwake = false;
            clips[Kind.Hit] = Make("hit", 0.14f, 1800, 160, 45, 0.55f, 0.35f);
            clips[Kind.Heavy] = Make("heavy", 0.2f, 900, 160, 45, 0.6f, 0.4f);
            clips[Kind.Block] = Make("block", 0.07f, 4000, 0, 0, 0.3f, 0);
            clips[Kind.Orb] = Make("orb", 0.3f, 600, 300, 900, 0.4f, 0.25f);
            clips[Kind.KO] = Make("ko", 0.6f, 400, 160, 40, 0.6f, 0.45f);
        }

        public void Play(Kind k) => source.PlayOneShot(clips[k]);

        static AudioClip Make(string name, float dur, float cutoff, float toneFrom, float toneTo, float noiseVol, float toneVol)
        {
            const int rate = 44100;
            int n = (int)(rate * dur);
            var data = new float[n];
            var rng = new System.Random(name.GetHashCode());
            float a = 1 - Mathf.Exp(-2 * Mathf.PI * cutoff / rate);
            float lp = 0, phase = 0;
            for (int i = 0; i < n; i++)
            {
                float t = (float)i / n;
                float env = Mathf.Pow(1 - t, 2.5f);
                lp += ((float)(rng.NextDouble() * 2 - 1) - lp) * a;
                float s = lp * noiseVol * 2;
                if (toneVol > 0)
                {
                    phase += 2 * Mathf.PI * toneFrom * Mathf.Pow(toneTo / toneFrom, t) / rate;
                    s += Mathf.Sin(phase) * toneVol;
                }
                data[i] = Mathf.Clamp(s * env, -1, 1);
            }
            var clip = AudioClip.Create(name, n, 1, rate, false);
            clip.SetData(data, 0);
            return clip;
        }
    }
}
