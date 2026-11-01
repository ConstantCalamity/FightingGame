"""Mordran the Flesh Eater: original dual-flail fighter. Rebuild with Blender -b -P this_file."""
import sys,os,math,random,json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import bpy,numpy as np
from mathutils import Vector,Matrix
import charlib as C, rigdef as R
from armorkit import Kit,rigid,smooth
from build_corvin import J as OLDJ
NAME='Mordran'; random.seed(19)
J={k:tuple(v[i]*(1.22 if i==0 else 1.08 if i==2 else 1) for i in range(3)) for k,v in OLDJ.items()}
C.reset_scene(); parts=[]
colors=[(.33,.055,.045),(.055,.063,.07),(.23,.13,.065),(.17,.13,.10),(.055,.035,.03),(.40,.35,.27),(.46,.20,.08),(.008,.006,.005)]
mats=[C.mat_flat('Palette'+str(i),c,.7 if i==0 else .45,.8 if i in (1,2,5) else 0) for i,c in enumerate(colors)]
def finish(o,mat,bone):
    C.finish(o,mats[mat],rigid(bone) if isinstance(bone,str) else bone,sub=0); parts.append(o); return o
def ell(name,center,scale,mat,bone):
    return finish(C.uv_sphere(name,1,center,seg=24,rings=16,scale=scale),mat,bone)
def bar(name,a,b,r,mat,bone,r2=None):
    a,b=Vector(a),Vector(b); o=C.loft(name,[dict(z=0,rx=r,ry=r),dict(z=(b-a).length,rx=r if r2 is None else r2,ry=r if r2 is None else r2)],12,cap0=True,cap1=True)
    C.place(o,a,b-a); return finish(o,mat,bone)
def blade(name,base,vec,width,kind):
    base=Vector(base); z=Vector(vec); length=z.length
    profile=[(-width,0),(width,0),(width*.68,length*.71),(width*.12,length*.64),(-width*.18,length)]
    if kind==1: profile=[(-width,0),(width,0),(width*.25,length*.87),(-width*.3,length*.76),(-width*.6,length)]
    verts=[(x,y,h) for y in (-.012,.012) for x,h in profile]; n=len(profile)
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    o=C.mesh_obj(name,verts,faces,False); C.place(o,base,z); finish(o,5,'chest')
    if kind!=2:
        unit=z.normalized(); bar(name+'Tang',base-unit*.12,base,.018,4,'chest')
        cross=unit.cross(Vector((0,1,0))).normalized(); bar(name+'BrokenGuard',base+cross*width*1.7,base-cross*width*1.3,.013,2,'chest')
# Continuous underlying torso and limbs, then layered muscle volumes.
kit=Kit(J,dict(chain=mats[0]),w=1.65)
parts+=kit.underbody()
for side,sign in [('L',1),('R',-1)]:
    def pt(k): v=J[k]; return Vector((v[0]*sign,v[1],v[2]))
    for name,a,b,r,depth,bone in [('Deltoid','shoulder','elbow',.125,.13,'upperarm.'+side),('Forearm','elbow','wrist',.095,.09,'forearm.'+side),('Thigh','hip','knee',.15,.13,'thigh.'+side),('Calf','knee','ankle',.105,.09,'shin.'+side)]:
        p=(pt(a)+pt(b))*.5; ell(name+side,p,(r,depth,(pt(a)-pt(b)).length*.62),0,bone)
    ell('Pectoral'+side,(sign*.14,-.12,1.44),(.17,.075,.11),0,'chest')
    ell('Fist'+side,pt('handEnd')+Vector((0,0,.04)),(.073,.075,.10),0,'hand.'+side)
    ell('Boot'+side,pt('toe')+Vector((0,.02,.035)),(.105,.20,.095),1,'foot.'+side)
    for z in (.16,.23,.31,.39):
        bar('GreaveBand'+side,(sign*.155,-.065,z),(sign*.155,.08,z),.064,2,'shin.'+side)
    for k,bn in [('wrist','forearm.'+side),('elbow','forearm.'+side)]:
        p=pt(k); ell('LeatherWrap'+side,p,(.085,.09,.055),4,bn)
for z in (1.12,1.23,1.32):
    for x in (-.065,.065): ell('Abdominal',(x,-.112,z),(.083,.065,.065),0,'spine')
