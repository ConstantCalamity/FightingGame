using System.Collections.Generic;
using UnityEngine;

namespace FightingGame
{
    /// <summary>Placeholder impact sounds synthesised at startup (filtered noise + a pitch sweep).</summary>
    public class Sfx
    {
        public enum Kind { Hit, Heavy, Block, Orb, KO, Parry, GuardBreak }

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
            // parry: two blades meeting
            clips[Kind.Parry] = Clash("parry", 0.7f);
            // guard break: a low, crunching impact with a falling tone
            clips[Kind.GuardBreak] = Make("guardbreak", 0.55f, 1100, 260, 55, 0.85f, 0.5f);
        }

        /// <summary>
        /// Sword-on-sword clash: a hard broadband crack, a short bright scrape, a low thud for weight, and a dense
        /// cluster of inharmonic steel modes. Each mode has a slightly detuned twin so the ring beats and sounds
        /// like struck metal rather than a tuned chime.
        /// </summary>
        static AudioClip Clash(string name, float dur)
        {
            const int rate = 44100;
            int n = (int)(rate * dur);
            var data = new float[n];
            var rng = new System.Random(name.GetHashCode());
            float[] modes = { 1187f, 1622f, 2351f, 2968f, 3733f, 4419f, 5246f, 6187f, 7341f, 8612f };
            var phase = new float[modes.Length * 2];
            for (int k = 0; k < phase.Length; k++) phase[k] = (float)rng.NextDouble() * Mathf.PI * 2;

            float hpCrack = 1 - Mathf.Exp(-2 * Mathf.PI * 1500f / rate);     // crack: noise above ~1.5 kHz
            float hpScrape = 1 - Mathf.Exp(-2 * Mathf.PI * 3500f / rate);    // scrape: a 3.5-9 kHz band
            float lpScrape = 1 - Mathf.Exp(-2 * Mathf.PI * 9000f / rate);
            float lowC = 0, lowS = 0, bandS = 0, peak = 0;
            for (int i = 0; i < n; i++)
            {
                float t = (float)i / rate;
                float noise = (float)(rng.NextDouble() * 2 - 1);
                lowC += (noise - lowC) * hpCrack;
                lowS += (noise - lowS) * hpScrape;
                bandS += ((noise - lowS) - bandS) * lpScrape;

                float s = (noise - lowC) * 1.1f * Mathf.Exp(-t * 85f);            // ~25 ms crack
                s += bandS * 0.45f * Mathf.Exp(-t * 22f) * (0.6f + 0.4f * Mathf.Sin(t * 260f));   // gritty scrape
                s += Mathf.Sin(2 * Mathf.PI * 165f * t) * 0.3f * Mathf.Exp(-t * 32f);             // body thud
                for (int k = 0; k < modes.Length; k++)
                {
                    float amp = 0.32f / Mathf.Pow(k + 1, 0.55f);
                    float decay = 5.5f + k * 2.6f;
                    float env = Mathf.Exp(-t * decay) * Mathf.Clamp01(t / 0.0015f);
                    float f2 = modes[k] * (1.004f + 0.0011f * k);
                    s += amp * env * (Mathf.Sin(2 * Mathf.PI * modes[k] * t + phase[2 * k]) +
                                      0.7f * Mathf.Sin(2 * Mathf.PI * f2 * t + phase[2 * k + 1]));
                }
                data[i] = (float)System.Math.Tanh(s * 1.3f);
                peak = Mathf.Max(peak, Mathf.Abs(data[i]));
            }
            float norm = 0.9f / Mathf.Max(0.001f, peak);
            float fadeStart = n - rate * 0.05f;
            for (int i = 0; i < n; i++)
                data[i] *= norm * (i > fadeStart ? (n - i) / (n - fadeStart) : 1f);
            var clip = AudioClip.Create(name, n, 1, rate, false);
            clip.SetData(data, 0);
            return clip;
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
