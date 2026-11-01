using UnityEngine;

namespace FightingGame
{
    /// <summary>Joint angles in radians. "A" limbs are the striking side (rear arm punches, rear leg kicks).</summary>
    public struct Pose
    {
        public float ShA, ElA, ShB, ElB, HpA, KnA, HpB, KnB, Twist, Lean, Dip;

        public static Pose Base => new Pose
        {
            ShA = -0.9f, ElA = -1.7f, ShB = -1.1f, ElB = -1.5f,
            HpA = 0.25f, KnA = 0.35f, HpB = -0.35f, KnB = 0.45f,
            Twist = 0.25f, Lean = 0.08f, Dip = -0.06f,
        };

        public static Pose Lerp(Pose a, Pose b, float k) => new Pose
        {
            ShA = Mathf.Lerp(a.ShA, b.ShA, k), ElA = Mathf.Lerp(a.ElA, b.ElA, k),
            ShB = Mathf.Lerp(a.ShB, b.ShB, k), ElB = Mathf.Lerp(a.ElB, b.ElB, k),
            HpA = Mathf.Lerp(a.HpA, b.HpA, k), KnA = Mathf.Lerp(a.KnA, b.KnA, k),
            HpB = Mathf.Lerp(a.HpB, b.HpB, k), KnB = Mathf.Lerp(a.KnB, b.KnB, k),
            Twist = Mathf.Lerp(a.Twist, b.Twist, k), Lean = Mathf.Lerp(a.Lean, b.Lean, k),
            Dip = Mathf.Lerp(a.Dip, b.Dip, k),
        };
    }

    /// <summary>
    /// A blocky placeholder character built from primitives, with a joint hierarchy that is posed from code.
    /// Swap this for an imported rigged model later; the gameplay code only talks to <see cref="Apply"/>.
    /// </summary>
    public class FighterRig
    {
        const float HipHeight = 1.03f;

        public Transform Root, Body, Hips, Torso;
        Transform shA, elA, shB, elB, hpA, knA, hpB, knB;
        Material bodyMat;
        Pose cur = Pose.Base;
        float yaw, fall, lift;
        bool flashOn;

        public static FighterRig Build(string name, Color color, Color accent, Material litTemplate)
        {
            Material Mat(Color c, float smooth, Color emission)
            {
                var m = new Material(litTemplate);
                m.SetColor("_BaseColor", c);
                m.SetFloat("_Smoothness", smooth);
                m.SetColor("_EmissionColor", emission);
                return m;
            }

            var r = new FighterRig();
            var body = r.bodyMat = Mat(color, 0.55f, Color.black);
            var skin = Mat(new Color(0.85f, 0.65f, 0.5f), 0.3f, Color.black);
            var dark = Mat(new Color(0.11f, 0.12f, 0.17f), 0.2f, Color.black);
            var acc = Mat(accent, 0.5f, accent * 1.2f);

            r.Root = new GameObject(name).transform;
            r.Body = Node("Body", r.Root, Vector3.zero);
            r.Hips = Node("Hips", r.Body, new Vector3(0, HipHeight, 0));
            Part(PrimitiveType.Cube, r.Hips, Vector3.zero, new Vector3(0.5f, 0.25f, 0.3f), dark);

            r.Torso = Node("Torso", r.Hips, new Vector3(0, 0.12f, 0));
            Part(PrimitiveType.Cube, r.Torso, new Vector3(0, 0.36f, 0), new Vector3(0.62f, 0.66f, 0.36f), body);
            Part(PrimitiveType.Cube, r.Torso, new Vector3(0, 0.05f, 0), new Vector3(0.64f, 0.09f, 0.38f), acc);
            Part(PrimitiveType.Sphere, r.Torso, new Vector3(0, 0.9f, 0), Vector3.one * 0.42f, skin);
            Part(PrimitiveType.Cube, r.Torso, new Vector3(0, 0.97f, 0), new Vector3(0.44f, 0.07f, 0.44f), acc);
            Part(PrimitiveType.Cube, r.Torso, new Vector3(0, 0.92f, 0.2f), new Vector3(0.26f, 0.04f, 0.02f), dark);
            Part(PrimitiveType.Cube, r.Torso, new Vector3(0.1f, 0.95f, -0.35f), new Vector3(0.05f, 0.05f, 0.4f), acc)
                .localRotation = Quaternion.Euler(-23, 0, 0);

            (r.shA, r.elA) = Arm(r.Torso, -1, body, skin, acc);
            (r.shB, r.elB) = Arm(r.Torso, 1, body, skin, acc);
            (r.hpA, r.knA) = Leg(r.Hips, -1, dark, acc);
            (r.hpB, r.knB) = Leg(r.Hips, 1, dark, acc);
            return r;
        }

