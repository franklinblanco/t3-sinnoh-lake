from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageOps
from cruise import LakeTraffic
import numpy as np
import math, struct, sys
from io import BytesIO

work = Path(__file__).parent
art = work.parent / 'assets'
sprites_dir = work / 'sprites'
assets = art / 'phases'
assets.mkdir(parents=True, exist_ok=True)
original = Image.open(art / "sinnoh-rift.png").convert("RGB")
W,H = original.size
import argparse
parser = argparse.ArgumentParser(description="Build one lake phase from the source artwork.")
parser.add_argument("phase", choices=["day", "night", *(
    f"{direction}{level}" for direction in ("rise", "set") for level in range(1, 9)
)])
parser.add_argument("--preview", type=Path, help="Save a still from the composed animation")
parser.add_argument("--frame", type=int, choices=range(240), metavar="0..239", default=0)
args = parser.parse_args()
phase = args.phase
mode, step = ("night",0) if phase=="night" else ("day",8) if phase=="day" else (phase[:-1],int(phase[-1]))
def mix(a,b,f):
    return a*(1-f) + b*f

def scene():
    src = np.asarray(original,dtype=np.float32)
    lum = src @ np.array([.24,.56,.20],dtype=np.float32)
    x = (np.arange(W,dtype=np.float32)[None,:]+.5)/W
    y = (np.arange(H,dtype=np.float32)[:,None]+.5)/H
    stops = [0,19,37,55,80,110,159,214,255]
    def ramp(palette, chroma):
        palette=np.array(palette)
        colors=np.stack([np.interp(lum,stops,channel) for channel in palette.T],axis=-1)
        return colors+(src-lum[...,None])*chroma
    night=src*np.array([.74,.79,.96])
    if mode=='night': return Image.fromarray(np.uint8(np.clip(night,0,255)))
    blue=ramp([(5,23,40),(14,45,64),(34,81,103),(63,116,142),(96,147,168),(133,176,188),(178,206,211),(224,235,229),(250,252,241)],.30)
    # The low sky and the lake itself catch more skylight than the shaded foreground.
    daylight=blue+np.array([7,17,23])*np.exp(-((y-.36)/.38)**2)[:,:,None]
    if mode=='day': return Image.fromarray(np.uint8(np.clip(daylight,0,255)))
    morning = mode=='rise'
    center = .448 if morning else .656
    golden = ramp(([(12,24,48),(27,41,64),(62,71,90),(100,101,114),(150,129,132),(189,154,149),(232,192,165),(255,228,191),(255,245,219)]
         if morning else [(17,18,42),(39,32,60),(78,55,82),(118,75,96),(163,97,103),(202,123,111),(240,164,127),(255,212,164),(255,237,201)]),.32)
    glow=np.exp(-((x-center)/.27)**2-((y-.36)/.135)**2)
    golden+=glow[:,:,None]*(np.array([98,61,19]) if morning else np.array([110,58,11]))
    # The lake catches a broken column of light in its existing horizontal pixel texture.
    surface=np.clip((y-.548)/.078,0,1)*np.exp(-((y-.65)/.21)**2)
    strokes=.35+.65*np.clip((lum-26)/35,0,1)
    reflected=np.exp(-((x-center)/(.029+.10*np.maximum(0,y-.54)))**2)*surface*strokes
    golden+=reflected[:,:,None]*np.array([86,47,13])
    f=[0,.16,.36,.62,.85,1,.73,.43,.20][step]
    base=night if step<=5 else daylight
    result=mix(base,golden,f)
    # A pixel sun peeks over the ridge. Sampled skyline segments follow the art at each disc.
    if step>=4:
        cx=round((center+(.007 if morning else -.007)*(step-5))*W)
        rx=np.arange(W)
        if morning:
            ridge=np.interp(rx/2,[345,355,361,370,382,390,400,410],[151,146,146,153,159,162,164,164])*2
        else:
            ridge=np.interp(rx/2,[505,515,526,536,549,557,565,573],[181,180,185,189,186,184,181,185])*2
        cy=ridge[cx]+[0,0,0,0,6,-6,-25,-54,-92][step]
        px=(np.arange(W)//3*3)[None,:]; py=(np.arange(H)//3*3)[:,None]
        sun=((px-cx)**2+(py-cy)**2<19**2)&(py<ridge[None,:]-3)
        result[sun]=mix(result[sun],np.array([255,232,172]),.83 if step<=6 else .58)
    return Image.fromarray(np.uint8(np.clip(result,0,255)))

lake=scene()
traffic = LakeTraffic(lake, mode, step)
waters=(0,round(H*.55),W,round(H*.87))
water=lake.crop(waters).convert('RGBA')
swimmers=[(129,.32,.125,.669,57,.18),(129,.48,.079,.614,38,.84),(418,.68,.114,.738,59,.57),(456,.50,.142,.792,78,.38)]
def load_swimmer(species,width):
    gif=Image.open(sprites_dir/f'{species}.gif')
    frames=[]; ends=[]
    for i in range(gif.n_frames):
        gif.seek(i)
        frame=gif.convert('RGBA')
        # Register every frame to the opaque silhouette; the battle sprites contain jump
        # offsets and uneven transparent margins that would lift them above the wake.
        frame=frame.crop(frame.getbbox())
        if species==129:
            frame=frame.rotate(19,Image.Resampling.NEAREST,expand=True)
            frame=frame.crop(frame.getbbox())
        height=round(frame.height*width/frame.width*({129:.50,418:.84,456:.71}[species]))
        frame=frame.resize((width,height),Image.Resampling.NEAREST)
        frames.append(frame)
        ends.append((ends[-1] if ends else 0)+gif.info.get("duration",100))
    return frames,ends
groups=[load_swimmer(s[0],s[4]) for s in swimmers]
def render(n):
    t=n/240
    sheet=water.copy()
    traffic.draw_boat(sheet, waters[1], t)
    for (species,center,radius,line,width,phase_offset),(frames,ends) in zip(swimmers,groups):
        angle=2*math.pi*(t+phase_offset)
        x=round(W*(center+radius*math.cos(angle)))
        y=round(H*(line+.012*math.sin(angle)))-waters[1]
        pos=(t*round(24000/ends[-1])+phase_offset)%1*ends[-1]
        frame=frames[next(i for i,end in enumerate(ends) if end>pos)]
        # Narrow the silhouette during a turn; both sides meet at the end of the path.
        span=round(width*(.52+.48*min(1,abs(math.sin(angle))*4)))
        stride=frame.resize((span,frame.height),Image.Resampling.NEAREST)
        direction=1 if math.sin(angle)<0 else -1
        if direction>0: stride=ImageOps.mirror(stride)
        hh=stride.height
        surface=int(hh*({129:.20,418:.49,456:.10}[species]))
        top=y-surface
        left=x-span//2
        under=sheet.crop((left,top,left+span,top+hh))
        # The lake texture shows through the submerged bodies. Only Buizel's head and
        # the crest of the larger Magikarp are clear of the surface.
        for row in range(hh):
            depth=(row-surface)/hh
            visibility= (.74 if depth<0 else max(.16,.52-.39*depth))
            if species==456: visibility=.43-.18*max(0,depth)
            strip=stride.crop((0,row,span,row+1))
            strip.putalpha(strip.getchannel("A").point(lambda a,s=visibility:round(a*s)))
            shift=round(math.sin(row*.52+12*angle)) if depth>0 else 0
            under.alpha_composite(strip,(shift,row))
        sheet.paste(under,(left,top))
        draw=ImageDraw.Draw(sheet)
        for k in range(3):
            p=(t*12+phase_offset+k/3)%1
            wake_x=round(x-direction*span*(.26+.58*p))
            wy=y+round(1+4*p)
            size=round(span*(.15-.10*p))+1
            shore=water.getpixel((wake_x,wy))[:3]
            color=tuple(round(mix(c,198,(1-p)*(.32 if species!=456 else .18))) for c in shore)
            draw.line((wake_x-size,wy,wake_x+size,wy),fill=color)
        # Foreground ripple crosses the sprite at its waterline.
        for start,end in [(-.34,-.15),(-.06,.21)]:
            wy=y+(1 if start<-.1 else 0)
            rgb=water.getpixel((x,wy))[:3]
            col=tuple(round(mix(c,183,.31 if species!=456 else .21)) for c in rgb)
            draw.line((round(x+start*span),wy,round(x+end*span),wy),fill=col,width=2)
    frame = lake.copy()
    frame.paste(sheet, waters[:2])
    traffic.sky(frame, t)
    return frame

if args.preview:
    render(args.frame).save(args.preview)
    sys.exit()

def chunk(tag,data):
    return tag+struct.pack("<I",len(data))+data+b"\0"*(len(data)%2)
def u24(n):return int(n).to_bytes(3,"little")
def encode(im,x=0,y=0):
    s=BytesIO(); im.save(s, "WEBP",lossless=True,method=2)
    blob=s.getvalue()[12:]; assert blob[:4]==b'VP8L'
    return chunk(b'ANMF',b''.join(map(u24,[x//2,y//2,im.width-1,im.height-1,100]))+b'\0'+blob)
body=bytearray(chunk(b'VP8X',bytes([18,0,0,0])+u24(W-1)+u24(H-1))+chunk(b'ANIM',bytes(6)))
prev=None
for n in range(240):
    frame = render(n)
    if prev is None:
        body.extend(encode(frame))
    else:
        diff = ImageChops.difference(frame, prev)
        left, top, right, bottom = diff.getbbox()
        # ANMF positions use two-pixel units. Unchanged pixels inside the
        # bounding box stay transparent between the sky and water layers.
        box = (left & ~1, top & ~1, right, bottom)
        patch = frame.crop(box)
        r, g, b = diff.crop(box).split()
        mask = ImageChops.lighter(r, ImageChops.lighter(g, b)).point(lambda v: 255 if v else 0)
        patch.putalpha(mask)
        body.extend(encode(patch, box[0], box[1]))
    prev = frame
out=assets/(phase+'.webp')
out.write_bytes(chunk(b'RIFF',b'WEBP'+body))
with Image.open(out) as check:
    assert check.n_frames==240 and check.info['loop']==0 and out.stat().st_size<16*1024*1024
    for n in [0,60,150,239]:
        check.seek(n)
        assert ImageChops.difference(check.convert('RGB'), render(n)).getbbox() is None
print(phase,out.stat().st_size,flush=True)