ell('Belly',(0,.01,1.18),(.24,.15,.25),0,smooth(['hips','spine','chest']))
# Distinct uneven armor: one high segmented shoulder, crossed leather baldric, narrow cage helm.
for i in range(3): ell('LeftShoulderLame',(.285+i*.028,.012,1.61-i*.045),(.17,.16,.055),1,'upperarm.L')
ell('RightShoulderPlate',(-.29,.02,1.57),(.16,.13,.075),2,'upperarm.R')
for sign in (-1,1): bar('CrossedHarness',(sign*.26,-.165,1.60),(-sign*.18,-.17,1.10),.028,4,'chest')
for z in (1.05,1.0):
    o=C.loft('IronWaist',[dict(z=z,rx=.255,ry=.16),dict(z=z+.035,rx=.255,ry=.16)],40); finish(o,2,'hips')
for i in range(9):
    x=(i-4)*.054; length=.28+.16*(1-abs(x)/.25)+random.random()*.08
    o=C.mesh_obj('SplitLeatherSkirt',[(x-.033,-.17,1.01),(x+.033,-.17,1.01),(x+.029,-.205,1.01-length*.85),(x-.012,-.215,1.01-length)],[(0,1,2,3)],False)
    C.solidify(o,.008); C.apply_mods(o); finish(o,4,'hips')
# Hoodless angular executioner helmet, brow and staggered bronze face slats; no copied horns.
ell('HelmShell',(0,.005,1.89),(.145,.15,.20),1,'head')
ell('BlackVisor',(0,-.139,1.85),(.118,.035,.145),7,'head')
for i in range(-3,4):
    x=i*.032; bar('VisorBar',(x,-.18,1.99-abs(i)*.012),(x*.85,-.185,1.73+abs(i)*.012),.008,2,'head')
bar('HeavyBrow',(-.14,-.16,1.98),(.14,-.16,1.98),.018,5,'head')
# Embedded broken weapons, with broad blades, snapped edges, guards, tangs and spear shafts.
for i in range(11):
    angle=(i-5)*.14; base=(math.sin(angle)*.29,.145,1.43+random.uniform(-.08,.10))
    vec=(math.sin(angle)*(.35+random.random()*.2),.17+random.random()*.12,.42+random.random()*.29)
    if i%3==2:
        v=Vector(vec); bar('SnappedSpearShaft',base,Vector(base)+v*.7,.018,4,'chest'); blade('BrokenSpearhead',Vector(base)+v*.7,v*.45,.044,2)
    else: blade('BrokenSword' if i%2 else 'BrokenKnife',base,vec,.045 if i%2 else .027,i%2)
# Old wounds, layered scar ridges and split bracer plates break up the broad flesh surfaces.
for i in range(18):
    x=random.uniform(-.21,.21); z=random.uniform(1.10,1.55)
    a=(x,-.19,z); b=(x+random.uniform(.025,.07),-.191,z+random.uniform(.025,.07))
    bar('HealedWeaponScar',a,b,.004,7,'chest')
    bar('RaisedScarEdge',Vector(a)+Vector((.006,.001,0)),Vector(b)+Vector((.006,.001,0)),.003,6,'chest')
for side,sign in [('L',1),('R',-1)]:
    hand=Vector((sign*J['handEnd'][0],J['handEnd'][1],J['handEnd'][2]))
    for finger in range(4):
        x=hand.x+(finger-1.5)*.026
        ell('FoldedFinger'+side,(x,hand.y-.062,hand.z+.015),(.014,.025,.040),0,'hand.'+side)
    ell('Thumb'+side,hand+Vector((sign*.06,-.025,.04)),(.025,.035,.05),0,'hand.'+side)
    for z in (.14,.22,.30):
        center=Vector((sign*.155,.01,z)); path=[center+Vector((.09*math.cos(k*math.tau/24),.095*math.sin(k*math.tau/24),0)) for k in range(25)]
        finish(C.sweep('BootShackle'+side,path,C.circle_profile(.012,6),closed_path=True),2,'shin.'+side)
