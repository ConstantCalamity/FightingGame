using UnityEngine;

namespace FightingGame
{
    /// <summary>
    /// Lightweight secondary motion for a bone chain (capes): each bone's tip is a damped particle pulled
    /// toward its animated position and kept at bone length. Runs after animation in LateUpdate.
    /// </summary>
    public class SpringChain : MonoBehaviour
    {
        public float stiffness = 0.12f;
        public float damping = 0.2f;
        public Vector3 gravity = new Vector3(0, -2.5f, 0);

        Transform[] bones;
        Vector3[] tipLocal;
        Vector3[] pos, prev;
        float[] length;
        bool primed;

        public void Init(Transform[] chain)
        {
            bones = chain;
            int n = bones.Length;
            tipLocal = new Vector3[n];
            pos = new Vector3[n];
            prev = new Vector3[n];
            length = new float[n];
            for (int i = 0; i < n; i++)
            {
                // tip = next bone's origin, or extrapolate along the last bone
                Vector3 tipWorld = i + 1 < n ? bones[i + 1].position
                    : bones[i].position + (bones[i].position - bones[i - 1].position);
                tipLocal[i] = bones[i].InverseTransformPoint(tipWorld);
                length[i] = Vector3.Distance(bones[i].position, tipWorld);
            }
            primed = false;
        }

        public void ResetSim() => primed = false;

        public void Step(float dt)
        {
            if (bones == null || dt <= 0) return;
            dt = Mathf.Min(dt, 1f / 30f);
            for (int i = 0; i < bones.Length; i++)
            {
                var b = bones[i];
                Vector3 target = b.TransformPoint(tipLocal[i]);
                if (!primed)
                {
                    pos[i] = prev[i] = target;
                    continue;
                }
                Vector3 velocity = (pos[i] - prev[i]) * (1 - damping);
                prev[i] = pos[i];
                Vector3 p = pos[i] + velocity + gravity * (dt * dt);
                p = Vector3.Lerp(p, target, stiffness);
                Vector3 dir = p - b.position;
                if (dir.sqrMagnitude < 1e-8f) dir = target - b.position;
                p = b.position + dir.normalized * length[i];
                pos[i] = p;
                Vector3 animDir = target - b.position;
                b.rotation = Quaternion.FromToRotation(animDir, p - b.position) * b.rotation;
            }
            primed = true;
        }
    }
}