        static (Transform, Transform) Arm(Transform torso, int side, Material body, Material skin, Material acc)
        {
            var sh = Node("Shoulder", torso, new Vector3(0.41f * side, 0.6f, 0));
            Part(PrimitiveType.Cube, sh, new Vector3(0, -0.18f, 0), new Vector3(0.17f, 0.36f, 0.17f), body);
            var el = Node("Elbow", sh, new Vector3(0, -0.36f, 0));
            Part(PrimitiveType.Cube, el, new Vector3(0, -0.16f, 0), new Vector3(0.14f, 0.32f, 0.14f), skin);
            Part(PrimitiveType.Sphere, el, new Vector3(0, -0.36f, 0), Vector3.one * 0.22f, acc);
            return (sh, el);
        }

        static (Transform, Transform) Leg(Transform hips, int side, Material dark, Material acc)
        {
            var hp = Node("Hip", hips, new Vector3(0.16f * side, -0.1f, 0));
            Part(PrimitiveType.Cube, hp, new Vector3(0, -0.225f, 0), new Vector3(0.21f, 0.45f, 0.21f), dark);
            var kn = Node("Knee", hp, new Vector3(0, -0.45f, 0));
            Part(PrimitiveType.Cube, kn, new Vector3(0, -0.21f, 0), new Vector3(0.18f, 0.42f, 0.18f), dark);
            Part(PrimitiveType.Cube, kn, new Vector3(0, -0.44f, 0.06f), new Vector3(0.19f, 0.08f, 0.32f), acc);
            return (hp, kn);
        }

        static Transform Node(string name, Transform parent, Vector3 pos)
        {
            var t = new GameObject(name).transform;
            t.SetParent(parent, false);
            t.localPosition = pos;
            return t;
        }

        static Transform Part(PrimitiveType type, Transform parent, Vector3 pos, Vector3 size, Material mat)
        {
            var go = GameObject.CreatePrimitive(type);
            Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<MeshRenderer>().sharedMaterial = mat;
            var t = go.transform;
            t.SetParent(parent, false);
            t.localPosition = pos;
            t.localScale = size;
            return t;
        }

        public void ResetPose(int facing)
        {
            cur = Pose.Base;
            yaw = facing > 0 ? 90 : -90;
            fall = lift = 0;
        }

        /// <summary>Blend toward the target pose and place the character in the world.</summary>
        public void Apply(Pose target, float k, float dt, float x, float y, int facing, bool knockedDown, bool flash)
        {
            cur = Pose.Lerp(cur, target, k);
            shA.localRotation = Rx(cur.ShA); elA.localRotation = Rx(cur.ElA);
            shB.localRotation = Rx(cur.ShB); elB.localRotation = Rx(cur.ElB);
            hpA.localRotation = Rx(cur.HpA); knA.localRotation = Rx(cur.KnA);
            hpB.localRotation = Rx(cur.HpB); knB.localRotation = Rx(cur.KnB);
            Torso.localRotation = Quaternion.Euler(cur.Lean * Mathf.Rad2Deg, cur.Twist * Mathf.Rad2Deg, 0);
            Hips.localPosition = new Vector3(0, HipHeight + cur.Dip, 0);

            Root.position = new Vector3(x, y, 0);
            yaw = Mathf.Lerp(yaw, facing > 0 ? 90 : -90, 1 - Mathf.Pow(1e-6f, dt));
            Root.rotation = Quaternion.Euler(0, yaw, 0);

            float fallK = 1 - Mathf.Pow(0.01f, dt);
            fall = Mathf.Lerp(fall, knockedDown ? -83 : 0, fallK);
            lift = Mathf.Lerp(lift, knockedDown ? 0.16f : 0, fallK);
            Body.localRotation = Quaternion.Euler(fall, 0, 0);
            Body.localPosition = new Vector3(0, lift, 0);

            if (flash != flashOn)
            {
                flashOn = flash;
                bodyMat.SetColor("_EmissionColor", flash ? new Color(0.8f, 0.8f, 0.8f) : Color.black);
            }
        }

        static Quaternion Rx(float rad) => Quaternion.Euler(rad * Mathf.Rad2Deg, 0, 0);
    }
}