# Skeleton: independent chain bones follow each hand; collision markers at each ball.
weapon=dict(grip=J['handEnd'],tip=tuple(Vector(J['handEnd'])+Vector((0,0,-.62))),edge=(0,-1,0))
bones=R.skeleton(J,weapon,two_handed=False)
# weapon is an exported marker, no IK dependency; both hands animate independently.
for b in bones:
    if b['name']=='weapon': b['parent']='hand.R'; b['head']=(-J['handEnd'][0],J['handEnd'][1],J['handEnd'][2]); b['tail']=tuple(Vector(b['head'])+Vector((0,0,-.15)))
    if b['name']=='weapon_tip': b['parent']='chain.R'; b['head']=(-J['handEnd'][0],J['handEnd'][1],J['handEnd'][2]-.64); b['tail']=tuple(Vector(b['head'])+Vector((0,0,-.08)))
for side,sign in [('L',1),('R',-1)]:
    grip=Vector((sign*J['handEnd'][0],J['handEnd'][1],J['handEnd'][2]))
    bones.append(dict(name='chain.'+side,head=tuple(grip),tail=tuple(grip+Vector((0,0,-.64))),parent='hand.'+side,z_axis=(0,-1,0)))
    if side=='L':
        bones.append(dict(name='weapon_left',head=tuple(grip),tail=tuple(grip+Vector((0,0,-.10))),parent='hand.L',z_axis=(0,-1,0)))
        bones.append(dict(name='weapon_tip_left',head=tuple(grip+Vector((0,0,-.64))),tail=tuple(grip+Vector((0,0,-.72))),parent='chain.L',z_axis=(0,-1,0)))
    for n in range(11):
        center=grip+Vector((0,0,-n*.054)); path=[]
        for k in range(13):
            a=k*math.tau/12; path.append(center+Vector((math.cos(a)*.022 if n%2==0 else 0,math.cos(a)*.022 if n%2 else 0,math.sin(a)*.035)))
        finish(C.sweep('ForgedLink'+side,path,C.circle_profile(.007,6),closed_path=True),1,'chain.'+side)
    ball=grip+Vector((0,0,-.64)); ell('SpikedBall'+side,ball,(.125,.125,.125),1,'chain.'+side)
    for k in range(14):
        z=1-2*(k+.5)/14; a=k*2.39996; v=Vector((math.sqrt(1-z*z)*math.cos(a),math.sqrt(1-z*z)*math.sin(a),z))
        bar('FlailSpike'+side,ball+v*.11,ball+v*.205,.027,5,'chain.'+side,.001)
arm=C.build_armature(bones); C.bind_all(parts,arm); body=C.join(parts,NAME+'_Body'); C.skin_to(body,arm)
# A compact UV palette atlas preserves color/material variation without an expensive texture bake.
mesh=body.data; old=list(mesh.materials); atlas=mesh.uv_layers.new(name='UVMap')
for poly in mesh.polygons:
    idx=int(old[poly.material_index].name.replace('Palette','')) if old[poly.material_index].name.startswith('Palette') else 0
    for li in poly.loop_indices:
        v=mesh.vertices[mesh.loops[li].vertex_index].co; u=(v.x*1.5+v.y*.6)%1; vv=(v.z*1.4)%1
        atlas.data[li].uv=((idx%4+.08+u*.84)/4,(idx//4+.08+vv*.84)/2)
texdir=os.path.join(C.REPO,'Assets','_Game','Art','Characters',NAME); os.makedirs(texdir,exist_ok=True)
size=1024; rng=np.random.default_rng(19); pix=np.ones((size,size,4),dtype=np.float32); mask=pix.copy()
for i,col in enumerate(colors):
    xs=slice((i%4)*256,(i%4+1)*256); ys=slice((i//4)*512,(i//4+1)*512)
    noise=rng.uniform(.72,1.15,(512,256,1)); pix[ys,xs,:3]=np.array(col)*noise
    mask[ys,xs,:3]=(0.8 if i in (1,2,5) else 0); mask[ys,xs,3]=.35
for channel,data in [('Albedo',pix),('Mask',mask)]:
    img=bpy.data.images.new('T_'+NAME+'_Body_'+channel,size,size,alpha=True); img.pixels.foreach_set(data.ravel()); img.filepath_raw=os.path.join(texdir,img.name+'.png'); img.file_format='PNG'; img.save()
m=C.mat_flat('M_'+NAME+'_Body',(1,1,1)); m.use_nodes=True; nt=m.node_tree; node=nt.nodes.new('ShaderNodeTexImage'); node.image=bpy.data.images['T_'+NAME+'_Body_Albedo']; nt.links.new(node.outputs['Color'],next(n for n in nt.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color']); mesh.materials.clear(); mesh.materials.append(m)
for p in mesh.polygons:p.material_index=0
# FK actions, with separately keyed flail swings. Legs/torso reuse the standard exported skeleton.
bpy.context.view_layer.objects.active=arm
clips=['Idle','WalkFwd','WalkBack','Jump','Block','Hit','KO','Win','Light','Heavy','Special','Air']
spec=json.load(open(os.path.join(C.REPO,'Assets/_Game/Data/Movesets.json'))); spec=next(c for c in spec['characters'] if c['id']==NAME)
for name in clips:
    duration=60 if name=='Idle' else 30
    move=next((m for m in spec['moves'] if m['id']==name),None)
    if move: duration=move['startupF']+move['activeF']+move['recoveryF']
    C.new_action(arm,name)
    for f in range(duration+1):
        bpy.context.scene.frame_set(f)
        phase=f/duration; wave=math.sin(phase*math.tau); pulse=math.sin(math.pi*phase)
        for pb in arm.pose.bones:pb.rotation_mode='XYZ';pb.rotation_euler=(0,0,0);pb.location=(0,0,0)
        def rot(b,x=0,y=0,z=0):arm.pose.bones[b].rotation_euler=tuple(math.radians(a) for a in (x,y,z))
        # Lower the A-pose upper arms into a relaxed fighting stance.
        rot('upperarm.L',0,0,-12);rot('upperarm.R',0,0,12)
        rot('forearm.L',-22);rot('forearm.R',-22);rot('chest',3+wave*1.5)
        if name.startswith('Walk'):
            sign=1 if name=='WalkFwd' else -1
            rot('thigh.L',wave*24*sign);rot('thigh.R',-wave*24*sign);rot('shin.L',max(0,-wave)*28);rot('shin.R',max(0,wave)*28)
        if name in ('Jump','Air'):rot('thigh.L',-38);rot('thigh.R',-25);rot('shin.L',65);rot('shin.R',50)
        if name=='Block':rot('forearm.L',-100);rot('forearm.R',-100);rot('upperarm.L',-25);rot('upperarm.R',-25)
        if name=='Hit':rot('chest',-pulse*22);rot('head',pulse*12)
        if name=='KO':rot('hips',-phase*80);arm.pose.bones['hips'].location.z=-phase*.65
        if name=='Win':rot('upperarm.L',-75*pulse);rot('upperarm.R',-75*pulse)
        if move:
            # Wind up before the authored startup frame, then sweep each weighted chain into range.
            t=f/max(1,move['startupF']); attack=math.sin(min(1,t)*math.pi/2)
            for side in (['R'] if name=='Light' else ['L'] if name=='Heavy' else ['R','L']):
                rot('upperarm.'+side,45*attack,0,0);rot('forearm.'+side,15*attack)
                rot('chain.'+side,-110*attack+math.sin(phase*math.pi*2)*25,0,(-15 if side=='L' else 15)*pulse)
            rot('chest',8*pulse,0,(-18 if name=='Heavy' else 18)*pulse)
        else:
            rot('chain.L',wave*7);rot('chain.R',-wave*7)
        bpy.context.view_layer.update()
        if move:
            for side in (['R'] if name=='Light' else ['L'] if name=='Heavy' else ['R','L']):
                grip=arm.pose.bones['chain.'+side].head.copy()
                swing=math.radians(75)*min(1,f/max(1,move['startupF']))
                C.set_bone_matrix(arm,'chain.'+side,C.weapon_matrix(grip,(0,-math.sin(swing),-math.cos(swing)),(1,0,0)))
            bpy.context.view_layer.update()
        for pb in arm.pose.bones:
            if pb.bone.use_deform: C.key_bone(arm,pb.name,f)
arm.animation_data.action=None
for pb in arm.pose.bones:pb.rotation_euler=(0,0,0);pb.location=(0,0,0)
C.save_blend(os.path.join(C.REPO,'ArtSource','Characters',NAME+'.blend'))
C.export_fbx(os.path.join(texdir,NAME+'.fbx'),[arm,body])
C.preview_setup('CYCLES',24,res=(900,1100)); C.three_point()
for label,pos in [('front',(2.7,-4.2,2.0)),('back',(-2.7,4.2,2.0))]:
    C.camera_look('Preview'+label,pos,(0,0,1.08),55); C.render_to(os.path.join(C.REPO,'Logs','chars',NAME+'_'+label+'.png'))
C.log('complete',NAME,'triangles',C.tri_count(body))



